"use client";

import { Loader2 } from "@/components/icons";
import type { WorkspaceTreeState } from "../hooks/use-workspace-tree";
import { TreeChildren } from "./tree-node";

interface FileTreeProps {
  tree: WorkspaceTreeState;
  activeFilePath: string | null;
  onFileClick: (path: string) => void;
}

export function FileTree({ tree, activeFilePath, onFileClick }: FileTreeProps) {
  const root = tree.nodes.get(tree.rootPath);

  if (!root?.loaded && root?.loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 type-caption text-fg-muted">
        <Loader2 size={14} className="animate-spin" strokeWidth={2} />
        Loading…
      </div>
    );
  }

  if (root?.error) {
    return (
      <div className="flex h-full items-center justify-center px-4 type-caption text-danger/80 text-center">
        {root.error}
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto py-1">
      <TreeChildren
        parentPath={tree.rootPath}
        depth={0}
        tree={tree}
        activeFilePath={activeFilePath}
        onFileClick={onFileClick}
      />
    </div>
  );
}
