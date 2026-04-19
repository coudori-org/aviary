"use client";

import { memo } from "react";
import { ChevronRight, Folder, FolderOpen, Loader2 } from "@/components/icons";
import { cn } from "@/lib/utils";
import { fileIconFor } from "../lib/file-icons";
import type { TreeEntry } from "../lib/workspace-api";
import type { WorkspaceTreeState } from "../hooks/use-workspace-tree";

interface TreeNodeProps {
  entry: TreeEntry;
  path: string;
  depth: number;
  tree: WorkspaceTreeState;
  activeFilePath: string | null;
  onFileClick: (path: string) => void;
}

const INDENT_BASE_PX = 6;
const INDENT_STEP_PX = 14;

export const TreeNode = memo(function TreeNode({
  entry, path, depth, tree, activeFilePath, onFileClick,
}: TreeNodeProps) {
  const isDir = entry.type === "dir";
  const isExpanded = isDir && tree.expanded.has(path);
  const node = tree.nodes.get(path);
  const isLoading = isDir && node?.loading === true;
  const isActive = !isDir && activeFilePath === path;
  const FileIcon = isDir ? null : fileIconFor(entry.name);
  const paddingLeft = INDENT_BASE_PX + depth * INDENT_STEP_PX;

  const handleClick = () => {
    if (isDir) tree.toggle(path);
    else onFileClick(path);
  };

  return (
    <>
      <button
        type="button"
        onClick={handleClick}
        className={cn(
          "group flex w-full items-center gap-1 py-0.5 pr-2 text-left type-caption transition-colors",
          isActive ? "bg-info/15 text-fg-primary" : "text-fg-muted hover:bg-raised hover:text-fg-primary",
          entry.hidden && !isActive && "opacity-60",
        )}
        style={{ paddingLeft }}
        title={entry.name}
      >
        {isDir ? (
          <>
            <ChevronRight
              size={11}
              strokeWidth={2}
              className={cn(
                "shrink-0 transition-transform",
                isExpanded && "rotate-90",
              )}
            />
            {isExpanded ? (
              <FolderOpen size={13} strokeWidth={1.75} className="shrink-0 text-info/80" />
            ) : (
              <Folder size={13} strokeWidth={1.75} className="shrink-0 text-info/70" />
            )}
          </>
        ) : (
          <>
            <span className="w-[11px] shrink-0" aria-hidden />
            {FileIcon && <FileIcon size={13} strokeWidth={1.75} className="shrink-0" />}
          </>
        )}
        <span className="truncate">{entry.name}</span>
        {isLoading && (
          <Loader2 size={11} strokeWidth={2} className="ml-auto shrink-0 animate-spin text-fg-disabled" />
        )}
      </button>

      {isDir && isExpanded && node?.loaded && (
        <TreeChildren parentPath={path} depth={depth + 1} tree={tree} activeFilePath={activeFilePath} onFileClick={onFileClick} />
      )}
      {isDir && isExpanded && node?.error && (
        <div
          className="py-0.5 type-caption text-danger/70"
          style={{ paddingLeft: INDENT_BASE_PX + (depth + 1) * INDENT_STEP_PX }}
        >
          {node.error}
        </div>
      )}
    </>
  );
});

interface TreeChildrenProps {
  parentPath: string;
  depth: number;
  tree: WorkspaceTreeState;
  activeFilePath: string | null;
  onFileClick: (path: string) => void;
}

export function TreeChildren({ parentPath, depth, tree, activeFilePath, onFileClick }: TreeChildrenProps) {
  const node = tree.nodes.get(parentPath);
  if (!node?.loaded) return null;
  if (node.entries.length === 0) {
    return (
      <div
        className="py-0.5 type-caption text-fg-disabled italic"
        style={{ paddingLeft: INDENT_BASE_PX + depth * INDENT_STEP_PX }}
      >
        empty
      </div>
    );
  }
  return (
    <>
      {node.entries.map((entry) => (
        <TreeNode
          key={`${parentPath}:${entry.name}`}
          entry={entry}
          path={tree.joinPath(parentPath, entry.name)}
          depth={depth}
          tree={tree}
          activeFilePath={activeFilePath}
          onFileClick={onFileClick}
        />
      ))}
    </>
  );
}
