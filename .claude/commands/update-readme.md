# Update README

Update all README files in the project root to reflect the current state of the codebase.

## Instructions

Follow these steps precisely:

### Step 1: Identify the last README update commit

For each README file in the project root (e.g., `README.md`, `README.ko.md`, and any other `README.*` files), find the last commit that modified it:

```
git log -1 --format="%H %ai" -- README.md
git log -1 --format="%H %ai" -- README.ko.md
```

Use the **oldest** commit among all README files as the baseline.

### Step 2: Analyze changes since last README update

Run a diff from that baseline commit to HEAD to understand what has changed in the project:

```
git diff <baseline-commit>..HEAD --stat
git diff <baseline-commit>..HEAD -- ':!README*' ':!*.lock' ':!node_modules' ':!*.json'
git log <baseline-commit>..HEAD --oneline
```

Focus on:
- New or removed services/components
- Architecture changes (new proxies, gateways, routing changes)
- New features or capabilities
- Changed tech stack (new dependencies, removed components)
- API endpoint changes
- Configuration changes
- Project structure changes (new or removed directories)

If the baseline commit IS the current HEAD (i.e., no changes since last README update), report that the README is already up to date and stop.

### Step 3: Read current README files

Read all README files in the project root to understand their current content, structure, and tone.

### Step 4: Determine what needs updating

Compare the changes found in Step 2 against the current README content. Identify:
- Sections that are now outdated or inaccurate
- Missing information about new components/features
- Information about removed components that should be deleted
- Tone inconsistencies (see tone guidelines below)

### Step 5: Update README files

Apply updates to ALL readme files found in the project root (all language variants).

**Tone & Style Guidelines:**
- Write as if you are an **open-source project maintainer** describing the project to the community
- Keep it high-level and approachable — explain WHAT the project does and WHY, not implementation minutiae
- Describe architecture and key technologies, but avoid internal implementation details (specific env vars, internal function names, DB column names, etc.)
- Use a neutral, professional tone consistent with well-known open-source projects (think Kubernetes, Grafana, Next.js docs)
- Be concise — if a section is getting too detailed, summarize and point to relevant source directories instead
- Do NOT include internal-only information like specific test database names, mock auth details, or internal debugging tips
- Keep the architecture diagram updated if the component topology has changed
- Maintain consistent formatting across all language variants

**What to include:**
- Project overview and purpose
- Architecture diagram (if topology changed)
- Key features (high-level, benefit-oriented)
- Tech stack table
- Project structure (top-level directories only)
- Getting started / Quick start
- Service port table
- API endpoints overview
- Key design decisions (1-2 paragraphs each, explain the "why")

**What NOT to include:**
- Specific environment variable tables (those belong in CLAUDE.md or internal docs)
- Implementation-specific gotchas or workarounds
- Detailed debugging instructions
- Internal test infrastructure details
- Specific version pinning details beyond major versions

**For non-English READMEs:**
- Translate all new/updated content to match the language of that file
- Ensure technical terms are used consistently with the existing translation style
- Keep code blocks, command examples, and proper nouns (project names, tech names) untranslated

### Step 6: Summary

After updating, provide a brief summary of what changed and why.
