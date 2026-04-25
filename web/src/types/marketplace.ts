export type MarketplaceKind = "agent" | "workflow";

export interface MarketplaceAuthor {
  /** Stable handle, e.g. "@platform-team". */
  handle: string;
  display_name: string;
}

export interface MarketplaceItemSummary {
  id: string;
  kind: MarketplaceKind;
  name: string;
  /** Short, single-line description shown on cards. */
  description: string;
  category: string;
  version: string;
  author: MarketplaceAuthor;
  installs: number;
  rating: number;
  /** ISO timestamp; drives the "Recently updated" sort. */
  updated_at: string;
  /** Featured items get the colored hero card on the list page. */
  featured?: boolean;
  /** Whether the current user already imported this item. */
  imported?: boolean;
  /** Whether the current user authored & published this item. */
  mine?: boolean;
  /** New version available for an item the user has imported. */
  new_update?: boolean;
}

export interface MarketplaceItem extends MarketplaceItemSummary {
  /** Long-form description / markdown summary surfaced on the detail page. */
  long_description: string;
  /** Tools the agent / workflow needs at runtime. */
  required_tools: string[];
  /** Reverse-chronological. First entry corresponds to `version`. */
  changelog: Array<{ version: string; date: string; notes: string[] }>;
  license: string;
}

export interface MarketplaceListQuery {
  kind?: MarketplaceKind;
  category?: string;
  query?: string;
  mineOnly?: boolean;
  sort?: "popular" | "rating" | "new" | "updated";
}
