"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { PageLoader } from "@/components/feedback/page-loader";
import { routes } from "@/lib/constants/routes";

export default function HomePage() {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "loading") return;
    router.replace(status === "authenticated" ? routes.agents : routes.login);
  }, [status, router]);

  return <PageLoader />;
}
