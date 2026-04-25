"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { AviaryLogo } from "@/components/brand/aviary-logo";
import { routes } from "@/lib/constants/routes";

/**
 * LoginCard — sign-in hero on the Slate canvas.
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
      <div className="relative flex flex-col items-center gap-10 animate-fade-in">
        {/* Logo + brand */}
        <div className="flex flex-col items-center gap-5">
          <div className="relative">
            <AviaryLogo size={104} />
          </div>
          <div className="flex flex-col items-center gap-2">
            <h1 className="type-display text-fg-primary">Aviary</h1>
            <p className="type-caption text-fg-muted tracking-[0.18em] uppercase">
              AI Agent Platform
            </p>
          </div>
        </div>

        {/* Sign-in card */}
        <div className="w-full max-w-sm rounded-xl">
          <div className="bg-raised border border-border-subtle rounded-xl shadow-xl p-8">
            <Button
              variant="cta"
              size="lg"
              onClick={login}
              disabled={isLoading}
              className="w-full"
            >
              {isLoading ? (
                <>
                  <Spinner size={16} className="text-white" />
                  Connecting…
                </>
              ) : (
                "Sign in with SSO"
              )}
            </Button>
            <p className="mt-5 text-center type-caption text-fg-muted">
              Authenticate via your organization&apos;s identity provider
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
