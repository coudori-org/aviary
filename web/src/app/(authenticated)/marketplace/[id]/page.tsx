"use client";

import { useParams } from "next/navigation";
import { MarketplaceDetail } from "@/features/marketplace/components/marketplace-detail";

export default function MarketplaceItemPage() {
  const { id } = useParams<{ id: string }>();
  return <MarketplaceDetail itemId={id} />;
}
