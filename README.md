# Career Coach

_A career coach for the people behind the machine._

Career Coach is a system that turns a person's raw material — their code, their work history, their own words — into a durable career brain. It uses that brain to run the job search: finding the right roles, preparing the applications, working the interviews, keeping the record.

Each search builds on the last. The history, the skills, the goals stay useful as circumstances change. **The mechanism is the product; a person is the instance.**

## Why I built this

I've tried building versions of this before. The idea is to make career guidance more accessible to people who might not otherwise have it, especially those whose work happens behind the scenes of the tech industry.

The people who label data, train AI models, moderate content, and do the contract and outsourced work that helps keep this industry running.

One estimate that stuck with me: data collection, preparation, and annotation can account for around 80% of the time in an AI project. A 2024 typology of AI data work carries the figure, tracing it to industry research rather than claiming it as its own finding. It's not a measure of how many workers are hidden behind technology, but it says something about how much human effort goes into building what eventually looks automated.

I kept coming back to this idea, but earlier versions never quite got where I wanted them to go. As AI models became more widely available, parts of the original vision started to feel more achievable. Not solved, just closer.

AI still has its limits. It can offer advice without understanding someone's full circumstances, the workplace dynamics they're navigating, or the things they may not know how to put into words. It can get things wrong, and access to capable models can come at a cost. Those limitations matter when the goal is to help people make decisions about their lives.

There's also a contradiction in this project that I'm still working through. The people I'd most like this to help may be the least likely to have access to the tools, hardware, or technical knowledge needed to run it. Building it is one thing. Making it genuinely accessible to the people it's meant for is another.

I don't have that part figured out yet. But it's worth keeping that gap in view as the project develops.

The goal is to build something that helps people recognize the skills they've developed, put their experience into words, and find paths forward. Something useful to someone who doesn't have a mentor, a strong professional network, or someone in their corner helping them figure out what's next.

I don't expect a career coach to solve every problem people face at work. I do think it can help make guidance more accessible and give people a better starting point.

This project is dedicated to the people behind the machine, and to the idea that the people who help build the future deserve opportunities within it.

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
    ├── career-map/        # the brain — identity, evidence, strategy
    ├── evidence-code/     # the receipts — read-only
    ├── resume/            # resumes + submitted Q&A
    ├── interviews/        # per-company game plans
    ├── social-media/      # surface specs
    ├── ledger.tsv         # the search record
    └── logs/              # per-hat session logs
