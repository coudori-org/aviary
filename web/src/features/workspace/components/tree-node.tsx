"use client";

import { memo } from "react";
import { ChevronRight, Folder, FolderOpen, Loader2 } from "@/components/icons";
import { cn } from "@/lib/utils";
import { fileIconFor } from "../lib/file-icons";
import type { TreeEntry } from "../lib/workspace-api";
import type { WorkspaceTreeState } from "../hooks/use-workspace-tree";
import { RenameInput } from "./rename-input";

export type PendingNew = { parent: string; mode: "file" | "dir" } | null;

export interface TreeInteractions {
  activeFilePath: string | null;
  onFileClick: (path: string) => void;
  onFileDoubleClick: (path: string) => void;
  onContextMenu: (e: React.MouseEvent, payload: {
    path: string;
    entry: TreeEntry | null; // null for root
  }) => void;
  renamingPath: string | null;
  onSubmitRename: (path: string, newName: string) => void;
  onCancelRename: () => void;
  pendingNew: PendingNew;
  onSubmitNew: (parent: string, mode: "file" | "dir", name: string) => void;
  onCancelNew: () => void;
}

interface TreeNodeProps {
  entry: TreeEntry;
  path: string;
  depth: number;
  tree: WorkspaceTreeState;
  ui: TreeInteractions;
}

const INDENT_BASE_PX = 6;
const INDENT_STEP_PX = 14;

export const TreeNode = memo(function TreeNode({
  entry, path, depth, tree, ui,
}: TreeNodeProps) {
  const isDir = entry.type === "dir";
  const isExpanded = isDir && tree.expanded.has(path);
  const node = tree.nodes.get(path);
  const isLoading = isDir && node?.loading === true;
  const isActive = !isDir && ui.activeFilePath === path;
  const FileIcon = isDir ? null : fileIconFor(entry.name);
  const paddingLeft = INDENT_BASE_PX + depth * INDENT_STEP_PX;

  const handleClick = () => {
    if (isDir) tree.toggle(path);
    else ui.onFileClick(path);
  };

  const isRenaming = ui.renamingPath === path;

  if (isRenaming) {
    return (
      <RenameInput
        initialValue={entry.name}
        depth={depth}
        onSubmit={(v) => ui.onSubmitRename(path, v)}
        onCancel={ui.onCancelRename}
      />
    );
  }

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        onClick={handleClick}
        onDoubleClick={() => {
          if (!isDir) ui.onFileDoubleClick(path);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            handleClick();
          }
        }}
        onContextMenu={(e) => {
          e.preventDefault();
          ui.onContextMenu(e, { path, entry });
        }}
        className={cn(
          "group flex w-full items-center gap-1 py-0.5 pr-2 text-left type-caption transition-colors cursor-pointer",
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
      </div>

      {isDir && isExpanded && node?.loaded && (
        <TreeChildren parentPath={path} depth={depth + 1} tree={tree} ui={ui} />
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
  ui: TreeInteractions;
}

export function TreeChildren({ parentPath, depth, tree, ui }: TreeChildrenProps) {
  const node = tree.nodes.get(parentPath);
  if (!node?.loaded) return null;

  const pendingHere =
    ui.pendingNew && ui.pendingNew.parent === parentPath ? ui.pendingNew : null;

  return (
    <>
      {pendingHere && (
        <RenameInput
          key="__pending_new__"
          initialValue=""
          placeholder={pendingHere.mode === "dir" ? "new folder name" : "new file name"}
          depth={depth}
          onSubmit={(v) => ui.onSubmitNew(parentPath, pendingHere.mode, v)}
          onCancel={ui.onCancelNew}
        />
      )}
      {!pendingHere && node.entries.length === 0 && (
        <div
          className="py-0.5 type-caption text-fg-disabled italic"
          style={{ paddingLeft: INDENT_BASE_PX + depth * INDENT_STEP_PX }}
        >
          empty
        </div>
      )}
      {node.entries.map((entry) => (
        <TreeNode
          key={`${parentPath}:${entry.name}`}
          entry={entry}
          path={tree.joinPath(parentPath, entry.name)}
          depth={depth}
          tree={tree}
          ui={ui}
        />
      ))}
    </>
  );
}
