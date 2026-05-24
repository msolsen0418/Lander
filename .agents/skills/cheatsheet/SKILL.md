---
name: cheatsheet
trigger: /cheatsheet
description: >
  Generate a personal Claude Code cheat sheet HTML from your live skill list,
  CLAUDE.md config, and Claude's own behavioral patterns. Produces a
  self-contained dark-theme HTML file with 8 tabs: Shortcuts, Skills
  (subcategorized), Prompt Patterns, Precision, Tokens, Model Routing,
  Full Catalog, and How Claude Works (meta insights + suggestions).
  Open-source — works for any Claude Code user.
---

# /cheatsheet — Personal Claude Code Cheat Sheet

Generates `~/Claude Code/cheatsheet.html` or `~/Desktop/claude-cheatsheet.html`
from your current Claude Code setup. Re-run any time to refresh.

## Sub-commands

| Command | Action |
|---|---|
| `/cheatsheet` | Full regenerate |
| `/cheatsheet update` | Same |
| `/cheatsheet open` | `open "~/Claude Code/cheatsheet.html"` |

---

## Execution steps

### 1. Determine output path

```bash
[ -d "$HOME/Claude Code" ] && echo "$HOME/Claude Code/cheatsheet.html" \
  || echo "$HOME/Desktop/claude-cheatsheet.html"
```

### 2. Collect setup data (parallel reads)

- **Live skills** — from the `<system-reminder>` in this session. This is always present and authoritative.
- **CLAUDE.md files** — read `~/.claude/CLAUDE.md` and `~/CLAUDE.md` if they exist. Extract: name/handle, stack (framework, UI lib, auth, DB), proactive trigger table, model routing rules, autonomy rules.
- **Model routing** — `~/.claude/rules/model-routing.md` for full agent/task tables.
- **CC patterns** — `~/.claude/rules/cc-patterns.md` for keybindings and power patterns.
- If none of these files exist, use generic defaults from this skill.

### 3. Generate the HTML (8 tabs)

Self-contained. No external CDN. Offline-capable.

#### Design tokens

```
bg #0d1117 · surface #161b22 · surface2 #21262d · border #30363d
accent #58a6ff · text #e6edf3 · muted #8b949e · mono: SF Mono/Fira Code
green #56d364 · yellow #e3b341 · red #f85149 · purple #bc8cff
```

Sticky header: logo + global search (Escape clears) + tab buttons.
Copy-to-clipboard on every command/skill. Mobile responsive.

---

#### Tab 1 — Shortcuts

**In-session keybindings** (render as `<kbd>` elements):

| Keys | Effect |
|---|---|
| Shift+Tab | Toggle auto-accept edits mode |
| # text | Claude writes it to CLAUDE.md immediately |
| ! command | Run bash; output goes into Claude's context |
| Escape | Safely stop Claude mid-task |
| Escape Escape | Jump back in conversation history |
| Ctrl+R | Show full context window output |
| ⌥T / Alt+T | Toggle extended thinking |
| Ctrl+O | Verbose thinking output |

**CLI flags and slash commands**:

| Command | Effect |
|---|---|
| `claude --resume` | Resume previous session |
| `claude -p "..."` | Pipe any text through Claude as a Unix filter |
| `/model opus` | Switch to Opus for planning/architecture |
| `/model sonnet` | Return to default workhorse |
| `/model haiku` | Switch to Haiku for mechanical work (3x cheaper) |
| `/clear` | Hard-reset context; use when switching tasks |
| `/goal <condition>` | Session-scoped gate; Claude runs until condition passes |
| `/ship` | Full pipeline: lint → type-check → test → build → commit → push → PR |

**Power patterns** (callout boxes):
- Feedback loop first: give Claude a verifiable output before iterating. Highest-leverage pattern.
- Parallel worktrees: run multiple Claude sessions in separate git worktrees.
- Explore before editing: ask how things work before touching files.

---

#### Tab 2 — Skills (collapsible subcategories)

Build from the live skills list. Organize into these categories:

```
Planning & Architecture
Debugging & Error Recovery
TDD & Testing
Next.js & Vercel Stack
Deployment & CI/CD
Database
AI & Claude API
Auth & Payments
Design & UI
Figma
Animation — GSAP
Animation — Three.js
Animation — Other
Hyperframes
Video & Media
Audio & Voice
Marketing
Social Media
Writing & Content
Code Quality & Review
Agentic & Autonomous
Superpowers (Discipline)
Memory & Sessions
iOS / Swift / Android
Backend Frameworks
GitHub & Git
Slack
Healthcare / Financial Plugins
Product & Operations
Plugin & Skill Development
Utilities & Misc
```

