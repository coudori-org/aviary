/**
 * Compact one-line summary of a tool's input — shown next to the tool
 * name in the collapsed card so users can tell tools apart at a glance.
 *
 * The mappings here are the only place tool-name → display-text logic
 * lives. Adding a new tool means adding one entry here.
 */
export function summarizeToolInput(name: string, input: Record<string, unknown>): string {
  if (name === "Read" || name === "Write" || name === "Edit") {
    return String(input.description ?? input.file_path ?? input.path ?? "").replace(/^.*\//, "");
  }
  if (name === "Bash") {
    return String(input.description ?? input.command ?? "").slice(0, 60);
  }
  if (name === "Grep") {
    if (input.description) return String(input.description).slice(0, 60);
    const target = input.glob || input.path;
    const parts = [input.pattern && `/${input.pattern}/`, target && `in ${target}`].filter(Boolean);
    return parts.join(" ").slice(0, 60);
  }
  if (name === "Glob") return String(input.description ?? input.pattern ?? "").slice(0, 60);
  if (name === "WebFetch") return String(input.description ?? input.url ?? "").slice(0, 60);
  if (name === "Agent") return String(input.description ?? "").slice(0, 60);

  // A2A tool calls: mcp__a2a__ask_{slug} — show the message being sent
  if (name.startsWith("mcp__a2a__ask_")) {
    const slug = name.replace("mcp__a2a__ask_", "");
    const msg = String(input.message ?? "").slice(0, 50);
    return `@${slug}: ${msg}`;
  }
  if (name === "TodoWrite") {
    const todos = input.todos as Array<Record<string, string>> | undefined;
    if (todos) return `${todos.length} item${todos.length !== 1 ? "s" : ""}`;
  }

  // Generic fallback: first string value in input
  const firstVal = Object.values(input).find((v) => typeof v === "string");
  return firstVal ? String(firstVal).slice(0, 60) : "";
}
