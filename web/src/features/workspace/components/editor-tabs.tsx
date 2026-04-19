"use client";

import { PanelRightClose, X } from "@/components/icons";
import { cn } from "@/lib/utils";
import type { EditorTab } from "../hooks/use-workspace-editor";
import { basename } from "../lib/paths";

interface EditorTabsProps {
  tabs: EditorTab[];
  activeTabPath: string | null;
  onActivate: (path: string) => void;
  onClose: (path: string) => void;
  onCollapseEditor: () => void;
}

export function EditorTabs({ tabs, activeTabPath, onActivate, onClose, onCollapseEditor }: EditorTabsProps) {
  return (
    <div className="flex shrink-0 items-stretch border-b border-white/[0.06] bg-base">
      <div className="flex min-w-0 flex-1 items-stretch overflow-x-auto">
      {tabs.map((tab) => {
        const active = tab.path === activeTabPath;
        const dirty = tab.draft !== null;
        return (
          <div
            key={tab.path}
            role="tab"
            aria-selected={active}
            tabIndex={0}
            onClick={() => onActivate(tab.path)}
            onAuxClick={(e) => {
              if (e.button === 1) {
                e.preventDefault();
                onClose(tab.path);
              }
            }}
            className={cn(
              "group flex min-w-0 cursor-pointer items-center gap-1.5 border-r border-white/[0.06] px-3 py-1.5 type-caption transition-colors",
              active
                ? "bg-canvas text-fg-primary"
                : "text-fg-muted hover:bg-raised hover:text-fg-primary",
            )}
            title={tab.path}
          >
            <span className="truncate max-w-[160px] font-mono">{basename(tab.path)}</span>
            {dirty && (
              <span
                aria-label="Unsaved changes"
                className="h-1.5 w-1.5 shrink-0 rounded-full bg-fg-primary"
              />
            )}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onClose(tab.path);
              }}
              aria-label={`Close ${basename(tab.path)}`}
              className="flex h-4 w-4 shrink-0 items-center justify-center rounded-xs text-fg-muted hover:bg-white/10 hover:text-fg-primary"
            >
              <X size={10} strokeWidth={2.5} />
            </button>
          </div>
        );
      })}
      </div>
      <button
        type="button"
        onClick={onCollapseEditor}
        aria-label="Collapse editor"
        title="Collapse editor"
        className="flex h-auto w-8 shrink-0 items-center justify-center border-l border-white/[0.06] text-fg-muted hover:bg-raised hover:text-fg-primary"
      >
        <PanelRightClose size={14} strokeWidth={2} />
      </button>
    </div>
  );
}
