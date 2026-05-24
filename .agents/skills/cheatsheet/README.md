<div align="center">

# Personal Claude Code Cheat Sheet

**A self-updating HTML reference for every Claude Code user**

<br />

[![Install](https://img.shields.io/badge/install-npx%20skills%20add-58a6ff?style=flat-square&logo=npm)](https://github.com/sants2001/personal-claude-code-cheatsheet)
[![Skills](https://img.shields.io/badge/covers-500%2B%20skills-56d364?style=flat-square)](https://github.com/sants2001/personal-claude-code-cheatsheet)
[![Tabs](https://img.shields.io/badge/8%20tabs-shortcuts%20%E2%86%92%20meta-e3b341?style=flat-square)](https://github.com/sants2001/personal-claude-code-cheatsheet)
[![Offline](https://img.shields.io/badge/offline-capable-bc8cff?style=flat-square)](https://github.com/sants2001/personal-claude-code-cheatsheet)
[![License](https://img.shields.io/badge/license-MIT-8b949e?style=flat-square)](./LICENSE)

```bash
npx skills add sants2001/personal-claude-code-cheatsheet
```

> *"I kept forgetting my own shortcuts. Now I just open one file."*

</div>

---

## Why I Built This

I had 100+ skills installed, a dozen keybindings I kept forgetting, and no single place to see what Claude Code could actually do.

Every "getting started" guide lists the obvious stuff. Nothing showed me:
- Which of my 100+ skills to invoke for a given task
- Why Claude hallucinates and what specifically triggers it
- When extended thinking actually helps vs. wastes tokens
- What the anti-patterns look like so I can stop doing them

So I wrote a skill that reads your live session, reads your `CLAUDE.md`, and generates a single offline HTML file with everything in it. Run `/cheatsheet` any time to refresh it.

— Santino

---

## How It Works

**1. Install the skill**

```bash
npx skills add sants2001/personal-claude-code-cheatsheet
```

**2. Run it inside Claude Code**

```
/cheatsheet
```

Claude reads your live skill list from the session, your `CLAUDE.md` files if they exist, and your model routing rules. It writes a single self-contained HTML file to `~/Claude Code/cheatsheet.html` (or `~/Desktop/claude-cheatsheet.html`), then opens it automatically.

**3. Get a personal reference that reflects your actual setup**

Not a generic guide. Your installed skills, your name, your stack, your trigger table.

**4. Re-run after installing new skills**

The output always reflects the current session. New plugin installed? Run `/cheatsheet` again. It rewrites the file.

---

## Getting Started

```bash
npx skills add sants2001/personal-claude-code-cheatsheet
```

Or copy `SKILL.md` manually to `~/.claude/skills/cheatsheet/SKILL.md`.

---

## Commands

| Command | What happens |
|---|---|
| `/cheatsheet` | Full regenerate from current session |
| `/cheatsheet update` | Same as above |
| `/cheatsheet open` | Open the existing file in your browser |

---

## What's Inside (8 Tabs)

| Tab | What you get |
|---|---|
| **Shortcuts** | Every keybinding, CLI flag, and power pattern — rendered as `<kbd>` elements |
| **Skills** | All your installed skills, organized into 30+ subcategories, each row copyable |
| **Prompt Patterns** | 14 ready-to-copy prompts for debugging, TDD, review, and autonomous work |
| **Precision** | Surgical edit techniques, the exact error format that works, stopping guesswork |
| **Tokens** | Token-saving commands, model routing for cost, context hygiene do/don't list |
| **Model Routing** | Opus / Sonnet / Haiku task tables from your `model-routing.md` |
| **Full Catalog** | Filterable dense table of every installed skill with category badges |
| **How Claude Works** | Context window mechanics, hallucination triggers, thinking modes, feedback loops, anti-patterns, suggestions |

---

## Why It Works

**Reads from the live session, not a static file.**
The skills list in the cheat sheet comes from the actual `<system-reminder>` in your Claude Code session — not from scraping a directory. If you installed a skill 10 minutes ago, it's already in the output.

**No config required.**
Works for any Claude Code user out of the box. Personal details (name, stack, trigger table) are pulled from `CLAUDE.md` if present. Without it, the skill uses clean generic defaults.

**Offline-capable, no external dependencies.**
The output is a single self-contained HTML file. No CDN, no `fetch()` calls, no internet required. The dark GitHub theme loads instantly from inline CSS.

---

## Personal to You

When `~/.claude/CLAUDE.md` or `~/CLAUDE.md` exists, the cheat sheet reads them for:

- Your name and handle
- Your stack (framework, UI lib, auth, DB)
- Your proactive trigger table (message patterns → skill invocations)
- Your model routing rules
- Your autonomy and approval policies

Without those files, it falls back to sensible defaults. The skill is designed to be useful either way.

---

## Design

```
bg      #0d1117   (GitHub dark)
surface #161b22
accent  #58a6ff
text    #e6edf3
mono    SF Mono / Fira Code
```

- Global search across all tabs (Escape to clear)
- Copy-to-clipboard on every row
- Collapsible skill categories with count badges
- Mobile responsive
- Prints cleanly

---

## Example Output

See [`example.html`](./example.html) — generated from a setup with 560+ installed skills.

---

## Keeping It Current

Install new skills → run `/cheatsheet` → the file updates.

That's it.

---

<div align="center">

Built with [Claude Code](https://claude.ai/claude-code) · [MIT License](./LICENSE)

*Run `/cheatsheet`. See what you've been missing.*

</div>