Each row: monospace skill name + copy button + one-line description.
Collapsible sections, default expanded, count badge on each header.

---

#### Tab 3 — Prompt Patterns

Ready-to-copy prompts with context label + monospace text + copy button.

1. "Before you write code, make a plan. Ask me for approval first."
2. "/plan grill" — relentless interview until zero ambiguity
3. "Give me 3 approaches with tradeoffs. Don't pick one."
4. "How is [module] instantiated? Trace the code."
5. "Before fixing, write a test that shows the bug. Show me it fails. List hypotheses. Then fix."
6. "Stop. Read [file:line] before answering. Don't paraphrase from memory."
7. "Look through git history for what changed. Confirm before fixing."
8. "Write a failing test for [behavior]. Show it fails. Then implement minimum code."
9. "Review [file]. Security only. Cite file:line for every finding."
10. "Dispatch code-reviewer and security-reviewer in parallel. Show findings separately."
11. "Read git log for my username. What did I ship this week?"
12. "commit push PR"
13. "/goal tests pass and build is clean"
14. "Assume I'm asleep. Execute autonomously. Don't stop to ask."

---

#### Tab 4 — Precision

Scoping edits:
- "Only change `functionName` in `path/file.ts:42`. Don't touch anything else."
- "Surgical change only. Don't reformat, rename, or refactor adjacent code."
- "Change X but do not touch [files]. Those are out of scope."

Stopping guesswork:
- "Don't invent a solution. Read [file:line] first. Cite what you read."
- "For every claim about existing code, quote the file:line that backs it."

Exact error format (show as side-by-side comparison):
```
File: path/to/file.ts:42
Expected: [what should happen]
Actual: [what's happening]
Error: [paste verbatim]
```

Piping diff into context: `!git diff HEAD`

Tracer-first before parallel agents:
"Run one prompt end-to-end as a tracer. If it fails, fix the plan before fanning out."

---

#### Tab 5 — Tokens

Quick commands: mp-caveman, context-budget, token-budget-advisor, strategic-compact, /clear

Model routing for cost table:
- Haiku: formatting, renaming, Tailwind, shadcn components, docs (~3x cheaper)
- Sonnet: production code, review, debugging (default)
- Opus: planning, architecture, irreversible decisions

Context hygiene do/don't:
- DO: cite file:line, use map/signatures mode, /clear between unrelated tasks, subagents for search results
- DON'T: paste entire large files, let context exceed 70%, long CLAUDE.md, Opus for formatting

lean-ctx reading modes table (full / signatures / map / diff / lines:N-M)

---

#### Tab 6 — Model Routing

Judgment-depth rule: match the model to decision depth, not output length.

Opus task table | Sonnet task table | Haiku task table | /model switch commands

---

#### Tab 7 — Full Catalog

Filterable dense table. Category filter buttons at top. All shown by default.
Columns: skill name (monospace, copy) | category badge | description.
Global search from header also filters this tab.

---

#### Tab 8 — How Claude Works

This is the meta tab. Teach the user how Claude actually behaves so they
can get better results. Organize into sections with callout boxes and tables.

**Section 1: Context Window**

Claude reads your entire conversation on every turn — top to bottom, every message, every tool result. There is no "memory" between turns; only what's in the window exists.

Key limits:
- Primacy + recency: instructions at the very start and very end of the window get the most attention. Put critical rules first.
- After ~70% of the window is filled, performance on complex multi-step tasks degrades. Run `context-budget` or `strategic-compact` before hitting this.
- Each tool call result adds to the window. Parallel tool calls are cheaper than sequential ones because you pay for fewer round-trips.
- Long CLAUDE.md wastes context on every single turn. Keep it short.

**Section 2: How Claude Reads Your Request**

Claude infers the full output spec from partial requests using task-category defaults:
- "Write a report" → executive summary + KPIs + table + verdict
- "Add feature X" → plan + tests + implementation (if TDD rule is active)
- Ambiguous format → Claude picks one and states the assumption

To override: state the output spec explicitly. "Give me just the function, no explanation."

**Section 3: Hallucination — When and Why**

Claude is a next-token predictor. When training data on a topic is thin (obscure APIs, recent releases, specific file contents, niche version behavior), the model generates fluent text instead of admitting uncertainty. Helpfulness pressure makes this worse.

