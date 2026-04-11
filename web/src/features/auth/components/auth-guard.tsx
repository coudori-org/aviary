"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { PageLoader } from "@/components/feedback/page-loader";
import { routes } from "@/lib/constants/routes";

/**
 * AuthGuard — wraps protected pages, redirects unauthenticated users to /login.
 *
 * Renders a full-page loader while auth status is `loading`, then either
 * delegates to children (authenticated) or triggers a router replace.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace(routes.login);
    }
  }, [status, router]);

  if (status === "loading" || !user) {
    return <PageLoader />;
  }

  return <>{children}</>;
}
