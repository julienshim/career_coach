# Career Coach

A career coach built around the person, not just the job search.

Career Coach turns a person’s work history, code, and own words into a persistent career profile. It uses that context to manage the job search: identifying relevant roles, preparing applications, supporting interview prep, and tracking progress.

Each search adds to the last. Experience, skills, and goals carry forward as a person’s priorities and circumstances change. **The system is consistent; the context is personal.**

## Why I built this

I've tried building versions of this before. The idea is to make career guidance more accessible to people who keep the tech industry running behind the scenes: the people who label data, train AI models, moderate content, and do the contract and outsourced work that makes it all possible.

One estimate that stuck with me is that data collection, preparation, and annotation can account for around 80% of the time in an AI project. A 2024 typology of AI data work traces this figure to industry research. It's not a measure of how many people work behind the scenes, but it highlights just how much human effort goes into building what eventually looks automated.

Earlier versions of this idea never quite came together. As AI models became more capable and accessible, the vision started to feel more achievable. Not solved, but closer.

The limitations still matter. AI can't fully understand someone's circumstances or workplace dynamics, and it can get things wrong. There's also a contradiction I'm still working through: the people this project aims to help may be the least likely to have access to the tools, hardware, or technical knowledge needed to use it.

Building something useful is one challenge. Making it genuinely accessible is another, and I haven't figured that part out yet.

The goal is to help people recognize their skills, articulate their experience, and find paths forward, especially if they lack a mentor, a professional network, or someone in their corner.

I don't expect a career coach to solve every problem at work. But it can offer a starting point for people who might otherwise go without guidance.

This project is dedicated to the people behind the machine, and to the idea that those who help build the future deserve opportunities within it.

## Further Reading

