"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  Download,
  Eye,
  FilePlus,
  FolderPlus,
  Pencil,
  Trash2,
  Upload,
} from "@/components/icons";
import { cn } from "@/lib/utils";

export interface ContextMenuItem {
  id: string;
  label: string;
  icon?: "open" | "new-file" | "new-folder" | "rename" | "delete" | "upload" | "download";
  danger?: boolean;
  onSelect: () => void;
}

interface WorkspaceContextMenuProps {
  x: number;
  y: number;
  items: ContextMenuItem[];
  onClose: () => void;
}

export function WorkspaceContextMenu({ x, y, items, onClose }: WorkspaceContextMenuProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState({ left: x, top: y });

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left = x;
    let top = y;
    if (left + rect.width > vw) left = Math.max(0, vw - rect.width - 4);
    if (top + rect.height > vh) top = Math.max(0, vh - rect.height - 4);
    setPos({ left, top });
  }, [x, y]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div
      ref={ref}
      role="menu"
      className="fixed z-50 min-w-[180px] rounded-md border border-border bg-popover py-1 shadow-xl"
      style={{ left: pos.left, top: pos.top }}
    >
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="menuitem"
          onClick={() => {
            item.onSelect();
            onClose();
          }}
          className={cn(
            "flex w-full items-center gap-2 px-3 py-1.5 text-left type-caption transition-colors",
            item.danger
              ? "text-danger hover:bg-danger/15"
              : "text-fg-primary hover:bg-active",
          )}
        >
          <MenuIcon kind={item.icon} />
          <span className="truncate">{item.label}</span>
        </button>
      ))}
    </div>
  );
}

function MenuIcon({ kind }: { kind?: ContextMenuItem["icon"] }) {
  switch (kind) {
    case "open":
      return <Eye size={12} strokeWidth={2} />;
    case "new-file":
      return <FilePlus size={12} strokeWidth={2} />;
    case "new-folder":
      return <FolderPlus size={12} strokeWidth={2} />;
    case "rename":
      return <Pencil size={12} strokeWidth={2} />;
    case "delete":
      return <Trash2 size={12} strokeWidth={2} />;
    case "upload":
      return <Upload size={12} strokeWidth={2} />;
    case "download":
      return <Download size={12} strokeWidth={2} />;
    default:
      return <span className="h-3 w-3" />;
  }
}
