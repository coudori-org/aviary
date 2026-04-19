"use client";

import Link from "next/link";
import {
  ArrowRight,
  Bot,
  GitBranch,
  Sparkles,
  MessageSquare,
} from "@/components/icons";
import { AviaryLogo } from "@/components/brand/aviary-logo";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";
import { useAuth } from "@/features/auth/providers/auth-provider";

type Accent = "violet" | "cyan" | "mint";

interface ActionTileProps {
  href: string;
  icon: React.ReactNode;
  kicker: string;
  title: string;
  description: string;
  accent: Accent;
}

const TILE_ACCENT: Record<Accent, { icon: string; glow: string }> = {
  violet: {
    icon: "bg-aurora-violet/15 text-aurora-violet ring-1 ring-inset ring-aurora-violet/30",
    glow: "group-hover:shadow-[0_0_56px_-8px_rgba(123,92,255,0.55)]",
  },
  cyan: {
    icon: "bg-aurora-cyan/15 text-aurora-cyan ring-1 ring-inset ring-aurora-cyan/30",
    glow: "group-hover:shadow-[0_0_56px_-8px_rgba(79,201,255,0.55)]",
  },
  mint: {
    icon: "bg-aurora-mint/15 text-aurora-mint ring-1 ring-inset ring-aurora-mint/30",
    glow: "group-hover:shadow-[0_0_56px_-8px_rgba(92,255,204,0.5)]",
  },
};

function ActionTile({ href, icon, kicker, title, description, accent }: ActionTileProps) {
  const style = TILE_ACCENT[accent];
  return (
    <Link
      href={href}
      className={cn(
        "group relative flex flex-col rounded-xl glass-pane p-6",
        "transition-all duration-[320ms] ease-[cubic-bezier(0.16,1,0.3,1)]",
        "hover:-translate-y-[2px] hover:bg-white/[0.07] hover:border-white/[0.14]",
        style.glow,
      )}
    >
      <div className={cn("mb-5 inline-flex h-11 w-11 items-center justify-center rounded-lg", style.icon)}>
        {icon}
      </div>
      <div className="type-small text-fg-muted">{kicker}</div>
      <h3 className="mt-1.5 type-subheading text-fg-primary">{title}</h3>
      <p className="mt-2 type-body-tight text-fg-muted">{description}</p>
      <div className="mt-auto inline-flex items-center gap-1.5 pt-6 type-caption text-fg-tertiary transition-colors group-hover:text-fg-primary">
        <span>Open</span>
        <ArrowRight
          size={12}
          strokeWidth={2}
          className="transition-transform duration-200 group-hover:translate-x-0.5"
        />
      </div>
    </Link>
  );
}

export default function HomePage() {
  const { user } = useAuth();
  const firstName = user?.display_name?.split(" ")[0] ?? user?.email?.split("@")[0] ?? "there";

  return (
    <div className="relative h-full overflow-y-auto">
      <div className="relative mx-auto flex min-h-full max-w-container flex-col px-6 pt-16 pb-12 md:px-10 md:pt-24 md:pb-16">
        {/* Hero */}
        <section className="flex flex-col items-center text-center animate-fade-in">
          <div className="inline-flex items-center gap-2 rounded-pill glass-raised px-3 py-1 type-caption text-fg-muted">
            <Sparkles size={12} strokeWidth={1.75} className="text-aurora-violet" />
            <span>
              Welcome back, <span className="text-fg-secondary">{firstName}</span>
            </span>
          </div>

          <h1 className="mt-8 max-w-3xl text-balance type-display-hero tracking-tight">
            <span className="text-aurora-a">
              AI agents, ready to fly.
            </span>
          </h1>

          <p className="mt-5 max-w-md text-balance type-body-lg text-fg-muted">
            Your command center for Gen-AI agents and workflows.
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              href={routes.agents}
              className="inline-flex h-11 items-center gap-2 rounded-pill bg-aurora-a animate-aurora-sheen px-6 type-button text-white shadow-[0_0_32px_rgba(123,92,255,0.4),inset_0_1px_0_rgba(255,255,255,0.2)] transition-all duration-[320ms] ease-[cubic-bezier(0.16,1,0.3,1)] hover:-translate-y-[1px] hover:shadow-[0_0_44px_rgba(123,92,255,0.55),inset_0_1px_0_rgba(255,255,255,0.25)]"
            >
              <MessageSquare size={14} strokeWidth={2} />
              Start a chat
              <ArrowRight size={14} strokeWidth={2} />
            </Link>
            <Link
              href={routes.workflows}
              className="inline-flex h-11 items-center gap-2 rounded-pill glass-raised px-6 type-button text-fg-primary transition-all duration-300 hover:-translate-y-[1px] hover:bg-white/[0.11]"
            >
              <GitBranch size={14} strokeWidth={2} />
              Explore workflows
            </Link>
          </div>
        </section>

        {/* Primary action tiles */}
        <section className="mt-20 grid gap-5 sm:grid-cols-2 lg:grid-cols-3 animate-slide-up">
          <ActionTile
            href={routes.agents}
            accent="violet"
            icon={<Bot size={22} strokeWidth={1.5} />}
            kicker="Agents"
            title="Chat with your specialists"
            description="Route any request to a purpose-built AI agent — each one carries its own tools, memory, and personality."
          />
          <ActionTile
            href={routes.workflows}
            accent="cyan"
            icon={<GitBranch size={22} strokeWidth={1.5} />}
            kicker="Workflows"
            title="Orchestrate pipelines"
            description="Chain agents and tools into DAGs that run themselves — triggered, scheduled, or on-demand."
          />
          <ActionTile
            href={routes.agentNew}
            accent="mint"
            icon={<Sparkles size={22} strokeWidth={1.5} />}
            kicker="Create"
            title="Craft a new agent"
            description="Spin up a specialist in minutes. Pick a model, wire up MCP tools, and give it a voice."
          />
        </section>

        <footer className="mt-20 flex flex-col items-center gap-2 opacity-60">
          <AviaryLogo size={22} />
          <p className="type-caption text-fg-muted">Aviary · AI Agent Platform</p>
        </footer>
      </div>
    </div>
  );
}
