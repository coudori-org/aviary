"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { http } from "@/lib/http";
import type { Agent } from "@/types";

interface MentionItem {
  id: string;
  slug: string;
  name: string;
  description?: string;
}

interface MentionAutocompleteProps {
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  value: string;
  onChange: (value: string) => void;
  /** Slug of the current agent to exclude from the list (prevent self-mention) */
  excludeSlug?: string;
  /** ID of the current agent to exclude (alternative to excludeSlug) */
  excludeAgentId?: string;
  /** Called when the dropdown opens or closes (parent can suppress Enter-to-send) */
  onOpenChange?: (open: boolean) => void;
}

/** Find the index of an `@` immediately preceded by start-of-string or
 *  whitespace, scanning backwards from the cursor. Returns -1 if not found
 *  or if a whitespace breaks the run. */
function findMentionStart(text: string, cursorPos: number): number {
  for (let i = cursorPos - 1; i >= 0; i--) {
    const ch = text[i];
    if (ch === "@") {
      if (i === 0 || /\s/.test(text[i - 1])) return i;
      return -1;
    }
    if (/\s/.test(ch)) return -1;
  }
  return -1;
}

/**
 * MentionAutocomplete — dropdown overlay that triggers on `@` in a textarea
 * and lets users insert `@slug` references to other agents.
 *
 * Lazily fetches the agents list on first trigger and caches it.
 */
export function MentionAutocomplete({
  textareaRef,
  value,
  onChange,
  excludeSlug,
  excludeAgentId,
  onOpenChange,
}: MentionAutocompleteProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [agents, setAgents] = useState<MentionItem[]>([]);
  const [filtered, setFiltered] = useState<MentionItem[]>([]);
  const isVisible = isOpen && filtered.length > 0;
  useEffect(() => {
    onOpenChange?.(isVisible);
  }, [isVisible, onOpenChange]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [mentionStart, setMentionStart] = useState(-1);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const dropdownRef = useRef<HTMLDivElement>(null);
  const agentsLoaded = useRef(false);

  const loadAgents = useCallback(async () => {
    if (agentsLoaded.current) return;
    agentsLoaded.current = true;
    const res = await http.get<{ items: Agent[] }>("/agents?limit=100");
    setAgents(
      res.items.map((a) => ({
        id: a.id,
        slug: a.slug,
        name: a.name,
        description: a.description,
      })),
    );
  }, []);

  // Detect @ trigger
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const handleInput = () => {
      const cursorPos = textarea.selectionStart;
      const text = textarea.value;
      const start = findMentionStart(text, cursorPos);

      if (start >= 0) {
        const mentionQuery = text.slice(start + 1, cursorPos).toLowerCase();
        setMentionStart(start);
        setQuery(mentionQuery);
        setIsOpen(true);
        setSelectedIndex(0);
        void loadAgents();

        const rect = textarea.getBoundingClientRect();
        const lineHeight = parseInt(getComputedStyle(textarea).lineHeight) || 20;
        const lines = text.slice(0, start).split("\n").length;
        setPosition({
          top: rect.top - Math.min(lines, 3) * lineHeight - 8,
          left: rect.left + 16,
        });
      } else {
        setIsOpen(false);
      }
    };

    textarea.addEventListener("input", handleInput);
    textarea.addEventListener("click", handleInput);
    return () => {
      textarea.removeEventListener("input", handleInput);
      textarea.removeEventListener("click", handleInput);
    };
  }, [textareaRef, loadAgents]);

  // Filter agents (excluding self)
  useEffect(() => {
    if (!isOpen) return;
    const q = query.toLowerCase();
    setFiltered(
      agents
        .filter(
          (a) =>
            a.slug !== excludeSlug &&
            a.id !== excludeAgentId &&
            (a.slug.includes(q) || a.name.toLowerCase().includes(q)),
        )
        .slice(0, 8),
    );
  }, [query, agents, isOpen, excludeSlug, excludeAgentId]);

  // Keyboard navigation
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea || !isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (filtered.length === 0) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        e.stopPropagation();
        setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        e.stopPropagation();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        e.stopPropagation();
        selectAgent(filtered[selectedIndex]);
      } else if (e.key === "Escape") {
        e.stopPropagation();
        setIsOpen(false);
      }
    };

    textarea.addEventListener("keydown", handleKeyDown);
    return () => textarea.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, filtered, selectedIndex, textareaRef]);

  const selectAgent = (agent: MentionItem) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const before = value.slice(0, mentionStart);
    const after = value.slice(textarea.selectionStart);
    const newValue = `${before}@${agent.slug} ${after}`;
    onChange(newValue);
    setIsOpen(false);

    requestAnimationFrame(() => {
      const newPos = mentionStart + agent.slug.length + 2;
      textarea.setSelectionRange(newPos, newPos);
      textarea.focus();
    });
  };

  // Close on click outside
  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isOpen]);

  if (!isOpen || filtered.length === 0) return null;

  return (
    <div
      ref={dropdownRef}
      className="fixed z-50 w-72 rounded-md bg-elevated shadow-5 overflow-hidden"
      style={{ bottom: `calc(100vh - ${position.top}px)`, left: position.left }}
    >
      <div className="px-3 py-2 type-small text-fg-disabled border-b border-white/[0.06]">
        Agents
      </div>
      <div className="max-h-48 overflow-y-auto py-1">
        {filtered.map((agent, i) => (
          <button
            key={agent.slug}
            type="button"
            className={`flex w-full items-start gap-3 px-3 py-2 text-left transition-colors ${
              i === selectedIndex
                ? "bg-info/10 text-fg-primary"
                : "text-fg-secondary hover:bg-white/[0.03]"
            }`}
            onMouseEnter={() => setSelectedIndex(i)}
            onClick={() => selectAgent(agent)}
          >
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-xs bg-info/10 type-caption-bold text-info">
              @
            </div>
            <div className="min-w-0 flex-1">
              <div className="type-body-tight truncate">
                {agent.name}{" "}
                <span className="text-fg-disabled font-normal">@{agent.slug}</span>
              </div>
              {agent.description && (
                <div className="type-caption text-fg-muted truncate">{agent.description}</div>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
