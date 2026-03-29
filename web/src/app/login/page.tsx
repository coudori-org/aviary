"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
  const { user, isLoading, login } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && user) {
      router.replace("/agents");
    }
  }, [user, isLoading, router]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8">
      <div className="flex flex-col items-center gap-2">
        <h1 className="text-4xl font-bold tracking-tight">Aviary</h1>
        <p className="text-muted-foreground">
          Multi-tenant AI Agent Platform
        </p>
      </div>
      <Button size="lg" onClick={login} disabled={isLoading}>
        Sign in with SSO
      </Button>
    </div>
  );
}
