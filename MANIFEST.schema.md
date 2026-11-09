# MANIFEST — the registry contract

The manifest is the only place paths live. The mechanism (hats, standards) names **concepts**, never raw user paths. The per-user `MANIFEST.md` (in `instance/`) resolves a concept to a file. This schema is shared and tracked. A new user's manifest must define every concept below.

A concept resolves to a file or a directory. Every target must exist. A concept that cannot be resolved is a bug: the hat stops and names the missing concept, it does not guess a path.

## The concepts

| Concept | What it is | Schema (what it must contain) | Default path |
|---|---|---|---|
| `profile` | who the user is, the constants | identity, framing, evidence values, banned claims + tools-not-used, NDA list, contract facts | `instance/profile.md` |
| `config` | the user's tunables — how the mechanism should behave | comp floor/target + red flag, pace target + formula, follow-up cadence + posture, benefit-claim constants + logging duty (where applicable) | `instance/config.md` |
| `sources` | the artifacts the user points to | one entry per artifact: name, path, kind, date, EVID link | `instance/career-map/sources/source_registry.md` |
| `market_intel` | external market signals — distilled industry intel | a dated, tagged signal log: source + incentive, the signal, confidence, which hat it feeds; plus a "reviewed, no keep" line per article that yielded nothing | `instance/market-intel.md` |
| `voice` | the identity voice | tagline, spine, differentiator, origin, proof, philosophy, registers, carrying, hard rules | `instance/career-map/identity/voice.md` |
| `strategy` | the lane and the placement | objective, active lane, the cast (the responding record, dated), what died, differentiator, top priority | `instance/career-map/job_matching/strategy.md` |
| `companies` | the pre-check data | re-apply limits, prior applications, standing calls | `instance/career-map/job_matching/companies.md` |
| `target_roles` | the credible role targets | tiered search titles, per-role fit + evidence, the wall keywords | `instance/career-map/job_matching/target_roles.md` |
| `story_bank` | the stable Q&A answers | per question: the stable answer (voice), the evidence it draws on, the one company slot | `instance/career-map/resume_components/story_bank.md` |
| `evidence` | the ground truth | an index (catalog) plus one file per EVID (claim, numbers, date, provenance) | `instance/career-map/evidence/` |
| `evidence_code` | the user's work snapshots — the receipts | the code the EVIDs cite by path; agent-off-limits (the rule in `standards/STANDARDS.md`) | `instance/evidence-code/` |
| `skills` | the skills inventory | technical, domain, methodologies | `instance/career-map/skills/` |
| `store` | the data layer's system of record | one sqlite db: `events` (append-only dated events — no edit path), `threads` (derived status per company + role — never hand-set), `run_logs` (the hat logs). The ops in `standards/STANDARDS.md` § The store are the only writer; `ledger` and the `logs` TSVs are its generated exports | `instance/db/career.db` |
| `ledger` | the application ledger — the store's generated export | a dated row per application and outcome. The search record's spine. Third-party-safe: factual event, link, posted facts only — agent deliberation lives in the sourcing log row. Regenerated at the end of any run that wrote events, never hand-edited | `instance/ledger.tsv` |
| `resume_default` | the default resume | the submitted-by-default resume | `instance/resume/` (the per-user manifest resolves the file) |
| `resume_qa` | the per-application Q&A record | one section per company: date, status, resume call, the submitted answers verbatim | `instance/resume/QA.md` |
| `surfaces` | the public surfaces | the LinkedIn / GitHub / portfolio copy plus the working doc | `instance/social-media/` |
| `interviews` | per-company prep | one dir per live company plus the shared standard banks; closed threads are distilled into the standard bank and the company dir deleted (the store is the status source of truth) | `instance/interviews/` |
| `logs` | per-hat session logs — the store's generated export | one dated TSV per hat (the "pick up from last" scoped to the hat); regenerated, never hand-edited | `instance/logs/` |

## The standard layout (the default file tree)

The default `instance/` tree. `instance/` is gitignored, so a fresh clone of the product has no `instance/` at all — this section is the reference the Discovery hat builds a new brain from (a per-user `career-map/README.md` documents the filled map, but it does not exist before discovery). The per-user `MANIFEST.md` is authoritative and may relocate any concept; this is the default it is written against.

```
instance/
├── MANIFEST.md            # the registry — concepts → paths (this user's)
├── profile.md             # who the user is, the constants
├── config.md              # the user's tunables (settings)
├── market-intel.md        # distilled external signals (dated, tagged)
├── ledger.tsv             # the application ledger — the store's generated export
├── db/                    # the store — the data layer's system of record (career.db)
├── career-map/            # the brain
│   ├── README.md          # the map's structure + naming convention (per-user, written by discovery)
│   ├── validation.md      # project-name mapping + workspace → evidence index
│   ├── identity/          # identity.md, career_themes.md, thesis.md, voice.md
│   ├── timeline/          # career_timeline.md
│   ├── roles/             # one file per detailed role
│   ├── projects/          # one file per canonical project
│   ├── accomplishments/   # index.md
│   ├── skills/            # technical.md, methodologies.md, domain.md
│   ├── domains/           # index.md + one file per domain
│   ├── evidence/          # evidence_catalog.md + evidences/EVID-NNN.md
│   ├── resume_components/ # story_bank.md, bullet_library.md, summary_themes.md, positioning_options.md
│   ├── job_matching/      # strategy.md, companies.md, target_roles.md
│   ├── sources/           # source_registry.md
│   └── review/            # conflicts.md, unknowns.md, questions.md
├── resume/                # the default resume (the manifest names the file) + QA.md + README.md
├── interviews/            # one dir per live company + the shared standard banks
├── social-media/          # the surfaces (LinkedIn, GitHub, portfolio)
├── evidence-code/         # the user's work snapshots — agent-off-limits
└── logs/                  # one dated TSV per hat — the store's generated export
```

## Rules
- The mechanism names concepts. The paths shown in the hats are the standard default layout for reference; a user's `MANIFEST.md` is authoritative and may relocate any concept.
- The per-user `MANIFEST.md` (in `instance/`) is private (gitignored). This schema is shared (tracked).
- `evidence` and `sources` are the ground-truth concepts. Every claim in `profile`, `voice`, `strategy`, `story_bank` traces to an `evidence` EVID.
- `standards` and `hats` are mechanism, not user data. They are tracked at fixed paths at the brain root and are not in the manifest. All user data lives under `instance/`. The per-hat SOP lives in the hat's Process section.
- `store` is user data (the db, under `instance/`); the ops that write it are mechanism (`scripts/`, tracked). `ledger` and `logs` are the store's generated exports — never hand-edited; the ops are the only writer. A new user's store is built by the first `migrate`.