- Muldoon, J., Cant, C., Wu, B., Graham, M. (2024). [A Typology of AI Data Work](https://journals.sagepub.com/doi/10.1177/20539517241232632). *Big Data & Society* 11(1). Open access: [repository copy](https://repository.essex.ac.uk/37647/).

## The two layers
- **The mechanism** (this root, tracked, user-agnostic, the product): `AGENTS.md` (the one door), `hats/` (the six hats, each a strict SOP), `standards/` (the shared rules), `MANIFEST.schema.md` (the registry contract), `CHANGELOG.md` (the dated change record), this README.
- **The instance** (`instance/`, per-user, private, gitignored): one person's whole data set — the records of who they are and what we know, plus the settings that tune the mechanism.

A new user is a new `instance/` (with its own `career-map/`) built by the Discovery hat. The hats never change per person. The mechanism is the product; the instance is the data.

```
career_coach/
├── AGENTS.md              # the one door — task → hat
├── README.md              # the journal — for humans
├── CHANGELOG.md           # the dated change record
├── MANIFEST.schema.md     # the registry contract — the concepts
├── standards/
│   └── STANDARDS.md       # shared rules — scantron, operating rules, voice, schemas
├── hats/
│   ├── README.md          # the hat spec
│   └── <hat>.md           # six hats, each a strict SOP
└── instance/              # one person's data — private, gitignored
    ├── MANIFEST.md        # the registry — concepts → paths
    ├── profile.md         # who the user is (facts)
     ├── config.md          # the user's tunables (settings)
     ├── market-intel.md    # distilled external signals (dated, tagged)
     ├── career-map/        # the brain — identity, evidence, strategy
    ├── evidence-code/     # the receipts — agent-off-limits (standards)
    ├── resume/            # resumes + submitted Q&A
    ├── interviews/        # per-company game plans
    ├── social-media/      # surface specs
    ├── ledger.tsv         # the search record
    └── logs/              # per-hat session logs
```

## How it works

I wanted a single place to start, so AGENTS.md became the entry point. It selects the hat for the task. Each hat knows which context units it needs and what it must produce. It loads only what the work calls for, never the entire directory.

Shared rules live in standards/STANDARDS.md: the scantron, operating rules, answer voice, and context-unit schemas. These belong to the mechanism, not to any particular user or instance.

The mechanism defines concepts; each instance provides a MANIFEST.md that maps those concepts to actual files. This keeps the mechanism independent of any instance's layout. It knows what to look for, not where a particular instance keeps it.

In the reference setup the work happens in an OpenCode session. The directory holds the pieces, AGENTS.md starts the process, and the selected hat loads what it needs. Context is deliberate: the AI doesn't read everything simply because it's available.

**Sessions are disposable.** A clean session—a fresh agent with an empty conversation—can reconstruct its full working context from files alone. AGENTS.md provides the entry point; the manifest and standards establish the environment; the hat's SOP defines the procedure; and the hat's log records where work left off. The conversation is a workspace, not a record. Anything that matters is persisted at a run boundary, so a compacted or terminated session loses nothing that the files don't already hold. The next session simply resumes from the last recorded boundary.

**When to close a session and start fresh:** the signs of drift and the handoff duties are in `The session boundary` below. The short version: close at a clean finish or at the first signs of drift — the state lives in the files, not the conversation.

## The hats
| Hat | Job |
|---|---|
| Architect | Something is mis-placed, smeared, or will bias the next agent. Audit the mechanism. You name; after approval, you execute the batch |
| Sourcing | A new JD or batch. Apply/skip, resume call, Q&A, logging |
| Interview | An active company's interview. Build the game plan in the user's voice |
| Presence | The public surfaces. One voice, three registers |
| Strategy | The lane read, the placement call, "your instinct is off" |
| Discovery | Onboard a new user. Turn raw material into evidence and a career-map |

## Common operations

What to say, and which hat picks it up:

- "Here is a JD" (or a batch) → **Sourcing** — apply/skip, the resume call, the Q&A, the logging.
- "I have an interview at X" → **Interview** — the game plan, in your voice.
- "X answered — here is the outcome" → the outcome is logged (the ledger row, the thread hub README): an application-stage event by **Sourcing**; a round outcome by **Interview**, which on a confirmed rejection also runs the distillation.
- "Update my LinkedIn / GitHub / portfolio" → **Presence** — one voice, three registers.
- "Where is the search going? Should I keep pushing X?" → **Strategy** — the lane read, the placement call.
- "Something in the brain feels off" → **Architect** — the audit.
- "Set up a new brain" → **Discovery** — a new user's instance.
- "Here is an article / a signal" → the external-signal distillation (standards) — a durable rule or a dated `market_intel` line.

The agent-facing routing table is in `AGENTS.md`; this list is for the human.

## How the System Evolved

The system evolved by addressing problems as they surfaced. Each change clarified the separation between the reusable mechanism and the user’s data, reduced duplication, and made the agent’s behavior more predictable.

### 1. Separating the mechanism from the user

Initially, everything lived in a single session file: progress, preferences, rules, locations, salary, limits, and decisions. This was easy to start with but difficult to maintain. Information became mixed together, and a fresh agent had no reliable way to determine what was current.

The first change was to separate the **mechanism** from the **instance**. The mechanism defines the reusable system: the entry point (`AGENTS.md`), the hats, shared standards, and registry contract. The instance holds one user’s data and preferences.

This made the system reusable without carrying personal information into another user’s setup.

### 2. Replacing session memory with structured records

Once the separation was established, the session file was no longer necessary. Its contents moved to dedicated homes: progress to per-hat logs and the ledger, writing conventions to shared standards, file locations to the manifest, personal details to the profile, and limits to the relevant companies unit.

The agent now rebuilds its working context from the records relevant to each task rather than relying on a single file to remember everything.

### 3. Establishing a single source of truth

Distributing information across files solved the original problem but created a risk of duplication. When the same fact appears in multiple places, copies can drift apart.

The standards now define where each type of information belongs. Every durable fact has one canonical home; other files may reference it but should not maintain competing versions.

The same principle applies to the system’s architecture. The registry defines the available resources, while the per-user manifest maps them to actual file locations. The mechanism works with those references rather than depending on a particular directory structure.

### 4. Centralizing shared standards

As the system grew, its writing conventions, operating rules, answer voice, and context schemas needed a consistent home. These were consolidated into a shared standards file that every hat follows.

Instead of interpreting the same rules independently, each hat relies on the same definitions and focuses on its specific responsibilities.

### 5. Turning roles into procedures

Role descriptions alone did not make agent behavior predictable. They explained what a hat was responsible for without necessarily defining what information to consult, what steps to follow, when to involve the user, or what changes it could make.

Each hat was therefore developed into a standard operating procedure covering its role, working perspective, required context, sequence of steps, user decision points, write permissions, and expected output.

This replaced loosely defined responsibilities with an explicit process.

### 6. Removing personal assumptions from the mechanism

A later audit found user-specific details embedded in shared files, including a name, role, numerical values, employer, and project information. Anyone reusing the system could therefore inherit assumptions that did not apply to them.

These details were removed from the mechanism and replaced with references to instance data. The mechanism defines what information is needed and how to retrieve it; the instance supplies the values.

### 7. Separating personal settings from personal records

The final distinction was between **what is known about the user** and **how the user wants the system to operate**.

Previously, settings such as salary floors, application pace, and follow-up cadence were mixed into profiles, strategy documents, or shared standards. These are configurable preferences, not personal facts or universal rules.

The instance now separates its records—the career map and ledger—from its tunable settings, held in a single configuration file. The mechanism reads the configuration; the user owns and controls it.

The result is a system with clear boundaries: reusable behavior in the mechanism, personal records in their designated files, and user-controlled settings in one place.

### Where it stands today

The system is built on a small set of governing principles:

- **Clear separation of responsibilities:** The mechanism defines how the product works, the config defines how it behaves for a specific person, and the records define who that person is.
- **One authoritative home for every durable fact:** Information has a single source of truth rather than being duplicated across files.
- **Manifest-driven file resolution:** File locations are resolved through the manifest. The paths shown in the hats are the default layout for reference; the user's manifest is authoritative.
- **Shared standards across every hat:** Common rules live in the standards and apply consistently, regardless of which hat is active.
- **Explicit procedures and boundaries:** Each hat follows a defined procedure with clear decision points, write boundaries, and output requirements.
- **Purpose-built continuity:** Progress and continuity are maintained through logs and the ledger, not accumulated in a catch-all session file.
- **Files as the source of state:** Sessions are disposable; the files are authoritative. A fresh agent session reconstructs its full working context starting from `AGENTS.md` (the manifest, the standards, the hat's log).

Together, these principles are designed to keep the system coherent as it grows. New capabilities should extend the existing structure, not create competing sources of truth, blur established boundaries, or introduce additional rules for the agent to reconcile.

## Where state lives

The system keeps its working history, job-search progress, settings, and operating rules in separate files.

- `instance/logs/<hat>.tsv` — each hat's work and handoff notes.
- `instance/ledger.tsv` — the job search and its progress.
- `instance/config.md` — the user's tunables: floor, pace, follow-up cadence, claim duties.
- `standards/STANDARDS.md` — the shared rules.

This separation allows the system to resume work without relying on a single session file. Each file has a defined purpose and serves as the reference for its own category of information.

## Setup

The mechanism runs on any agent harness. Reference setup: a local model served through [llama.cpp](https://github.com/ggml-org/llama.cpp), [OpenCode](https://opencode.ai/) as the agent, and [Superpowers](https://github.com/obra/superpowers) for structured development workflows.

Requirements:
- `llama.cpp` serving a compatible local model
- OpenCode configured to connect to it
- Superpowers installed and available

```
cd /path/to/project
opencode
```

Humans start here; agents start at `AGENTS.md`.

Running a model locally keeps inference inside your configured environment, but it does not make the whole workflow offline — plugins, external services, and other integrations may still reach remote systems depending on their configuration.

## Testing and evaluation

AI output is not self-verifying. A model can produce plausible reasoning, convincing tests, and code that passes every check while still being wrong. Tests written by the same model may reproduce the assumptions that led to the mistake.

Evaluate the reasoning, not just the result. Challenge assumptions. Look for counterexamples. Check edge cases, failure paths, and data integrity independently. Ask what evidence would change the conclusion, and distinguish what has been verified from what merely seems likely.

Evaluate the interaction, too. A model can misunderstand the task, project intentions onto the user, or become attached to an interpretation that no longer fits the evidence. When its behavior feels off, don't automatically compensate by explaining yourself more carefully. Re-examine the assumptions and the mechanisms shaping the response.

A passing test is evidence, not proof. A confident explanation is a hypothesis, not verification. Keep testing both the work and the reasoning that produced it.

## The session boundary

A session is a working context, not a source of truth. As it grows, old assumptions, abandoned approaches, and outdated references can persist long after the underlying reality has changed. The model may remember what was true without recognizing that it no longer is.

The same drift can happen in its understanding of the user. A tentative inference becomes an assumed preference. An isolated reaction becomes a personality trait. A mistaken interpretation starts shaping every subsequent response. The model then reads new evidence through a projection of its own making.

Know when to stop and start fresh. Begin a new session when the task changes substantially, the context becomes cluttered, the reasoning starts to loop, or the interaction repeatedly misses the mark. Before handing off, preserve verified facts, current state, unresolved questions, and explicit constraints. Keep inferences separate from things the user has actually said.

A fresh session is an opportunity to re-establish the facts, not an excuse to discard useful history. Carry forward what is supported. Reconsider what is merely assumed.

## The audit habit

Drift accumulates in code, documentation, context, and the model's understanding of the user. A pointer to a file that has moved. A state marker that has aged. A decision copied into multiple documents until the versions disagree. An assumption about the user's intentions repeated until it passes for fact.

This is data smear, and it compounds. Each new session can inherit the residue of the last, mistaking accumulated drift for ground truth.

Audit on a rhythm, not just when something feels wrong. After a large batch of changes. When the task changes direction. Before handing work to another session. Whenever the code, the reasoning, or the interaction feels off.

Check claims against the repository. Check interpretations against what the user actually said. When the model repeatedly misses the mark, examine the mechanism producing the behavior: the instructions, the context, the evaluation criteria, or the handoff process. Correct the mechanism instead of endlessly correcting its latest output.

Don't turn a temporary inference into a permanent rule. Don't make the user adapt to a faulty model of them. When the evidence contradicts the model's understanding, update the understanding.

The audit is cheap. A smeared brain is not.