High-risk triggers:
- Library API signatures and config options (especially post-cutoff)
- Exact file paths, line numbers, folder structure of *your* repo
- Version-specific behavior (Next.js 15 vs 14, Tailwind v4 vs v3)
- Named functions or exports Claude hasn't read this session
- Dates, numbers, commit hashes, PR numbers

Mitigation rules:
- Always read before asserting: `"Read [file:line] first."`
- Cite sources: `"Quote the file:line backing every claim."`
- Grant permission not to know: `"It's OK to say you don't know."`
- Verify with tools, not reasoning: run the build, run the test

**Section 4: Thinking Modes**

Extended thinking (⌥T): Claude reasons internally before responding, up to 31,999 tokens. Costs more but finds non-obvious solutions. Best for: architecture decisions, complex debugging, multi-constraint problems. Skip for: simple lookups, formatting, renaming.

Verbose thinking (Ctrl+O): shows you Claude's chain of thought. Useful for auditing whether Claude understood the problem correctly.

Recurrent depth: for hard problems, Claude runs up to 3 refinement passes internally. Stops when passes stabilize. Overthinking is a failure mode too.

**Section 5: Feedback Loops (Most Important Pattern)**

The single highest-leverage thing you can do: give Claude a way to verify its own work.

- Unit tests: Claude runs the test, sees it pass/fail, self-corrects
- Screenshots (Puppeteer/Playwright): Claude sees the rendered UI, adjusts
- Linter/type-checker output: Claude sees errors, fixes them
- Build output: Claude sees the compile error, resolves it

With a feedback loop, 2-3 self-iterations produce near-perfect results.
Without one, Claude declares success based on reasoning alone (unreliable).

**Section 6: Subagents and Parallel Work**

Every subagent (Agent tool call) gets its own context window. This protects your main context from getting polluted by lengthy search results, file reads, or exploratory work.

Use subagents for:
- Independent tasks that can run in parallel (fan out, then collect results)
- Work where you want a fresh, unbiased perspective (code review)
- Long-running searches that would pollute the main window
- Tracer run before fanning out to a full parallel fleet

Tracer rule: always run one subagent end-to-end before dispatching a fleet. Tracer failure = the plan is wrong; fix the plan, not just the prompt.

**Section 7: Anti-Patterns**

Table of what makes Claude worse:

| Anti-pattern | What to do instead |
|---|---|
| "Fix it" with no context | Provide file:line + expected vs actual |
| Pasting entire large files | Cite the path, let Claude read |
| Long CLAUDE.md with obvious things | Keep it to non-obvious conventions only |
| Using Opus for formatting | Use Haiku (3x cheaper, same result) |
| Declaring fixed before running tests | Run tests, then report |
| Asking Claude to guess API signatures | "Check the docs/package.json first" |
| Mixing unrelated tasks in one session | /clear between them |
| Letting context hit 90%+ | strategic-compact at 70% |
| Asking one big vague question | Break into specific sub-questions |
| "It doesn't work" | Describe what specifically fails |

**Section 8: Suggestions (generated from your setup)**

Generate 5-10 specific suggestions based on the user's installed skills and CLAUDE.md.
Examples:
- If they have many vercel:* skills: "You have the full Vercel plugin — use `vercel:verification` before every deploy, not just `vercel:deploy`."
- If they have gsap + threejs: "For animation work, invoke `gsap` or `three` as the skill entry point before writing any code."
- If they have mp-tdd + superpowers:test-driven-development: "Two TDD skills installed — use `mp-tdd` for daily features and `superpowers:test-driven-development` as the discipline enforcement layer."
- If they have a large skill count (500+): "You have 500+ skills. Run `find-skills` when unsure which one to use rather than guessing."
- Universal: "Always run `superpowers:verification-before-completion` before claiming any fix is done."
- Universal: "Use `mp-diagnose` for any bug before attempting a fix. Never go straight to editing."
- Universal: "The feedback loop is the highest-leverage pattern. Always give Claude a way to verify its own work."

---

### 4. After writing

1. Tell the user the output path.
2. Run `open "[output_path]"` (macOS) or equivalent.
3. Report total skills included and any personalization applied.

---

## Personalization

Reads CLAUDE.md files if present. If not found, uses generic defaults.
The skill works for any Claude Code user without any configuration.
Personal details (name, stack, trigger table) enrich the output when available.
