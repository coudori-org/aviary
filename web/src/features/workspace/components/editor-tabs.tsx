"use client";

import {
  SortableContext,
  horizontalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { PanelRightClose, X } from "@/components/icons";
import { cn } from "@/lib/utils";
import type { EditorTab } from "../hooks/use-workspace-editor";
import { basename, sandboxPath } from "../lib/paths";

export function tabSortId(paneId: string, path: string): string {
  return `${paneId}::${path}`;
}

export function parseTabSortId(id: string): { paneId: string; path: string } | null {
  const sep = id.indexOf("::");
  if (sep === -1) return null;
  return { paneId: id.slice(0, sep), path: id.slice(sep + 2) };
}

interface EditorTabsProps {
  paneId: string;
  tabs: EditorTab[];
  activeTabPath: string | null;
  onActivate: (path: string) => void;
  onClose: (path: string) => void;
  onPin: (path: string) => void;
  onContextMenu: (e: React.MouseEvent, path: string) => void;
  onCollapseEditor?: () => void;
}

export function EditorTabs({
  paneId, tabs, activeTabPath, onActivate, onClose, onPin, onContextMenu, onCollapseEditor,
}: EditorTabsProps) {
  const items = tabs.map((t) => tabSortId(paneId, t.path));
  return (
    <div className="flex w-full min-w-0 shrink-0 items-stretch border-b border-border-subtle bg-sunk">
      <div className="flex min-w-0 flex-1 items-stretch overflow-x-auto">
        <SortableContext items={items} strategy={horizontalListSortingStrategy}>
          {tabs.map((tab) => (
            <SortableTab
              key={tab.path}
              paneId={paneId}
              tab={tab}
              active={tab.path === activeTabPath}
              onActivate={onActivate}
              onClose={onClose}
              onPin={onPin}
              onContextMenu={onContextMenu}
            />
          ))}
        </SortableContext>
      </div>
      {onCollapseEditor && (
        <button
          type="button"
          onClick={onCollapseEditor}
          aria-label="Collapse editor"
          title="Collapse editor"
          className="flex h-auto w-8 shrink-0 items-center justify-center border-l border-border-subtle text-fg-muted hover:bg-raised hover:text-fg-primary"
        >
          <PanelRightClose size={14} strokeWidth={2} />
        </button>
      )}
    </div>
  );
}

interface SortableTabProps {
  paneId: string;
  tab: EditorTab;
  active: boolean;
  onActivate: (path: string) => void;
  onClose: (path: string) => void;
  onPin: (path: string) => void;
  onContextMenu: (e: React.MouseEvent, path: string) => void;
}

/** Visual-only floating clone used inside dnd-kit's DragOverlay so the drag
 *  preview can leave its pane's overflow-clipped tab bar. */
export function TabGhost({ tab }: { tab: EditorTab }) {
  const dirty = tab.draft !== null;
  const preview = !tab.pinned;
  return (
    <div
      className={cn(
        "flex min-w-0 cursor-grabbing items-center gap-1.5 rounded-xs border border-border",
        "bg-canvas px-3 py-1.5 type-caption text-fg-primary shadow-xl",
      )}
    >
      <span
        className={cn(
          "truncate max-w-[200px] font-mono",
          preview && "italic",
        )}
      >
        {basename(tab.path)}
      </span>
      {dirty && (
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-fg-primary" />
      )}
    </div>
  );
}

function SortableTab({ paneId, tab, active, onActivate, onClose, onPin, onContextMenu }: SortableTabProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: tabSortId(paneId, tab.path),
  });
  const dirty = tab.draft !== null;
  const preview = !tab.pinned;
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 10 : undefined,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      role="tab"
      aria-selected={active}
      tabIndex={0}
      onClick={() => onActivate(tab.path)}
      onDoubleClick={() => onPin(tab.path)}
      onContextMenu={(e) => {
        e.preventDefault();
        onContextMenu(e, tab.path);
      }}
      onAuxClick={(e) => {
        if (e.button === 1) {
          e.preventDefault();
          onClose(tab.path);
        }
      }}
      onDragStart={(e) => e.preventDefault()}
      className={cn(
        "group flex min-w-0 cursor-pointer items-center gap-1.5 border-r border-border-subtle px-3 py-1.5 type-caption transition-colors",
        active
          ? "bg-canvas text-fg-primary"
          : "text-fg-muted hover:bg-raised hover:text-fg-primary",
        isDragging && "opacity-50",
      )}
      title={sandboxPath(tab.path)}
    >
      <span
        className={cn(
          "truncate max-w-[160px] font-mono",
          preview && "italic",
        )}
      >
        {basename(tab.path)}
      </span>
      {dirty && (
        <span
          aria-label="Unsaved changes"
          className="h-1.5 w-1.5 shrink-0 rounded-full bg-fg-primary"
        />
      )}
      <button
        type="button"
        onPointerDown={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.stopPropagation();
          onClose(tab.path);
        }}
        aria-label={`Close ${basename(tab.path)}`}
        className="flex h-4 w-4 shrink-0 items-center justify-center rounded-xs text-fg-muted hover:bg-active hover:text-fg-primary"
      >
        <X size={10} strokeWidth={2.5} />
      </button>
    </div>
  );
}
