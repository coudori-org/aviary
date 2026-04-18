"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { AviaryLogo } from "@/components/brand/aviary-logo";
import { routes } from "@/lib/constants/routes";

/**
 * LoginCard — branded sign-in entry. Raycast-style: dark canvas with a
 * subtle warm-glow card, diagonal stripe accent, single CTA.
 */
export function LoginCard() {
  const { user, status, login } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated" && user) {
      router.replace(routes.home);
    }
  }, [status, user, router]);

  const isLoading = status === "loading";

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center px-6 overflow-hidden">
      {/* Decorative diagonal stripes — Raycast brand element */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-64 stripe-pattern opacity-40"
        aria-hidden="true"
      />

      <div className="relative flex flex-col items-center gap-10 animate-fade-in">
        {/* Logo + brand */}
        <div className="flex flex-col items-center gap-4">
          <AviaryLogo size={96} />
          <div className="flex flex-col items-center gap-1">
            <h1 className="type-card-heading text-fg-primary">Aviary</h1>
            <p className="type-caption text-fg-muted">AI Agent Platform</p>
          </div>
        </div>

        {/* Sign-in card */}
        <div className="w-full max-w-sm rounded-xl bg-elevated shadow-2 glow-warm p-8">
          <Button
            variant="cta"
            size="lg"
            onClick={login}
            disabled={isLoading}
            className="w-full"
          >
            {isLoading ? (
              <>
                <Spinner size={16} className="text-fg-on-light" />
                Connecting…
              </>
            ) : (
              "Sign in with SSO"
            )}
          </Button>
          <p className="mt-4 text-center type-caption text-fg-muted">
            Authenticate via your organization&apos;s identity provider
          </p>
        </div>
      </div>
    </div>
  );
}
