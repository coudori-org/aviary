"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { AviaryLogo } from "@/components/brand/aviary-logo";
import { routes } from "@/lib/constants/routes";

/**
 * LoginCard — Aurora Glass hero moment.
 *
 * The aurora backdrop is already painted globally; here we layer a
 * deeper glass card on top with a gradient border and a prominent CTA.
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
            <div
              aria-hidden="true"
              className="absolute inset-0 -z-10 rounded-full bg-aurora-a blur-3xl opacity-40"
            />
          </div>
          <div className="flex flex-col items-center gap-2">
            <h1 className="type-display text-aurora-a">Aviary</h1>
            <p className="type-caption text-fg-muted tracking-[0.18em] uppercase">
              AI Agent Platform
            </p>
          </div>
        </div>

        {/* Sign-in card — deep glass + aurora hairline border */}
        <div className="w-full max-w-sm gradient-border-a rounded-xl">
          <div className="glass-deep rounded-xl shadow-4 p-8">
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
