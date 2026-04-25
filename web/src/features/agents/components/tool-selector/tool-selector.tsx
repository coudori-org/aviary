"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Plus, Server, Clock, Layers, X } from "@/components/icons";
import { mcpApi } from "@/features/agents/api/mcp-api";
import { ToolCard } from "./tool-card";
import { ToolDetailsSheet } from "./tool-details-sheet";
import {
  loadRecentToolIds,
  pushRecentToolId,
} from "@/lib/storage/recently-used-tools";
import { cn } from "@/lib/utils";
import type { McpServerInfo, McpToolInfo } from "@/types";

interface ToolSelectorProps {
  selectedToolIds: string[];
  onChange: (toolIds: string[], toolMap: Map<string, McpToolInfo>) => void;
  open: boolean;
  onClose: () => void;
}

/** Category key for the left rail. Either a synthetic bucket or a server id. */
type FilterKey = "all" | "recent" | string;

/**
 * ToolSelector — two-pane MCP tool picker.
 *
 * Left rail: "All", "Recently used", then one row per MCP server with
 * an on-hover `+N` bulk-add button. Right pane: card grid of tools
 * matching the active left-rail selection, or a search-results grid
 * when the user types in the top search box (search ignores the rail
 * selection so it always covers everything).
 */
export function ToolSelector({ selectedToolIds, onChange, open, onClose }: ToolSelectorProps) {
  const [servers, setServers] = useState<McpServerInfo[]>([]);
  const [serverTools, setServerTools] = useState<Record<string, McpToolInfo[]>>({});
  const [allToolInfo, setAllToolInfo] = useState<Map<string, McpToolInfo>>(new Map());
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<McpToolInfo[] | null>(null);
  const [activeFilter, setActiveFilter] = useState<FilterKey>("all");
  const [loadingServers, setLoadingServers] = useState(false);
  const [recentIds, setRecentIds] = useState<string[]>([]);
  const [detailsTool, setDetailsTool] = useState<McpToolInfo | null>(null);
  const selected = new Set(selectedToolIds);

  // Load servers + recent ids on open.
  useEffect(() => {
    if (!open) return;
    setLoadingServers(true);
    mcpApi
      .listServers()
      .then((data) => setServers(data))
      .finally(() => setLoadingServers(false));
    setRecentIds(loadRecentToolIds());
  }, [open]);

  const loadServerTools = useCallback(
    async (serverId: string) => {
      if (serverTools[serverId]) return;
      const tools = await mcpApi.listServerTools(serverId);
      setServerTools((prev) => ({ ...prev, [serverId]: tools }));
      setAllToolInfo((prev) => {
        const next = new Map(prev);
        for (const t of tools) next.set(t.id, t);
        return next;
      });
    },
    [serverTools],
  );

  // Lazy-load tools for whichever server(s) the active filter needs.
  // "all" fans out in parallel; a single-server filter just loads that one.
  useEffect(() => {
    if (!open || servers.length === 0) return;
    if (activeFilter === "all") {
      servers.forEach((s) => void loadServerTools(s.id));
    } else if (activeFilter !== "recent") {
      void loadServerTools(activeFilter);
    }
  }, [activeFilter, servers, open, loadServerTools]);

  // Debounced full-text search — bypasses the rail filter.
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    const timer = setTimeout(async () => {
      const results = await mcpApi.searchTools(searchQuery);
      setSearchResults(results);
      setAllToolInfo((prev) => {
        const next = new Map(prev);
        for (const t of results) next.set(t.id, t);
        return next;
      });
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const updateSelection = useCallback(
    (nextIds: string[]) => onChange(nextIds, allToolInfo),
    [allToolInfo, onChange],
  );

  const handleToggle = useCallback(
    (toolId: string) => {
      const next = new Set(selected);
      if (next.has(toolId)) {
        next.delete(toolId);
      } else {
        next.add(toolId);
        setRecentIds(pushRecentToolId(toolId));
      }
      updateSelection(Array.from(next));
    },
    [selected, updateSelection],
  );

  const handleAddServer = useCallback(
    (serverId: string) => {
      const tools = serverTools[serverId];
      if (!tools || tools.length === 0) return;
      const next = new Set(selected);
      for (const t of tools) next.add(t.id);
      updateSelection(Array.from(next));
    },
    [selected, serverTools, updateSelection],
  );

  // Tools visible in the right pane given current filter/search state.
  const displayedTools = useMemo<McpToolInfo[]>(() => {
    if (searchResults !== null) return searchResults;
    if (activeFilter === "all") {
      return servers.flatMap((s) => serverTools[s.id] ?? []);
    }
    if (activeFilter === "recent") {
      return recentIds
        .map((id) => allToolInfo.get(id))
        .filter((t): t is McpToolInfo => t !== undefined);
    }
    return serverTools[activeFilter] ?? [];
  }, [searchResults, activeFilter, servers, serverTools, recentIds, allToolInfo]);

  // When "recent" is active but not every recent id is in allToolInfo
  // (e.g. first-open, haven't loaded the owning servers yet), fan out
  // a load of all servers so the map fills in. Cheap — each server is
  // only fetched once.
  useEffect(() => {
    if (!open || activeFilter !== "recent") return;
    if (recentIds.every((id) => allToolInfo.has(id))) return;
    servers.forEach((s) => void loadServerTools(s.id));
  }, [open, activeFilter, recentIds, allToolInfo, servers, loadServerTools]);

  if (!open) return null;

  const activeServer =
    activeFilter !== "all" && activeFilter !== "recent"
      ? servers.find((s) => s.id === activeFilter) ?? null
      : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay backdrop-blur-sm animate-fade-in-fast p-6">
      <div className="flex h-full max-h-[80vh] w-full max-w-4xl flex-col rounded-xl bg-popover border border-border shadow-5">
        <div className="flex items-center justify-between border-b border-border-subtle px-6 py-4">
          <h2 className="type-button text-fg-primary">Browse Tools</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-fg-muted hover:text-fg-primary transition-colors"
            aria-label="Close"
          >
            <X size={18} strokeWidth={2} />
          </button>
        </div>

        <div className="border-b border-border-subtle px-6 py-3">
          <Input
            placeholder="Search tools by name or description…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="flex min-h-0 flex-1">
          {/* Left rail — category filters. Hidden while search is active
              so the grid can take the full width. */}
          {searchResults === null && (
            <nav className="w-56 shrink-0 overflow-y-auto border-r border-border-subtle p-3 space-y-0.5">
              <RailItem
                active={activeFilter === "all"}
                onClick={() => setActiveFilter("all")}
                icon={<Layers size={13} strokeWidth={1.75} />}
                label="All tools"
              />
              {recentIds.length > 0 && (
                <RailItem
                  active={activeFilter === "recent"}
                  onClick={() => setActiveFilter("recent")}
                  icon={<Clock size={13} strokeWidth={1.75} />}
                  label="Recently used"
                  count={recentIds.length}
                />
              )}
              {servers.length > 0 && (
                <div className="pt-2 pb-1">
                  <span className="px-2 type-small text-fg-muted">Servers</span>
                </div>
              )}
              {servers.map((srv) => (
                <RailItem
                  key={srv.id}
                  active={activeFilter === srv.id}
                  onClick={() => setActiveFilter(srv.id)}
                  icon={<Server size={13} strokeWidth={1.75} />}
                  label={srv.name}
                  count={srv.tool_count}
                  onBulkAdd={
                    serverTools[srv.id]?.length
                      ? () => handleAddServer(srv.id)
                      : undefined
                  }
                />
              ))}
              {loadingServers && (
                <div className="flex items-center gap-2 px-2 py-2 type-caption text-fg-muted">
                  <Spinner size={12} />
                  Loading…
                </div>
              )}
            </nav>
          )}

          {/* Right pane — tool card grid. */}
          <div className="flex-1 overflow-y-auto p-4">
            {activeServer && searchResults === null && (
              <div className="mb-3 flex items-center justify-between">
                <p className="type-caption text-fg-muted">
                  {activeServer.description ?? `${activeServer.name} tools`}
                </p>
                {serverTools[activeServer.id]?.length ? (
                  <button
                    type="button"
                    onClick={() => handleAddServer(activeServer.id)}
                    className="inline-flex items-center gap-1 rounded-xs px-2 py-1 type-caption text-info hover:bg-info/10 transition-colors"
                  >
                    <Plus size={11} strokeWidth={2.5} />
                    Add all {serverTools[activeServer.id].length}
                  </button>
                ) : null}
              </div>
            )}

            {displayedTools.length === 0 ? (
              <EmptyState
                searching={searchResults !== null}
                filter={activeFilter}
                loadingServers={loadingServers}
              />
            ) : (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {displayedTools.map((tool) => (
                  <ToolCard
                    key={tool.id}
                    tool={tool}
                    checked={selected.has(tool.id)}
                    onToggle={handleToggle}
                    onShowDetails={setDetailsTool}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-border-subtle px-6 py-4">
          <span className="type-caption text-fg-muted">
            {selected.size} tool{selected.size === 1 ? "" : "s"} selected
          </span>
          <Button variant="primary" size="sm" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>

      <ToolDetailsSheet tool={detailsTool} onClose={() => setDetailsTool(null)} />
    </div>
  );
}

interface RailItemProps {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  count?: number;
  /** Optional hover-revealed bulk-add button — present only for server
   *  rows whose tools have finished loading. */
  onBulkAdd?: () => void;
}

function RailItem({ active, onClick, icon, label, count, onBulkAdd }: RailItemProps) {
  return (
    <div
      className={cn(
        "group flex items-center gap-2 rounded-sm px-2 py-1.5 type-caption transition-colors cursor-pointer",
        active
          ? "bg-info/10 text-fg-primary"
          : "text-fg-muted hover:bg-hover hover:text-fg-primary",
      )}
      onClick={onClick}
    >
      <span className={cn("shrink-0", active ? "text-info" : "text-fg-disabled")}>
        {icon}
      </span>
      <span className="flex-1 truncate">{label}</span>
      {onBulkAdd ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onBulkAdd();
          }}
          className="flex h-4 w-4 shrink-0 items-center justify-center rounded-xs text-fg-muted opacity-0 transition-opacity hover:text-info group-hover:opacity-100"
          title={`Add all ${count ?? ""} tools`}
          aria-label={`Add all ${count ?? ""} tools`}
        >
          <Plus size={11} strokeWidth={2.5} />
        </button>
      ) : count !== undefined ? (
        <span className="shrink-0 tabular-nums text-fg-muted">{count}</span>
      ) : null}
    </div>
  );
}

function EmptyState({
  searching,
  filter,
  loadingServers,
}: {
  searching: boolean;
  filter: FilterKey;
  loadingServers: boolean;
}) {
  if (loadingServers) {
    return (
      <div className="flex items-center gap-2 type-caption text-fg-muted">
        <Spinner size={12} />
        Loading tools…
      </div>
    );
  }
  if (searching) {
    return <p className="type-caption text-fg-muted">No tools match your search.</p>;
  }
  if (filter === "recent") {
    return (
      <p className="type-caption text-fg-muted">
        No recently used tools yet. Pick one to get started.
      </p>
    );
  }
  return <p className="type-caption text-fg-muted">No tools available.</p>;
}
