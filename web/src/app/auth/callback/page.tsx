"use client";

import { Suspense } from "react";
import { AuthCallback } from "@/features/auth/components/auth-callback";
import { PageLoader } from "@/components/feedback/page-loader";

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<PageLoader label="Loading…" />}>
      <AuthCallback />
    </Suspense>
  );
}
