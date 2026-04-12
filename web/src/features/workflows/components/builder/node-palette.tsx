"use client";

import { Play, Globe, Bot, GitBranch, Layers, Filter, FileText } from "@/components/icons";
import { NODE_REGISTRY, NODE_CATEGORIES } from "@/features/workflows/lib/node-registry";
import type { NodeType } from "@/features/workflows/lib/types";
import { cn } from "@/lib/utils";

interface NodePaletteProps {
  onAddNode: (type: NodeType) => void;
}

const CATEGORY_COLORS: Record<string, string> = {
  trigger: "#5fc992",
  agent: "#55b3ff",
  control: "#ffbc33",
  transform: "#e085d0",
};

const NODE_ICONS: Record<string, React.ReactNode> = {
  manual_trigger: <Play size={13} strokeWidth={2} />,
  webhook_trigger: <Globe size={13} strokeWidth={1.75} />,
  agent_step: <Bot size={13} strokeWidth={1.75} />,
  condition: <GitBranch size={13} strokeWidth={1.75} />,
  merge: <Layers size={13} strokeWidth={1.75} />,
  payload_parser: <Filter size={13} strokeWidth={1.75} />,
  template: <FileText size={13} strokeWidth={1.75} />,
};

export function NodePalette({ onAddNode }: NodePaletteProps) {
  const onDragStart = (e: React.DragEvent, type: NodeType) => {
    e.dataTransfer.setData("application/workflow-node-type", type);
    e.dataTransfer.effectAllowed = "move";
  };

  return (
    <div className="px-3 py-4">
      {NODE_CATEGORIES.map(({ key, label }) => {
        const items = NODE_REGISTRY.filter((n) => n.category === key);
        if (items.length === 0) return null;
        const color = CATEGORY_COLORS[key] ?? "#888";

        return (
          <div key={key} className="mb-5">
            <p
              className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-widest"
              style={{ color }}
            >
              {label}
            </p>
            <div className="flex flex-col gap-0.5">
              {items.map((def) => (
                <button
                  key={def.type}
                  type="button"
                  draggable
                  onDragStart={(e) => onDragStart(e, def.type)}
                  onClick={() => onAddNode(def.type)}
                  className={cn(
                    "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-left",
                    "text-[13px] text-fg-muted",
                    "hover:bg-white/[0.04] hover:text-fg-primary transition-colors",
                    "cursor-grab active:cursor-grabbing",
                  )}
                >
                  <span style={{ color }} className="shrink-0 opacity-70">
                    {NODE_ICONS[def.type]}
                  </span>
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
