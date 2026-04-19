/**
 * Read-only workspace browse for the Web UI's file-tree panel.
 *
 * `/.claude` and `/.venv` are bind-mounted per-agent inside the bubblewrap
 * sandbox; on the pod those copies in `sessions/{sid}/shared/` are empty
 * mount points. Reads of those virtual prefixes redirect to
 * `sessions/{sid}/agents/{aid}/` so the tree shows the real contents.
 */

import * as fs from "node:fs";
import * as path from "node:path";

import { sessionClaudeDir, sessionSharedDir, sessionVenvDir } from "./constants.js";

const DEFAULT_MAX_FILE_BYTES = 2 * 1024 * 1024; // 2 MiB

export function workspaceMaxFileBytes(): number {
  const raw = process.env.WORKSPACE_MAX_FILE_BYTES;
  const parsed = raw ? parseInt(raw, 10) : NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_MAX_FILE_BYTES;
}

export interface TreeEntry {
  name: string;
  type: "file" | "dir";
  size?: number;
  mtime?: number;
  hidden?: boolean;
}

export interface TreeListing {
  path: string;
  entries: TreeEntry[];
}

export interface FileContents {
  path: string;
  content: string;
  encoding: "utf8" | "base64";
  size: number;
  mtime: number;
  isBinary: boolean;
  truncated: boolean;
}

export class WorkspaceError extends Error {
  constructor(public readonly code: "invalid_path" | "not_found" | "not_a_directory" | "not_a_file" | "too_large", message: string) {
    super(message);
    this.name = "WorkspaceError";
  }
}

// Dot-prefix directories are hidden by default; dot-files (.gitignore, .env)
// stay visible. `include_hidden` surfaces hidden dirs with hidden:true.
function isHiddenEntry(name: string, isDir: boolean): boolean {
  return isDir && name.startsWith(".");
}

function resolveInsideBase(base: string, rel: string): string {
  const stripped = (rel ?? "").replace(/^\/+/, "");
  const joined = path.resolve(base, stripped);
  const baseResolved = path.resolve(base);
  if (joined !== baseResolved && !joined.startsWith(baseResolved + path.sep)) {
    throw new WorkspaceError("invalid_path", "path escapes session workspace");
  }
  return joined;
}

interface ResolvedPath {
  /** Base dir on the pod filesystem — used for traversal check + relativizing. */
  diskBase: string;
  /** Prefix in the user-facing virtual layout ("/", "/.claude", "/.venv"). */
  virtualBase: string;
  abs: string;
}

function resolvePath(
  sessionId: string,
  agentId: string | null,
  rel: string,
): ResolvedPath {
  const stripped = (rel ?? "").replace(/^\/+/, "");
  const firstSlash = stripped.indexOf("/");
  const head = firstSlash === -1 ? stripped : stripped.slice(0, firstSlash);
  const tail = firstSlash === -1 ? "" : stripped.slice(firstSlash + 1);

  if (head === ".claude" || head === ".venv") {
    if (!agentId) {
      throw new WorkspaceError(
        "invalid_path",
        `agent_id is required to read ${head}`,
      );
    }
    const diskBase = head === ".claude"
      ? sessionClaudeDir(sessionId, agentId)
      : sessionVenvDir(sessionId, agentId);
    fs.mkdirSync(diskBase, { recursive: true });
    const abs = tail ? resolveInsideBase(diskBase, tail) : path.resolve(diskBase);
    return { diskBase, virtualBase: "/" + head, abs };
  }

  const diskBase = sessionSharedDir(sessionId);
  fs.mkdirSync(diskBase, { recursive: true });
  const abs = resolveInsideBase(diskBase, stripped);
  return { diskBase, virtualBase: "/", abs };
}

function toVirtualPath(resolved: ResolvedPath): string {
  const rel = path.relative(resolved.diskBase, resolved.abs);
  const segments = rel.split(path.sep).filter(Boolean);
  if (resolved.virtualBase === "/") {
    return segments.length === 0 ? "/" : "/" + segments.join("/");
  }
  return segments.length === 0
    ? resolved.virtualBase
    : resolved.virtualBase + "/" + segments.join("/");
}

export function listTree(
  sessionId: string,
  agentId: string | null,
  relPath: string,
  includeHidden: boolean,
): TreeListing {
  const resolved = resolvePath(sessionId, agentId, relPath);

  let stat: fs.Stats;
  try {
    stat = fs.lstatSync(resolved.abs);
  } catch {
    throw new WorkspaceError("not_found", "path not found");
  }
  if (stat.isSymbolicLink()) {
    throw new WorkspaceError("invalid_path", "symlinks are not traversed");
  }
  if (!stat.isDirectory()) {
    throw new WorkspaceError("not_a_directory", "path is not a directory");
  }

  const entries: TreeEntry[] = [];
  for (const name of fs.readdirSync(resolved.abs)) {
    let child: fs.Stats;
    try {
      child = fs.lstatSync(path.join(resolved.abs, name));
    } catch {
      continue;
    }
    if (child.isSymbolicLink()) continue;
    if (!child.isFile() && !child.isDirectory()) continue;

    const isDir = child.isDirectory();
    const isHidden = isHiddenEntry(name, isDir);
    if (isHidden && !includeHidden) continue;

    const entry: TreeEntry = {
      name,
      type: isDir ? "dir" : "file",
      mtime: Math.floor(child.mtimeMs),
    };
    if (!isDir) entry.size = child.size;
    if (isHidden) entry.hidden = true;
    entries.push(entry);
  }

  entries.sort((a, b) => {
    if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });

  return { path: toVirtualPath(resolved), entries };
}

export function readFile(
  sessionId: string,
  agentId: string | null,
  relPath: string,
): FileContents {
  const resolved = resolvePath(sessionId, agentId, relPath);

  let stat: fs.Stats;
  try {
    stat = fs.lstatSync(resolved.abs);
  } catch {
    throw new WorkspaceError("not_found", "file not found");
  }
  if (stat.isSymbolicLink()) {
    throw new WorkspaceError("invalid_path", "symlinks are not followed");
  }
  if (!stat.isFile()) {
    throw new WorkspaceError("not_a_file", "path is not a file");
  }

  const max = workspaceMaxFileBytes();
  if (stat.size > max) {
    throw new WorkspaceError("too_large", `file exceeds ${max} bytes`);
  }

  const buf = fs.readFileSync(resolved.abs);
  const isBinary = looksBinary(buf);

  return {
    path: toVirtualPath(resolved),
    content: isBinary ? "" : buf.toString("utf8"),
    encoding: "utf8",
    size: stat.size,
    mtime: Math.floor(stat.mtimeMs),
    isBinary,
    truncated: false,
  };
}

// NUL byte in the first 8 KB — same heuristic git/grep use for binary detection.
function looksBinary(buf: Buffer): boolean {
  const n = Math.min(buf.length, 8192);
  for (let i = 0; i < n; i++) {
    if (buf[i] === 0) return true;
  }
  return false;
}
