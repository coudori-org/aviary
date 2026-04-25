import type { MarketplaceItem } from "@/types/marketplace";

const NOW = Date.now();
const day = (n: number) => new Date(NOW - n * 86_400_000).toISOString();

export const MARKETPLACE_CATEGORIES = [
  "All",
  "Code review",
  "DevOps",
  "Data",
  "Research",
  "Internal tools",
  "Testing",
  "Documentation",
] as const;

export const MARKETPLACE_ITEMS: MarketplaceItem[] = [
  {
    id: "mp_pr_reviewer",
    kind: "agent",
    name: "PR Reviewer",
    description:
      "Reviews pull requests against your repo conventions and flags risky diffs.",
    category: "Code review",
    version: "v3.1.0",
    author: { handle: "@platform-team", display_name: "Platform Team" },
    installs: 1284,
    rating: 4.8,
    updated_at: day(2),
    featured: true,
    imported: false,
    long_description:
      "PR Reviewer reads your repository's CONVENTIONS.md and the diff context, then comments on pull requests with risk flags, missing tests, and style nits. It will not approve or merge — only annotate.",
    required_tools: [
      "github.pull_request.list",
      "github.pull_request.diff",
      "github.review.comment",
    ],
    changelog: [
      {
        version: "v3.1.0",
        date: day(2),
        notes: [
          "Reduced false-positive nits by 38%",
          "Added support for monorepo path scoping",
        ],
      },
      {
        version: "v3.0.0",
        date: day(28),
        notes: ["Switched to Claude Sonnet 4.6 by default"],
      },
    ],
    license: "Internal",
  },
  {
    id: "mp_sql_explainer",
    kind: "agent",
    name: "SQL Explainer",
    description:
      "Explains complex SQL queries in plain language and suggests safe rewrites.",
    category: "Data",
    version: "v2.4.1",
    author: { handle: "@data-platform", display_name: "Data Platform" },
    installs: 612,
    rating: 4.6,
    updated_at: day(5),
    featured: true,
    imported: true,
    new_update: true,
    long_description:
      "Walks through a SQL query clause-by-clause, calls out implicit joins or full scans, and proposes index-friendly rewrites. Read-only by default — toggle the `apply` capability to let it run EXPLAIN.",
    required_tools: ["postgres.explain", "postgres.describe"],
    changelog: [
      {
        version: "v2.4.1",
        date: day(5),
        notes: ["Postgres 16 grammar fixes"],
      },
    ],
    license: "Internal",
  },
  {
    id: "mp_release_notes",
    kind: "workflow",
    name: "Release Notes Pipeline",
    description:
      "Drafts release notes from merged PRs, posts to Slack, and opens a Notion page.",
    category: "DevOps",
    version: "v1.7.2",
    author: { handle: "@release-eng", display_name: "Release Eng" },
    installs: 423,
    rating: 4.7,
    updated_at: day(8),
    featured: true,
    imported: false,
    long_description:
      "Triggers on tagged releases. Pulls every merged PR since the previous tag, groups them by label, summarizes them, and routes the draft to Slack with a Notion link for the long-form changelog.",
    required_tools: [
      "github.tag.diff",
      "slack.post_message",
      "notion.create_page",
    ],
    changelog: [
      {
        version: "v1.7.2",
        date: day(8),
        notes: ["Honors `release-notes:skip` label"],
      },
    ],
    license: "Internal",
  },
  {
    id: "mp_doc_synth",
    kind: "agent",
    name: "Doc Synthesizer",
    description: "Turns Slack threads and meeting notes into structured docs.",
    category: "Documentation",
    version: "v1.2.0",
    author: { handle: "@knowledge-team", display_name: "Knowledge Team" },
    installs: 198,
    rating: 4.4,
    updated_at: day(14),
    long_description:
      "Reads a Slack thread or meeting transcript, extracts decisions and open questions, and writes a structured doc that you can drop into Notion or Confluence.",
    required_tools: ["slack.thread.read", "notion.create_page"],
    changelog: [
      { version: "v1.2.0", date: day(14), notes: ["Confluence export"] },
    ],
    license: "Internal",
  },
  {
    id: "mp_oncall_triage",
    kind: "workflow",
    name: "On-call Triage",
    description: "Routes PagerDuty alerts to the right team and pre-fills context.",
    category: "DevOps",
    version: "v0.9.0",
    author: { handle: "@sre", display_name: "SRE" },
    installs: 144,
    rating: 4.3,
    updated_at: day(21),
    long_description:
      "Receives PagerDuty alerts, looks up the service catalog, picks the responsible team, and posts a triage thread in their Slack channel with recent deploys and dashboards linked.",
    required_tools: ["pagerduty.alert.read", "slack.post_message"],
    changelog: [
      { version: "v0.9.0", date: day(21), notes: ["First public release"] },
    ],
    license: "Internal",
  },
  {
    id: "mp_test_synth",
    kind: "agent",
    name: "Test Synthesizer",
    description:
      "Generates unit and integration tests from your source files and existing fixtures.",
    category: "Testing",
    version: "v1.0.4",
    author: { handle: "@qa-tools", display_name: "QA Tools" },
    installs: 312,
    rating: 4.5,
    updated_at: day(11),
    long_description:
      "Reads a source file plus its sibling tests (or any fixture you point it at), then proposes additional cases — covering edges, error paths, and golden-file diffs.",
    required_tools: ["fs.read", "fs.write"],
    changelog: [
      { version: "v1.0.4", date: day(11), notes: ["Vitest + Pytest output"] },
    ],
    license: "Internal",
  },
  {
    id: "mp_research_brief",
    kind: "agent",
    name: "Research Brief",
    description:
      "Compiles a one-pager on any topic with citations from internal and web sources.",
    category: "Research",
    version: "v2.0.1",
    author: { handle: "@research-lab", display_name: "Research Lab" },
    installs: 528,
    rating: 4.6,
    updated_at: day(4),
    imported: true,
    long_description:
      "Searches your internal docs and the public web, deduplicates, and produces a 1-page brief with inline citations and a follow-up question list.",
    required_tools: ["web.search", "notion.search"],
    changelog: [
      { version: "v2.0.1", date: day(4), notes: ["Citation footnotes"] },
    ],
    license: "Internal",
  },
  {
    id: "mp_data_quality",
    kind: "workflow",
    name: "Data Quality Watchdog",
    description: "Profiles upstream tables daily and pages on schema drift.",
    category: "Data",
    version: "v1.3.0",
    author: { handle: "@analytics-eng", display_name: "Analytics Eng" },
    installs: 233,
    rating: 4.4,
    updated_at: day(9),
    long_description:
      "Runs a daily profile against your top tables, compares against the previous day, and pages the table owner if a column type changes or null-rate jumps past a threshold.",
    required_tools: ["snowflake.query", "pagerduty.alert.create"],
    changelog: [
      { version: "v1.3.0", date: day(9), notes: ["Cardinality drift checks"] },
    ],
    license: "Internal",
  },
  {
    id: "mp_internal_helpdesk",
    kind: "agent",
    name: "Internal Helpdesk",
    description:
      "Triages internal IT tickets and answers from the runbook before paging a human.",
    category: "Internal tools",
    version: "v1.1.0",
    author: { handle: "@you", display_name: "You" },
    installs: 47,
    rating: 4.2,
    updated_at: day(3),
    mine: true,
    long_description:
      "Watches the #it-help channel, matches the ticket against the runbook, and either answers directly or escalates with a pre-filled ticket.",
    required_tools: ["slack.thread.read", "jira.issue.create"],
    changelog: [
      { version: "v1.1.0", date: day(3), notes: ["Custom escalation rules"] },
    ],
    license: "Internal",
  },
  {
    id: "mp_cost_optimizer",
    kind: "agent",
    name: "AWS Cost Optimizer",
    description:
      "Scans AWS usage daily, ranks savings candidates, and proposes safe schedules.",
    category: "DevOps",
    version: "v0.8.2",
    author: { handle: "@finops", display_name: "FinOps" },
    installs: 89,
    rating: 4.1,
    updated_at: day(17),
    long_description:
      "Pulls AWS Cost Explorer data daily, identifies underused resources, and ranks savings candidates with confidence. Approval-gated before any change.",
    required_tools: [
      "aws.ec2.list_instances",
      "aws.cost_explorer.query",
      "slack.post_message",
    ],
    changelog: [
      { version: "v0.8.2", date: day(17), notes: ["Reserved-instance suggestions"] },
    ],
    license: "Internal",
  },
];

export function getMockMarketplaceItem(id: string): MarketplaceItem | null {
  return MARKETPLACE_ITEMS.find((m) => m.id === id) ?? null;
}
