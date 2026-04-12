"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Bot, GitBranch } from "@/components/icons";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { PageLoader } from "@/components/feedback/page-loader";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";

interface FeatureCardProps {
  href: string;
  icon: React.ReactNode;
  title: string;
  description: string;
}

function FeatureCard({ href, icon, title, description }: FeatureCardProps) {
  return (
    <Link href={href} className="group block">
      <div
        className={cn(
          "flex flex-col items-center gap-4 rounded-lg p-8 text-center transition-all duration-200",
          "bg-elevated shadow-2 hover:glow-warm",
        )}
      >
        <div className="flex h-14 w-14 items-center justify-center rounded-lg bg-raised">
          {icon}
        </div>
        <div>
          <h2 className="type-body text-fg-primary group-hover:text-brand transition-colors">
            {title}
          </h2>
          <p className="mt-1 type-caption text-fg-muted">{description}</p>
        </div>
      </div>
    </Link>
  );
}

export default function HomePage() {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") router.replace(routes.login);
  }, [status, router]);

  if (status !== "authenticated") return <PageLoader />;

  return (
    <div className="flex h-full items-center justify-center bg-canvas">
      <div className="w-full max-w-lg px-8">
        <h1 className="mb-8 text-center type-heading text-fg-primary">Aviary</h1>
        <div className="grid gap-4 sm:grid-cols-2">
          <FeatureCard
            href={routes.agents}
            icon={<Bot size={24} strokeWidth={1.5} className="text-fg-secondary" />}
            title="Chat"
            description="Talk with AI agents"
          />
          <FeatureCard
            href={routes.workflows}
            icon={<GitBranch size={24} strokeWidth={1.5} className="text-fg-secondary" />}
            title="Workflow"
            description="Build automation pipelines"
          />
        </div>
      </div>
    </div>
  );
}
