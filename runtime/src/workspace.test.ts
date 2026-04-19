import { after, before, describe, it } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

// Must set WORKSPACE_ROOT before importing the modules under test — the
// constants module reads it at import time.
const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "aviary-ws-"));
process.env.WORKSPACE_ROOT = tmpRoot;

const { WorkspaceError, listTree, readFile } = await import("./workspace.js");

function sharedDir(sid: string): string {
  return path.join(tmpRoot, "sessions", sid, "shared");
}

function agentClaudeDir(sid: string, aid: string): string {
  return path.join(tmpRoot, "sessions", sid, "agents", aid, ".claude");
}

function agentVenvDir(sid: string, aid: string): string {
  return path.join(tmpRoot, "sessions", sid, "agents", aid, ".venv");
}

function writeShared(sid: string, rel: string, content: string | Buffer): void {
  const abs = path.join(sharedDir(sid), rel);
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, content);
}

after(() => {
  if (fs.existsSync(tmpRoot)) {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

describe("workspace.listTree", () => {
  const sid = "sess-list";
  const aid = "agent-list";

  before(() => {
    fs.mkdirSync(sharedDir(sid), { recursive: true });
    writeShared(sid, "README.md", "hi");
    writeShared(sid, "b-file.txt", "x");
    fs.mkdirSync(path.join(sharedDir(sid), "src"), { recursive: true });
    fs.mkdirSync(path.join(sharedDir(sid), ".claude"), { recursive: true });
    fs.mkdirSync(path.join(sharedDir(sid), ".venv"), { recursive: true });
    fs.mkdirSync(path.join(sharedDir(sid), ".npm"), { recursive: true });
    writeShared(sid, ".gitignore", "node_modules/");
  });

  it("hides every dot-prefix directory by default, keeps dot-prefix files", () => {
    const tree = listTree(sid, aid, "/", false);
    assert.equal(tree.path, "/");
    // Dirs first, then files, case-insensitive locale-aware order (VS Code style).
    assert.deepEqual(
      tree.entries.map((e) => [e.type, e.name]),
      [
        ["dir", "src"],
        ["file", ".gitignore"],
        ["file", "b-file.txt"],
        ["file", "README.md"],
      ],
    );
  });

  it("surfaces every hidden dot-prefix dir with hidden:true when requested", () => {
    const tree = listTree(sid, aid, "/", true);
    const byName = Object.fromEntries(tree.entries.map((e) => [e.name, e]));
    assert.equal(byName[".claude"]?.hidden, true);
    assert.equal(byName[".venv"]?.hidden, true);
    assert.equal(byName[".npm"]?.hidden, true);
    assert.equal(byName[".gitignore"]?.hidden, undefined);
  });

  it("lists nested directories", () => {
    writeShared(sid, "src/app.ts", "console.log('hi');");
    const tree = listTree(sid, aid, "/src", false);
    assert.equal(tree.path, "/src");
    assert.deepEqual(
      tree.entries.map((e) => e.name),
      ["app.ts"],
    );
  });

  it("auto-creates the session base dir so fresh sessions don't 404", () => {
    const freshSid = "sess-fresh";
    const tree = listTree(freshSid, aid, "/", false);
    assert.deepEqual(tree.entries, []);
    assert.ok(fs.existsSync(sharedDir(freshSid)));
  });

  it("rejects path traversal", () => {
    assert.throws(
      () => listTree(sid, aid, "../../etc", false),
      (err: unknown) => err instanceof WorkspaceError && err.code === "invalid_path",
    );
  });

  it("404s for a non-existent directory under the session", () => {
    assert.throws(
      () => listTree(sid, aid, "/does-not-exist", false),
      (err: unknown) => err instanceof WorkspaceError && err.code === "not_found",
    );
  });

  it("refuses to traverse symlinks", () => {
    const linkSid = "sess-symlink";
    fs.mkdirSync(sharedDir(linkSid), { recursive: true });
    const outside = fs.mkdtempSync(path.join(os.tmpdir(), "aviary-ws-outside-"));
    try {
      fs.symlinkSync(outside, path.join(sharedDir(linkSid), "escape"));
      assert.throws(
        () => listTree(linkSid, aid, "/escape", false),
        (err: unknown) => err instanceof WorkspaceError && err.code === "invalid_path",
      );
    } finally {
      fs.rmSync(outside, { recursive: true, force: true });
    }
  });
});

describe("workspace .claude/.venv redirect", () => {
  const sid = "sess-redirect";
  const aid = "agent-redirect";

  before(() => {
    // Shared has an empty `.claude` mount point like real pod state —
    // browsing the shared path should show nothing; the redirect is what
    // makes content visible.
    fs.mkdirSync(path.join(sharedDir(sid), ".claude"), { recursive: true });

    const claudeReal = agentClaudeDir(sid, aid);
    fs.mkdirSync(path.join(claudeReal, "projects"), { recursive: true });
    fs.writeFileSync(path.join(claudeReal, "settings.json"), "{}");

    const venvReal = agentVenvDir(sid, aid);
    fs.mkdirSync(path.join(venvReal, "bin"), { recursive: true });
    fs.writeFileSync(path.join(venvReal, "pyvenv.cfg"), "home = /usr");
  });

  it("redirects /.claude listing to the per-agent dir", () => {
    const tree = listTree(sid, aid, "/.claude", true);
    assert.equal(tree.path, "/.claude");
    const names = tree.entries.map((e) => e.name).sort();
    assert.deepEqual(names, ["projects", "settings.json"]);
  });

  it("redirects /.venv listing to the per-agent dir", () => {
    const tree = listTree(sid, aid, "/.venv", true);
    assert.equal(tree.path, "/.venv");
    const names = tree.entries.map((e) => e.name).sort();
    assert.deepEqual(names, ["bin", "pyvenv.cfg"]);
  });

  it("keeps the /.claude prefix on nested path reads", () => {
    const out = readFile(sid, aid, "/.claude/settings.json");
    assert.equal(out.path, "/.claude/settings.json");
    assert.equal(out.content, "{}");
  });

  it("rejects /.claude traversal that would escape per-agent dir", () => {
    assert.throws(
      () => listTree(sid, aid, "/.claude/../../../etc", true),
      (err: unknown) => err instanceof WorkspaceError && err.code === "invalid_path",
    );
  });

  it("requires agent_id when the path targets .claude", () => {
    assert.throws(
      () => listTree(sid, null, "/.claude", true),
      (err: unknown) => err instanceof WorkspaceError && err.code === "invalid_path",
    );
  });

  it("requires agent_id when the path targets .venv", () => {
    assert.throws(
      () => readFile(sid, null, "/.venv/pyvenv.cfg"),
      (err: unknown) => err instanceof WorkspaceError && err.code === "invalid_path",
    );
  });

  it("still serves root listings when agent_id is null", () => {
    const tree = listTree(sid, null, "/", false);
    assert.ok(tree.entries.every((e) => !e.name.startsWith(".")));
  });
});

describe("workspace.readFile", () => {
  const sid = "sess-read";
  const aid = "agent-read";

  before(() => {
    fs.mkdirSync(sharedDir(sid), { recursive: true });
  });

  it("reads a text file", () => {
    writeShared(sid, "hello.txt", "hello world");
    const out = readFile(sid, aid, "/hello.txt");
    assert.equal(out.content, "hello world");
    assert.equal(out.isBinary, false);
    assert.equal(out.size, 11);
    assert.equal(out.encoding, "utf8");
  });

  it("flags binary files without returning content", () => {
    writeShared(sid, "bin.dat", Buffer.from([0x00, 0x01, 0x02, 0x03]));
    const out = readFile(sid, aid, "/bin.dat");
    assert.equal(out.isBinary, true);
    assert.equal(out.content, "");
  });

  it("rejects files over WORKSPACE_MAX_FILE_BYTES", () => {
    const prev = process.env.WORKSPACE_MAX_FILE_BYTES;
    process.env.WORKSPACE_MAX_FILE_BYTES = "8";
    try {
      writeShared(sid, "big.txt", "1234567890");
      assert.throws(
        () => readFile(sid, aid, "/big.txt"),
        (err: unknown) => err instanceof WorkspaceError && err.code === "too_large",
      );
    } finally {
      if (prev === undefined) delete process.env.WORKSPACE_MAX_FILE_BYTES;
      else process.env.WORKSPACE_MAX_FILE_BYTES = prev;
    }
  });

  it("rejects a directory", () => {
    fs.mkdirSync(path.join(sharedDir(sid), "a-dir"), { recursive: true });
    assert.throws(
      () => readFile(sid, aid, "/a-dir"),
      (err: unknown) => err instanceof WorkspaceError && err.code === "not_a_file",
    );
  });

  it("rejects traversal", () => {
    assert.throws(
      () => readFile(sid, aid, "../../etc/passwd"),
      (err: unknown) => err instanceof WorkspaceError && err.code === "invalid_path",
    );
  });
});