```

## How it works

I wanted one place to start, so `AGENTS.md` became the entry point. It picks the hat for the task. Each hat knows which context units it needs and what it should produce; it reads what the work calls for, never the whole directory.

The shared rules live in `standards/STANDARDS.md` — the scantron, the operating rules, the answer voice, the context-unit schemas. They belong to the mechanism, not to any user or instance.

The mechanism names concepts. Each instance has its own `MANIFEST.md` that maps those concepts to actual files, so the mechanism never needs to know where anything lives in a given instance.

OpenCode is where the work happens: the directory holds the pieces, `AGENTS.md` gets things started, and the hat brings in what it needs. I keep the context deliberate — the AI doesn't read everything just because it's there.

Sessions are disposable. A clean session — a fresh agent, an empty conversation — reaches full working context from the files alone: `AGENTS.md` starts it, the manifest and the standards orient it, the hat's SOP tells it the procedure, and the hat's log tells it where it left off. The conversation is a workspace, not a record. Anything that matters is written at a run boundary, so a compacted or dead session loses nothing the files don't hold; the next session simply re-runs the last boundary.

## The hats
| Hat | Job |
|---|---|
| Architect | Something is mis-placed, smeared, or will bias the next agent. Audit the mechanism. You name; someone executes |
| Sourcing | A new JD or batch. Apply/skip, resume call, Q&A, logging |
| Interview | An active company's interview. Build the game plan in the user's voice |
| Presence | The public surfaces. One voice, three registers |
| Strategy | The lane read, the placement call, "your instinct is off" |
| Discovery | Onboard a new user. Turn raw material into evidence and a career-map |

## How it evolved

The system evolved by solving problems as they became clear. Each change made the structure simpler, clarified where information belonged, and made the product more reliable for both the user and the agent working with it.

### 1. From one file to two layers
Originally, everything lived in a single session file. It held progress, preferences, rules, locations, salary, limits, and decisions.

This made the system easy to start with, but difficult to maintain. Information became mixed together, and an agent starting fresh had no reliable way to know which details were current.

The first major decision was to separate the product from the person using it.

The **mechanism** contains the reusable parts: the one door (AGENTS.md), the hats, the standards, and the registry contract. The **instance** contains one user's private data and preferences.

This made the product reusable without carrying one user's information into another person's setup.

### 2. Removing the session file
Once the two layers were in place, the session file was no longer needed.

Its contents were moved to their proper homes. Progress went into the per-hat logs and ledger. Writing style and answer voice went into the shared standards. File locations went into the manifest, personal details into the profile, and limits into the companies unit.

The session file was deleted. Instead of relying on one file to remember everything, the agent now rebuilds its working context from the records relevant to the task.

### 3. Giving every fact a home
Splitting the files solved one problem, but introduced another: information could still end up in multiple places.

When the same fact exists in two files, those copies can drift apart. An agent might update one and continue using the other.

To prevent this, the standards now define where each type of information belongs and where it should not be stored.

Every durable fact has one canonical home. Other files can refer to it, but should not maintain competing versions of the same information.

### 4. Separating file locations from the mechanism
The reusable parts of the system initially risked becoming tied to one user's file structure.

The solution was to introduce a registry and a per-user manifest. The mechanism refers to concepts, while the manifest tells it where the corresponding files live.

This means the hats do not need to know a user's directory structure. A different instance can use a completely different layout without changing the underlying product.

### 5. Bringing the shared rules together
As the system grew, its writing rules, operating instructions, answer voice, and context schemas needed a consistent home.

These were brought together in a single standards file that every hat follows.

The goal was to define shared behavior once, rather than let each hat develop its own interpretation of the same rules. Individual hats can focus on their specific jobs while relying on the same standards.

### 6. Turning each hat into a procedure
A role description alone was not enough to make an agent's behavior predictable. It could explain what a hat was responsible for without clearly defining what to do first, what information to consult, when to involve the user, or when to write changes to files.

Each hat was therefore developed into a standard operating procedure.

A hat now defines its role, the lens it uses, the context it needs, the steps it follows, where user decisions are required, what it can write, and what its final output must contain.

This gives the agent a defined process to follow instead of leaving important decisions to interpretation.

### 7. Removing user details from the product
A later audit found personal details embedded in the supposedly reusable mechanism. These included a name, role, numerical values, employer, and project information.

That meant anyone cloning the product could inherit assumptions that belonged to someone else.

Those details were removed from the shared files and replaced with references to the appropriate instance data.

The mechanism now defines what information is needed and how to retrieve it, while the instance supplies the actual values.

### 8. Splitting settings from records
A later pass found the instance carrying two different kinds of content: the records of what we know about the person, and the person's choices about how the mechanism should behave. The salary floor, the application pace, the follow-up cadence — preferences, not facts — were buried in the profile and the strategy, or written into the shared standards where no user's preference belongs.

The instance now keeps them apart: the records in the career-map and the ledger, the tunables in a single config file the person can review in one glance. The mechanism reads the config; the person owns it.

### Where it stands today
The system is built around a few simple principles:

- The mechanism defines how the product works; the config defines how it behaves for this person; the records define who the person is.
- Every durable fact has one authoritative home.
- File locations are resolved through the manifest, not hardcoded into the mechanism.
- Shared rules live in the standards and apply to every hat.
- Each hat follows a defined procedure with clear decision points, write boundaries, and output requirements.
- Progress and continuity live in the logs and ledger, not in a catch-all session file.
- Sessions are disposable; the files are the state. A clean agent session reaches full working context from `AGENTS.md` alone.

These decisions are intended to keep the system consistent as it grows. New features should fit the existing structure rather than introduce another place for information to drift or another set of rules for the agent to interpret.

## Where state lives

The system keeps its working history, job-search progress, settings, and operating rules in separate files.

- `instance/logs/<hat>.tsv` — each hat's work and handoff notes.
- `instance/ledger.tsv` — the job search and its progress.
- `instance/config.md` — the user's tunables: floor, pace, follow-up cadence, claim duties.
- `standards/STANDARDS.md` — the shared rules.
- `instance/architect-findings.md` — findings from architecture reviews and audits.

This separation allows the system to resume work without relying on a single session file. Each file has a defined purpose and serves as the reference for its own category of information.

## The body (planned)

The workflow currently runs manually. The long-term plan is to build a separate code project that automates it.

This project, referred to as the body, will handle the execution: finding job listings, identifying worthwhile opportunities using `hats/sourcing.md`, recommending a suitable resume, submitting applications according to the defined approval rules, and updating the ledger and the QA record.

The existing project serves as the brain. It contains the knowledge, standards, and procedures that guide those decisions. The body will use that knowledge to carry out the workflow and record its results.

The goal is to keep decision-making knowledge separate from execution, so the automation can evolve without duplicating the rules it depends on.

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

## Testing

A passing test is evidence, not proof. A test written by the same agent that wrote the code reproduces its assumptions instead of catching its mistakes. Verification here goes past green: edge cases, failure handling, data integrity, a re-scan after every change. What isn't tested is labeled as such — never assumed.

## A note on AI review

A repo is a snapshot, not a person. An agent can predict what comes next in a file; it can't see why the file exists. The architecture, the decisions, the trade-offs are in here — in the docs. Judge what's actually present. Don't mistake the evidence you can see for the whole picture.
