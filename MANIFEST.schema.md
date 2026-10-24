# MANIFEST — the registry contract

The manifest is the only place paths live. The mechanism (hats, standards) names **concepts**, never raw user paths. The per-user `MANIFEST.md` (in `instance/`) resolves a concept to a file. This schema is shared and tracked. A new user's manifest must define every concept below.

A concept resolves to a file or a directory. Every target must exist. A concept that cannot be resolved is a bug: the hat stops and names the missing concept, it does not guess a path.

## The concepts

| Concept | What it is | Schema (what it must contain) | Default path |
|---|---|---|---|
| `profile` | who the user is, the constants | identity, framing, evidence values, banned tools, NDA list, top priority, contract facts | `instance/profile.md` |
| `config` | the user's tunables — how the mechanism should behave | comp floor/target + red flag, pace target + formula, follow-up cadence + posture, benefit-claim constants (where applicable) | `instance/config.md` |
| `sources` | the artifacts the user points to | one entry per artifact: name, path, kind, date, EVID link | `instance/sources.md` |
| `market_intel` | external market signals — distilled industry intel | a dated, tagged signal log: source + incentive, the signal, confidence, which hat it feeds; plus a "reviewed, no keep" line per article that yielded nothing | `instance/market-intel.md` |
| `voice` | the identity voice | spine, origin, proof, philosophy, registers, carrying | `instance/career-map/identity/voice.md` |
| `strategy` | the lane and the placement | objective, active lane, what responded, what died, differentiator, top priority (plus the sibling role tiers) | `instance/career-map/job_matching/strategy.md` |
| `companies` | the pre-check data | re-apply limits, prior applications, standing calls | `instance/career-map/job_matching/companies.md` |
| `story_bank` | the stable Q&A answers | per question: the stable answer (voice), the evidence it draws on, the one company slot | `instance/career-map/resume_components/story_bank.md` |
| `evidence` | the ground truth | an index (catalog) plus one file per EVID (claim, artifact, numbers, date, source) | `instance/career-map/evidence/` |
| `skills` | the skills inventory | technical, domain, methodologies | `instance/career-map/skills/` |
| `ledger` | the application ledger | a dated row per application and outcome. The search record's spine | `instance/ledger.tsv` |
| `resume_default` | the default resume | the submitted-by-default resume (plus named variants) | `instance/resume/` (the per-user manifest resolves the file) |
| `surfaces` | the public surfaces | the LinkedIn / GitHub / portfolio copy plus the working doc | `instance/social-media/` |
| `interviews` | per-company prep | one dir per live company plus the shared standard banks; closed threads in `_archive/` (the ledger is the status source of truth) | `instance/interviews/` |
| `logs` | per-hat session logs | one dated TSV per hat (the "pick up from last" scoped to the hat) | `instance/logs/` |

## Rules
- The mechanism names concepts. The paths shown in the hats are the standard default layout for reference; a user's `MANIFEST.md` is authoritative and may relocate any concept.
- The per-user `MANIFEST.md` (in `instance/`) is private (gitignored). This schema is shared (tracked).
- `evidence` and `sources` are the ground-truth concepts. Every claim in `profile`, `voice`, `strategy`, `story_bank` traces to an `evidence` EVID.
- `standards` and `hats` are mechanism, not user data. They are tracked at fixed paths at the brain root and are not in the manifest. All user data lives under `instance/`. The per-hat SOP lives in the hat's Process section.
