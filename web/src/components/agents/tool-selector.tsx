"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { McpServerInfo, McpToolInfo } from "@/types";

interface ToolSelectorProps {
  selectedToolIds: string[];
  onChange: (toolIds: string[]) => void;
  open: boolean;
  onClose: () => void;
}

export function ToolSelector({ selectedToolIds, onChange, open, onClose }: ToolSelectorProps) {
  const [servers, setServers] = useState<McpServerInfo[]>([]);
  const [serverTools, setServerTools] = useState<Record<string, McpToolInfo[]>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<McpToolInfo[] | null>(null);
  const [expandedServer, setExpandedServer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const selected = new Set(selectedToolIds);

  // Fetch servers on open
  useEffect(() => {
    if (!open) return;
    (async () => {
      setLoading(true);
      try {
        const data = await apiFetch<McpServerInfo[]>("/mcp/servers");
        setServers(data);
      } catch {
        setServers([]);
      } finally {
        setLoading(false);
      }
    })();
  }, [open]);

  // Fetch tools when expanding a server
  const loadServerTools = useCallback(async (serverId: string) => {
    if (serverTools[serverId]) return;
    try {
      const tools = await apiFetch<McpToolInfo[]>(`/mcp/servers/${serverId}/tools`);
      setServerTools((prev) => ({ ...prev, [serverId]: tools }));
    } catch {
      setServerTools((prev) => ({ ...prev, [serverId]: [] }));
    }
  }, [serverTools]);

  const handleToggle = (toolId: string) => {
    const next = new Set(selected);
    if (next.has(toolId)) {
      next.delete(toolId);
    } else {
      next.add(toolId);
    }
    onChange(Array.from(next));
  };

  // Search
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const results = await apiFetch<McpToolInfo[]>(
          `/mcp/tools/search?q=${encodeURIComponent(searchQuery)}`
        );
        setSearchResults(results);
      } catch {
        setSearchResults([]);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  if (!open) return null;

  const displayTools = searchResults ?? [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-2xl max-h-[80vh] rounded-2xl border border-border bg-background shadow-xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/60 px-6 py-4">
          <h2 className="text-sm font-semibold">Browse Tools</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-lg">&times;</button>
        </div>

        {/* Search */}
        <div className="px-6 py-3 border-b border-border/40">
          <Input
            placeholder="Search tools by name or description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {loading && <p className="text-sm text-muted-foreground">Loading...</p>}

          {/* Search results mode */}
          {searchResults !== null ? (
            displayTools.length === 0 ? (
              <p className="text-sm text-muted-foreground">No tools found.</p>
            ) : (
              <div className="space-y-2">
                {displayTools.map((tool) => (
                  <ToolRow key={tool.id} tool={tool} checked={selected.has(tool.id)} onToggle={handleToggle} />
                ))}
              </div>
            )
          ) : (
            /* Server browse mode */
            servers.map((srv) => (
              <div key={srv.id} className="rounded-lg border border-border/50">
                <button
                  className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-muted/30 rounded-lg"
                  onClick={() => {
                    const next = expandedServer === srv.id ? null : srv.id;
                    setExpandedServer(next);
                    if (next) loadServerTools(next);
                  }}
                >
                  <div>
                    <span className="text-sm font-medium">{srv.name}</span>
                    {srv.description && (
                      <span className="ml-2 text-xs text-muted-foreground">{srv.description}</span>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">{srv.tool_count} tools</span>
                </button>
                {expandedServer === srv.id && (
                  <div className="border-t border-border/30 px-4 py-2 space-y-1">
                    {(serverTools[srv.id] ?? []).length === 0 ? (
                      <p className="text-xs text-muted-foreground py-2">Loading tools...</p>
                    ) : (
                      (serverTools[srv.id] ?? []).map((tool) => (
                        <ToolRow key={tool.id} tool={tool} checked={selected.has(tool.id)} onToggle={handleToggle} />
                      ))
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border/60 px-6 py-4">
          <span className="text-xs text-muted-foreground">{selected.size} tool(s) selected</span>
          <Button size="sm" onClick={onClose}>Done</Button>
        </div>
      </div>
    </div>
  );
}

function ToolRow({ tool, checked, onToggle }: { tool: McpToolInfo; checked: boolean; onToggle: (id: string) => void }) {
  return (
    <label className="flex items-start gap-3 px-3 py-2 rounded-lg hover:bg-muted/20 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={() => onToggle(tool.id)}
        className="mt-0.5 rounded border-border"
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate">{tool.qualified_name}</span>
        </div>
        {tool.description && (
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{tool.description}</p>
        )}
      </div>
    </label>
  );
}
