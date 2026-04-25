import type {
  MarketplaceItem,
  MarketplaceItemSummary,
  MarketplaceListQuery,
} from "@/types/marketplace";
import {
  MARKETPLACE_CATEGORIES,
  MARKETPLACE_ITEMS,
  getMockMarketplaceItem,
} from "./_mocks";

const FAKE_LATENCY_MS = 120;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), FAKE_LATENCY_MS));
}

function applyFilters(
  items: MarketplaceItem[],
  q: MarketplaceListQuery,
): MarketplaceItem[] {
  let r = items;
  if (q.kind) r = r.filter((m) => m.kind === q.kind);
  if (q.category && q.category !== "All") {
    r = r.filter((m) => m.category === q.category);
  }
  if (q.mineOnly) r = r.filter((m) => m.mine);
  const text = q.query?.trim().toLowerCase();
  if (text) {
    r = r.filter((m) =>
      [m.name, m.description, m.author.display_name, m.author.handle]
        .some((field) => field.toLowerCase().includes(text)),
    );
  }
  switch (q.sort ?? "popular") {
    case "popular":
      r = [...r].sort((a, b) => b.installs - a.installs);
      break;
    case "rating":
      r = [...r].sort((a, b) => b.rating - a.rating);
      break;
    case "new":
    case "updated":
      r = [...r].sort(
        (a, b) =>
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      );
      break;
  }
  return r;
}

export const marketplaceApi = {
  async list(query: MarketplaceListQuery = {}): Promise<MarketplaceItemSummary[]> {
    const filtered = applyFilters(MARKETPLACE_ITEMS, query);
    return delay(filtered);
  },
  async featured(): Promise<MarketplaceItemSummary[]> {
    return delay(MARKETPLACE_ITEMS.filter((m) => m.featured));
  },
  async get(id: string): Promise<MarketplaceItem | null> {
    return delay(getMockMarketplaceItem(id));
  },
  async categories(): Promise<readonly string[]> {
    return delay(MARKETPLACE_CATEGORIES);
  },
};

export { MARKETPLACE_CATEGORIES };
