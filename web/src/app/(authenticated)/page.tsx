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

type Accent = "red" | "blue" | "green";

interface ActionTileProps {
  href: string;
  icon: React.ReactNode;
  kicker: string;
  title: string;
  description: string;
  accent: Accent;
}

const TILE_ACCENT: Record<Accent, { icon: string; glow: string }> = {
  red: {
    icon: "bg-[rgba(255,99,99,0.10)] text-[#FF8585] ring-1 ring-inset ring-[rgba(255,99,99,0.25)]",
    glow: "group-hover:shadow-[0_0_48px_-8px_rgba(255,99,99,0.45)]",
  },
  blue: {
    icon: "bg-[rgba(85,179,255,0.10)] text-[#7AC4FF] ring-1 ring-inset ring-[rgba(85,179,255,0.25)]",
    glow: "group-hover:shadow-[0_0_48px_-8px_rgba(85,179,255,0.45)]",
  },
  green: {
    icon: "bg-[rgba(95,201,146,0.10)] text-[#7FD6AB] ring-1 ring-inset ring-[rgba(95,201,146,0.25)]",
    glow: "group-hover:shadow-[0_0_48px_-8px_rgba(95,201,146,0.45)]",
  },
};

function ActionTile({ href, icon, kicker, title, description, accent }: ActionTileProps) {
  const style = TILE_ACCENT[accent];
  return (
    <Link
      href={href}
      className={cn(
        "group relative flex flex-col rounded-xl border border-white/[0.06] bg-elevated/80 p-6 backdrop-blur-sm",
        "transition-all duration-300 ease-out",
        "hover:-translate-y-0.5 hover:border-white/[0.14]",
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
    <div className="relative h-full overflow-y-auto bg-canvas">
      {/* Aurora / mesh-gradient backdrop — drifts slowly for a subtle Gen-AI vibe */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div className="aurora-blob aurora-blob-red" />
        <div className="aurora-blob aurora-blob-blue" />
        <div className="aurora-blob aurora-blob-warm" />
        <div className="absolute inset-x-0 top-0 h-40 stripe-pattern opacity-[0.12] [mask-image:linear-gradient(to_bottom,black,transparent)]" />
        {/* Soft highlight near the top of the hero */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(255,255,255,0.04),transparent_55%)]" />
      </div>

      <div className="relative mx-auto flex min-h-full max-w-container flex-col px-6 pt-16 pb-12 md:px-10 md:pt-24 md:pb-16">
        {/* Hero */}
        <section className="flex flex-col items-center text-center animate-fade-in">
          <div className="inline-flex items-center gap-2 rounded-pill border border-white/[0.08] bg-white/[0.03] px-3 py-1 type-caption text-fg-muted backdrop-blur-sm">
            <Sparkles size={12} strokeWidth={1.75} className="text-info" />
            <span>
              Welcome back, <span className="text-fg-secondary">{firstName}</span>
            </span>
          </div>

          <h1 className="mt-8 max-w-3xl text-balance type-display-hero tracking-tight">
            <span className="bg-gradient-to-r from-[#FF8585] via-[#FFD27A] to-[#7AC4FF] bg-clip-text text-transparent">
              AI agents, ready to fly.
            </span>
          </h1>

          <p className="mt-5 max-w-md text-balance type-body-lg text-fg-muted">
            Your command center for Gen-AI agents and workflows.
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              href={routes.agents}
              className="inline-flex h-11 items-center gap-2 rounded-pill bg-white/[0.92] px-6 type-button text-fg-on-light shadow-3 transition-colors hover:bg-white"
            >
              <MessageSquare size={14} strokeWidth={2} />
              Start a chat
              <ArrowRight size={14} strokeWidth={2} />
            </Link>
            <Link
              href={routes.workflows}
              className="inline-flex h-11 items-center gap-2 rounded-pill border border-white/[0.10] bg-white/[0.02] px-6 type-button text-fg-primary shadow-1 backdrop-blur-sm transition-opacity hover:opacity-75"
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
            accent="red"
            icon={<Bot size={22} strokeWidth={1.5} />}
            kicker="Agents"
            title="Chat with your specialists"
            description="Route any request to a purpose-built AI agent — each one carries its own tools, memory, and personality."
          />
          <ActionTile
            href={routes.workflows}
            accent="blue"
            icon={<GitBranch size={22} strokeWidth={1.5} />}
            kicker="Workflows"
            title="Orchestrate pipelines"
            description="Chain agents and tools into DAGs that run themselves — triggered, scheduled, or on-demand."
          />
          <ActionTile
            href={routes.agentNew}
            accent="green"
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
