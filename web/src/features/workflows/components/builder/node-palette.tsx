"use client";

import { NODE_REGISTRY, NODE_CATEGORIES } from "@/features/workflows/lib/node-registry";
import type { NodeType } from "@/features/workflows/lib/types";
import { cn } from "@/lib/utils";

interface NodePaletteProps {
  onAddNode: (type: NodeType) => void;
}

export function NodePalette({ onAddNode }: NodePaletteProps) {
  const onDragStart = (e: React.DragEvent, type: NodeType) => {
    e.dataTransfer.setData("application/workflow-node-type", type);
    e.dataTransfer.effectAllowed = "move";
  };

  return (
    <div className="w-52 shrink-0 overflow-y-auto border-r border-white/[0.06] bg-canvas p-3">
      <h2 className="mb-3 type-caption-bold text-fg-muted uppercase tracking-wider">Nodes</h2>
      {NODE_CATEGORIES.map(({ key, label }) => {
        const items = NODE_REGISTRY.filter((n) => n.category === key);
        if (items.length === 0) return null;
        return (
          <div key={key} className="mb-4">
            <p className="mb-1.5 type-caption text-fg-disabled">{label}</p>
            <div className="flex flex-col gap-1">
              {items.map((def) => (
                <button
                  key={def.type}
                  type="button"
                  draggable
                  onDragStart={(e) => onDragStart(e, def.type)}
                  onClick={() => onAddNode(def.type)}
                  className={cn(
                    "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-left",
                    "type-caption text-fg-secondary",
                    "hover:bg-raised hover:text-fg-primary transition-colors",
                    "cursor-grab active:cursor-grabbing",
                  )}
                >
                  {def.label}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
