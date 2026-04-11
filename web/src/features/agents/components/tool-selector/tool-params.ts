/**
 * Helpers for reading per-tool parameter info from a JSON Schema.
 *
 * The MCP gateway annotates schema properties with an
 * `x-injected-from-vault` extension when the gateway will auto-fill that
 * argument from a Vault credential at call time. The injected args are
 * also stripped from the schema the agent (Claude) sees, so they only
 * appear in the catalog UI — to tell the human user which credentials
 * the tool depends on.
 */

export interface ToolParam {
  name: string;
  /** Vault key the gateway will auto-fill from, or null for a normal param. */
  vaultKey: string | null;
  /** Human-readable type string (e.g. "string", "string[] | null"). */
  type: string;
  required: boolean;
  description: string | null;
  defaultValue: unknown;
}

/**
 * Returns the top-level properties of a JSON Schema as a flat list of
 * `ToolParam` entries. Returns an empty array when the schema isn't
 * shaped like `{ properties: { ... } }`. Used by both the compact card
 * tag list (which only reads `name`/`vaultKey`) and the full details
 * sheet (which reads everything).
 */
export function extractToolParams(schema: Record<string, unknown>): ToolParam[] {
  const props = schema?.properties;
  if (!props || typeof props !== "object") return [];
  const required = Array.isArray(schema?.required)
    ? new Set(schema.required as string[])
    : new Set<string>();
  return Object.entries(props as Record<string, unknown>).map(([name, raw]) => {
    const prop = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
    const vaultKey = prop["x-injected-from-vault"];
    const description = prop.description;
    return {
      name,
      vaultKey: typeof vaultKey === "string" ? vaultKey : null,
      type: formatJsonSchemaType(prop),
      required: required.has(name),
      description: typeof description === "string" ? description : null,
      defaultValue: prop.default,
    };
  });
}

/**
 * Pretty-print a JSON Schema property's type for human display.
 *   {type:"string"}                            → "string"
 *   {type:"array", items:{type:"string"}}      → "string[]"
 *   {anyOf:[{type:"string"},{type:"null"}]}    → "string | null"
 *   {anyOf:[{type:"array",items:{type:"string"}},{type:"null"}]} → "string[] | null"
 * Falls back to "any" when the shape isn't recognized.
 */
function formatJsonSchemaType(prop: Record<string, unknown>): string {
  const anyOf = prop.anyOf;
  if (Array.isArray(anyOf)) {
    return anyOf
      .map((sub) => formatJsonSchemaType(sub as Record<string, unknown>))
      .join(" | ");
  }
  const t = prop.type;
  if (t === "array") {
    const items = prop.items as Record<string, unknown> | undefined;
    return items ? `${formatJsonSchemaType(items)}[]` : "any[]";
  }
  if (typeof t === "string") return t;
  return "any";
}
