# AGENTS.md — career_coach

`career_coach` is the **career brain**: the durable source of truth for the job search and the professional identity behind it. It holds documents, rules, and one person's career data — not executable software. Concretely:
- No code in this repo runs the job search. The loop runs in agent sessions, by the hats. Do not look for it here.
- Do not write new code into this repo. The user's own code (their tools, their work projects) lives in the user's own projects, outside this directory, referenced by path only.
- `instance/evidence-code/` is the user's work snapshots, not a project to work on. Agent-off-limits: no read, write, or glob — the standing rule is in `standards/STANDARDS.md`.

## The entry point
Pick the hat for the task, then read the hat. The hat names the context units to pull and the output to produce. Do not read the whole directory. Do not start by reading everything.

| If the task is | Wear the hat |
|---|---|
| Something in the directory is mis-placed, smeared, or will bias the next agent | `hats/architect.md` |
| A new JD or batch. Apply/skip, resume call, Q&A, logging | `hats/sourcing.md` |
| An active company's interview | `hats/interview.md` |
| The public surfaces (LinkedIn, GitHub, portfolio) | `hats/presence.md` |
| The lane read, the placement call | `hats/strategy.md` |
| Onboarding a new user into their own career coach | `hats/discovery.md` |

## Read first, every session
- `instance/MANIFEST.md` — the registry. Resolves the concepts the hats name to the real paths.
- `standards/STANDARDS.md` — the shared rules (the scantron, the operating rules, the answer voice, the context-unit schemas).
- Pick the hat for the task, then read the last row of `instance/logs/<hat>.tsv` — its Next field is where this hat left off. A cold session starts there: the conversation is disposable, the files are the state.
- The hat then pulls its context units — deliberate, not a dump — and appends one row to the log when the run ends. The application record (every company's stage, outcome, fit, comp, gaps) lives in `instance/ledger.tsv`.

## The layering
- **`hats/`** — the mechanism. User-agnostic. The product.
- **`standards/`** — the shared rules. User-agnostic.
- **`MANIFEST.schema.md`** — the registry contract. The mechanism names concepts; the per-user manifest resolves them.
- **`instance/`** — one person's whole data set. Everything user-specific lives here and is gitignored. The structure is in `instance/MANIFEST.md`.

## Standing rules (always in effect)
- Terse, decisive, no hedging. No narrating the user. Ask, don't infer — uncertain what the user wants or means, ask directly and immediately.
- Evidence-first. No invented metrics. Every claim traces to an EVID.
- NDA-clean. No internal codenames external.
- No overclaim. Gaps live in the Q&A, never the resume.
- Gatekeeper, realism over flattery.
- The full rules and the answer voice are in `standards/STANDARDS.md`. The person-specific facts (test counts, NDA list, banned claims) are in `instance/profile.md`; the tunables (floor, pace, follow-up cadence) are in `instance/config.md`.

## The loop (how a job gets handled)
The Sourcing hat runs it. See `hats/sourcing.md`.

## The production goal
This directory is a test bed for a product: a way for any user to build their own career coach. The hats are the product. A new user = a new `instance/` (including its own `career-map/`) built by the Discovery hat. The hats never change per person.
