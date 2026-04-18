"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { handleCallback } from "@/lib/auth";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { routes } from "@/lib/constants/routes";

/**
 * AuthCallback — processes the OIDC redirect with code+state, exchanges
 * for tokens, refreshes the auth context, then routes to the landing page.
 *
 * Uses a ref guard against React Strict Mode double-mount.
 */
export function AuthCallback() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { refreshUser } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const processedRef = useRef(false);

  useEffect(() => {
    if (processedRef.current) return;

    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const errorParam = searchParams.get("error");

    if (errorParam) {
      setError(searchParams.get("error_description") || errorParam);
      return;
    }

    if (!code || !state) {
      setError("Missing authorization code or state");
      return;
    }

    processedRef.current = true;

    handleCallback(code, state)
      .then(async () => {
        await refreshUser();
        router.replace(routes.home);
      })
      .catch((err: Error) => {
        setError(err.message);
        processedRef.current = false;
      });
  }, [searchParams, router, refreshUser]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="w-full max-w-md">
          <ErrorState
            title="Authentication failed"
            description={error}
            onRetry={() => {
              setError(null);
              router.replace(routes.login);
            }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <LoadingState label="Completing sign in…" />
    </div>
  );
}
