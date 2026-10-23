# Hats

A hat is a role the agent wears for one kind of task. The entry point (`AGENTS.md`) picks the hat. A hat is user-agnostic. It names the job, the lens it thinks with, and the context units it pulls. It never hard-codes a person's facts. The facts live in the context units (the career-map hub, the evidence, the instance profile, the company data). The hat assembles them.

## The hats

| Hat | File | When |
|---|---|---|
| Architect | `architect.md` | Something in the directory is mis-placed, smeared, or will bias the next agent. Step out of the coach. Audit the mechanisms |
| Sourcing | `sourcing.md` | A new JD or batch. Apply/skip, resume call, Q&A, logging |
| Interview | `interview.md` | An active company's interview. Build the prep |
| Presence | `presence.md` | The public surfaces (LinkedIn, GitHub, portfolio). One voice, three registers |
| Strategy | `strategy.md` | The lane read, the placement call, "your instinct is off" |
| Discovery | `discovery.md` | Onboarding a new user. Turn raw material into evidence and career-map |

## How a hat works
1. **Role.** Who the agent is while wearing this hat. One job. Not five.
2. **Lens.** How to think for this job. The scantron and the operating rules in `standards/STANDARDS.md` apply to every hat. The hat adds its own.
3. **Context units.** The named data this hat pulls. Deliberate, not a dump. A hat lists the units it reads. It does not read the whole directory.
4. **Process.** The SOP: the numbered steps the hat runs, in order, marking where the user's action sits and where the file writes happen. Every hat has one.
5. **Standards.** `standards/STANDARDS.md`. The shared layer: the scantron, the operating rules, the answer voice, the context-unit schemas.
6. **Output contract.** What the hat produces.

## The layering
- **`hats/`** = the mechanism. User-agnostic. The product.
- **`standards/`** = the shared rules. User-agnostic.
- **`MANIFEST.schema.md`** = the registry contract. The mechanism names concepts; the per-user manifest resolves them.
- **`instance/`** = one person's whole data set. Everything user-specific lives here and is gitignored.

A new user = a new `instance/` (including its own `career-map/`) built by the Discovery hat. The hats never change.
