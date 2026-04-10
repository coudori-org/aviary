"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatTokens } from "@/lib/utils/format";
import type { Agent, McpToolBinding } from "@/types";

interface AgentConfigGridProps {
  agent: Agent;
  mcpTools: McpToolBinding[];
}

/**
 * AgentConfigGrid — read-only configuration view for an agent.
 *
 * Four cards in a 2-column grid:
 *   1. Model         — backend, model id, max tokens
 *   2. Identity      — slug, visibility, status
 *   3. Instruction   — full-width, system instruction
 *   4. Tools         — full-width, built-in + MCP tools
 *
 * Lives in a separate component so the detail page stays a thin
 * assembler of hero + recent sessions + this grid.
 */
export function AgentConfigGrid({ agent, mcpTools }: AgentConfigGridProps) {
  return (
    <section>
      <h2 className="mb-3 type-button text-fg-primary">Configuration</h2>
      <div className="grid gap-4 md:grid-cols-2">
        <Card variant="elevated">
          <CardHeader>
            <CardTitle>Model</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <InfoRow label="Backend" value={agent.model_config.backend} />
            <InfoRow label="Model" value={agent.model_config.model} mono />
            {agent.model_config.max_output_tokens != null && (
              <InfoRow
                label="Max Output Tokens"
                value={formatTokens(agent.model_config.max_output_tokens)}
              />
            )}
          </CardContent>
        </Card>

        <Card variant="elevated">
          <CardHeader>
            <CardTitle>Identity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <InfoRow label="Identifier" value={agent.slug} mono />
            <InfoRow label="Visibility" value={agent.visibility} capitalize />
            <InfoRow label="Status" value={agent.status} capitalize />
          </CardContent>
        </Card>

        <Card variant="elevated" className="md:col-span-2">
          <CardHeader>
            <CardTitle>System Instruction</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-md bg-canvas p-4 type-body-tight text-fg-secondary">
              <pre className="whitespace-pre-wrap font-sans">{agent.instruction}</pre>
            </div>
          </CardContent>
        </Card>

        <Card variant="elevated" className="md:col-span-2">
          <CardHeader>
            <CardTitle>Tools</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {agent.tools.length > 0 && (
              <div>
                <p className="type-caption text-fg-muted mb-2">Built-in</p>
                <div className="flex flex-wrap gap-2">
                  {agent.tools.map((tool) => (
                    <Badge key={tool} variant="muted">
                      {tool}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            {mcpTools.length > 0 && (
              <div>
                <p className="type-caption text-fg-muted mb-2">MCP Tools</p>
                <div className="flex flex-wrap gap-2">
                  {mcpTools.map((b) => (
                    <Badge key={b.id} variant="info" title={b.tool.description || ""}>
                      {b.tool.qualified_name}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            {agent.tools.length === 0 && mcpTools.length === 0 && (
              <p className="type-caption text-fg-muted">No tools configured</p>
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

function InfoRow({
  label,
  value,
  mono,
  capitalize: cap,
}: {
  label: string;
  value: string;
  mono?: boolean;
  capitalize?: boolean;
}) {
  return (
    <div className="flex items-center justify-between type-body-tight">
      <span className="text-fg-muted">{label}</span>
      <span
        className={`text-fg-secondary ${mono ? "font-mono type-code-sm" : ""} ${cap ? "capitalize" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}
