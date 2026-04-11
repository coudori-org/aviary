"use client";

import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FormSection } from "./form-section";
import { ToolChip } from "./tool-chip";
import { ToolSelector } from "@/features/agents/components/tool-selector/tool-selector";
import { ToolDetailsSheet } from "@/features/agents/components/tool-selector/tool-details-sheet";
import type { McpToolInfo } from "@/types";
import type { AgentFormData } from "./types";

interface ToolsSectionProps {
  data: AgentFormData;
  setField: <K extends keyof AgentFormData>(key: K, value: AgentFormData[K]) => void;
  toolInfoMap: Map<string, McpToolInfo>;
  setToolInfoMap: (map: Map<string, McpToolInfo>) => void;
}

export function ToolsSection({ data, setField, toolInfoMap, setToolInfoMap }: ToolsSectionProps) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [detailsTool, setDetailsTool] = useState<McpToolInfo | null>(null);

  const removeTool = useCallback(
    (id: string) => {
      setField("mcp_tool_ids", data.mcp_tool_ids.filter((t) => t !== id));
    },
    [data.mcp_tool_ids, setField],
  );

  return (
    <FormSection title="Tools & Integrations" description="Connect external tools via MCP servers">
      <Card variant="standard" className="p-5 space-y-4">
        {data.mcp_tool_ids.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {data.mcp_tool_ids.map((id) => (
              <ToolChip
                key={id}
                id={id}
                info={toolInfoMap.get(id)}
                onRemove={removeTool}
                onShowDetails={setDetailsTool}
              />
            ))}
          </div>
        ) : (
          <p className="type-caption text-fg-muted">No tools connected yet.</p>
        )}

        <Button type="button" variant="secondary" size="sm" onClick={() => setPickerOpen(true)}>
          Browse Tools
        </Button>
      </Card>

      <ToolSelector
        selectedToolIds={data.mcp_tool_ids}
        onChange={(ids, map) => {
          setField("mcp_tool_ids", ids);
          if (map) setToolInfoMap(map);
        }}
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
      />

      <ToolDetailsSheet tool={detailsTool} onClose={() => setDetailsTool(null)} />
    </FormSection>
  );
}
