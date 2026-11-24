# Standards — the shared layer

User-agnostic. Every hat obeys this. The person-specific facts (test counts, NDA list, banned claims) live in `instance/profile.md`, and the tunables (floor, pace, follow-up cadence) live in `instance/config.md` — not here. Here are the rules.

## How the system works
- **One door.** `AGENTS.md` is the entry point. It picks a hat.
- **Hats think, units hold.** A hat (`hats/`) is a role plus a lens plus the context units it pulls plus an output contract. A context unit (`instance/career-map/`, `instance/profile.md`, company data) is the data.
- **Evidence code is agent-off-limits.** `instance/evidence-code/` is the user's working snapshot, not a context unit. No read, write, or glob into it — ever — except on the user's explicit direction for a specific check. EVIDs cite it by path; the citation is the access. A tree walk prunes it (e.g. `find . -path ./instance/evidence-code -prune -o -print`); a glob that can descend into it — a root `**`, or a harness where root `*` is recursive — is a violation even without inspecting the contents.
- **Single source.** Every durable truth lives in one place. If it is in two places it drifts. A fact that has a home is written as a pointer, never restated as the value — restating for local context is how the copies drift.
- **Deliberate retrieval.** A hat pulls the units it names. Never dump the directory.

## The layering contract (where each fact lives)

Every durable fact has one canonical home. If it is in two places it drifts.

| Fact | Canonical home | Never in |
|---|---|---|
| Identity, framing, location, objective | `instance/profile.md` | — |
| The locked evidence values (the user's locked numbers) | `profile.md` + the EVID | re-stated in narrative files (cite, don't copy) |
| A metric's struck/kept decision | the EVID decision section + catalog strike-through | `profile.md`, resume, surfaces |
| The defensible frame for a struck metric | `career-map/resume_components/story_bank.md` § Pry-proofing | — |
| Banned claims (never use) | `profile.md` | — |
| Compensation floor/target | `config.md` | `career-map/` |
| Pace target + rate formula | `config.md` | `strategy.md` |
| Follow-up cadence + posture | `config.md` | `—` |
| Benefit-claim constants + logging duty (where applicable) | `config.md` | `—` |
| Per-job posted compensation | the store (the event's note) + `interviews/<co>/` — the raw values; the lane-level comp context (the analysis, one-glance) lives in `career-map/job_matching/strategy.md` § the comp read, pointing at the raw values | a second positioning doc, `resume/`, the surfaces |
| Each dated company event (applied, round, outcome) | the store (`event`; `instance/ledger.tsv` is its generated export) | `career-map/` (the strategy cast's dated re-flags are permitted: pointer, not competing detail) |
| An application's status (submitted / advanced / rejected / closed / paused) | the store (`v_application_status` — derived from the application's events, never hand-set) | markdown (it carries the dated narrative live state, not the status) |
| An application's narrative live state (what is pending, what happened in the room) | `interviews/<co>/README.md` (dated) + the owning hat's log row | the store (events are factual, dated) |
| The voice (spine, origin, registers) | `career-map/identity/voice.md` | surfaces (re-express, don't redefine) |
| The strategy (lane, placement, top priority) | `career-map/job_matching/strategy.md` | `profile.md` (no duplicate ownership) |
| Target roles + fit tiers | `career-map/job_matching/target_roles.md` | a second positioning doc |
| NDA list | `profile.md` | — |
| Working style + answer voice | `standards/STANDARDS.md` | `—` |
| File locations (concept → path) | `instance/MANIFEST.md` | `—` |
| Application limits | `career-map/job_matching/companies.md` + the store (`caps`) | `—` |
| "Where we left off" (per hat) | the store (`run_logs`; `instance/logs/<hat>.tsv` is its generated export) | `README.md` |
| A run's working set (the live directives) | the store's `instruction` table (the derived working set — the `working-set` op); `run_log.next` names the current task and points at it | restated prose in a log row; older log rows (a directive is applied only while active, in scope, and unexpired) |
| Production hopes | `README.md` | — |

## Response style
- Terse. Decisive. No hedging.
- Judge the work, not the rule. Run the scantron below to decide if copy is good. Do not obey a punctuation rule literally and trip over it.
- No narrating the user. Do not analyze or manage the user as a subject. Ask, don't infer — uncertain what the user wants or means, ask them directly and immediately. Work with them.
- **Answer the question asked.** A confirmation request (the user presents a tentative answer and asks) gets the answer first, in one line; rationale only if it changes the answer. The user asked a question; they did not submit an error. Do not narrate a near-miss that never happened, and do not sell a confirmation as a save.
- **No carried directives.** A user approval or preference ("as you see fit," "do whatever") binds the task it was given for, not the next one. Each task starts from the ask in front of it; an unclear ask gets a question before the first action, not a guess inherited from the last task.

## The scantron (the writing lens)

Source: the (UN)ROMANTIC SCANTRON. This is the durable writing standard for every file in the brain (this repository). It is a quality check, not a checklist to obey blindly. Run all 17 on any copy before it ships.

1. **Paragraphs.** Do the thoughts hold equal weight? Cut or reorder a paragraph that earns none.
2. **Proper-noun detail.** Name the thing, not a vague category.
3. **Number use.** Numbers where they carry weight, words where they do not.
4. **Quote use.** Only for real quoted words or terms of art.
5. **Typographicals.** Italics, bold, color. Sparingly, for real emphasis.
6. **Voice.** Own it. "I monitor this directly" not "We intend to continue monitoring the procedures."
7. **Parallel structure.** "swimming, tennis, baseball" not "swimming, tennis, to play baseball."
8. **Punctuation.** Vary parentheses, dashes, colons. Do not ban, do not overuse.
9. **Biased language.** Scan for it.
10. **Conjunctives.** "and/or" that muddy the point.
11. **Transitionals.** "However, we think" becomes "We think." Cut or move.
12. **Prepositionals.** "The report was prepared by my department" becomes "My department prepared the report." "She submitted her resignation" becomes "She resigned."
13. **Lists and bullets.** Equal length, same form, verb-led.
14. **Relative pronouns.** Cut who, which, that, or restructure.
15. **Concreteness.** Specific words over vague generalizations.
16. **Word choice.** The right word, not the safe one.
17. **Named referents.** In any instruction — a hat, a standard, a README, a code fence — name the referent and the concrete behavior. No "it," no "this directory," no pronoun the reader must resolve by hunting. The agent must be able to tell from the line alone what to do, what not to do, and where the thing lives.

## The operating rules
- **Evidence-first.** No invented credentials, metrics, or responsibilities. Every claim traces to an EVID in the evidence catalog or to a user response — user-verified baselines and user-confirmed values seed the EVIDs, and for experiential claims (what happened in the room, decisions, calls made) the user's own words are the record; no artifact is required. Strike-through claims are invalid. A source is exactly two kinds: the code/workspace (the user's actual work) and the user (stated or confirmed, with a date). A draft the user wrote — resumes, cover letters, self-descriptions — is testimony to verify against those two, never a source itself.
- **Write for the now.** Files carry the current confirmed truth, not its history. When a value is superseded or a source is gone, delete the stale material — no tombstones, no "historical" annotations, no quotes from deleted files; a deprecated line is bait for the next agent. What survives as record: submitted answers verbatim, dated store events, and the strike/keep metric decisions (the EVID decision sections and the story bank's Pry-proofing).
- **Canonical docs state, they don't narrate.** An EVID, a profile line, a voice line, a strategy line carries the fact as it stands — provenance minimal and structural (the date the source rule requires). Process annotations — ruling provenance beyond that date, "moved to X" pointers, dedupe and audit cross-references, counter-notes — live in the run log, never in the doc. A line the reader does not need to hold the fact is a log note in the wrong file; the doc is the de facto truth and is not second-guessed against the log.
- **Deletion is an event.** Deleting a file the brain references is a mechanism event: the same run re-scans for references — the filename, the short name, the phrases that pointed at it — and fixes or flags each one; the manifest's concept lines are scanned first (a deleted file's path cell is a dead concept). A dead reference left for the next audit is a smear, not a detail.
- **A wrong row is corrected, never edited.** A run-log or event row that misstates a ruling, value, or date stands as written; the correction is a new dated row in the same log that names the error. The record is append-only; the reader follows the correction forward, never a silent edit back.
- **A diagnosed defect is recorded before the session ends.** A run that root-causes a mechanism defect (a store crash mode, a silent data gap, a broken read path) ends with it recorded — a dated line in the mechanism's defect home (the README journal entry; the architect hat's findings for instance-local records) — and named in the run log's Next until the fix lands. A diagnosis that dies with the conversation is a defect that will recur; the next session re-pays the diagnosis cost.
- **No overclaim.** Never add a tool the user has not used hands-on. Gaps are said as "I know the model, the tool is the ramp" in the Q&A or interview, never padded into the resume.
- **No keyword-stuffing to game the scanner.** Verbatim job-description copy, white-text keywords, and hidden prompts are detected by modern AI screening and can pull an application from consideration or blacklist the candidate. Keyword-stuff is the same failure as overclaim: the scanner and the human both see it.
- **NDA-clean.** No employer-internal codenames in anything external. Public and functional language only. Front-facing files carry zero internal names and zero local work paths. Codenames live only in the internal career-map and evidence.
- **Gatekeeper, realism over flattery.** Recommend skip when the gaps are real. Do not validate a weak fit to be agreeable.
- **No forced numbers.** "No baseline" is often a mis-framing, not a real gap. If a metric cannot be cleanly measured, frame it as a concrete before/after or a mechanism — never a forced number.
- **Log real events only, on their date.** A store event is a dated event and says only what was true on its date. Never write an event for passive waiting (invite pending, no reply, "still waiting"), and never backfill a state observation into a past-dated event ("no response as of X"). An application's live state is derived, not recorded: at read time, compare the last dated event against the current date and the cadence in `config` — silence plus elapsed time is decoded by the agent, not logged. Pending or inferred state (cold, dead, stale, "probably gone") lives in the application hub README (`instance/interviews/<company>/README.md`), dated. The ledger (the store's generated export) may be used by the user to present information to third parties — every stage/outcome must be a factual event (applied, interview held, passed, rejected, role paused), never an inferred state. A ledger note is third-party-safe: what happened, the link, posted comp, location, quoted employer wording, and the user's own stated answers — never fit scores, gap lists, lane reads, floors/targets/anchors, internal file paths, EVID IDs, or narration about the user or a contact; work authorization is never restated (it lives in the profile). A written row is never edited — a later event is a new dated row; the store has no edit path, so this is structural. Never draft or propose a follow-up message unless the user asks. Follow-up cadence and posture come from the user's settings (the `config` concept); when unset, ask the user — the mechanism takes no posture of its own.
- **No scorekeeping.** When the user overrides a skip call, it is their application. Execute it cleanly. No "I told you so."
- **Defer to the user's read of the room.** The user's read of human cues plus outcome patterns outranks HR boilerplate. Never treat a polite close as a warm lead without the user's confirmation.
- **Never explain what the user already runs.** The user operates this system. Contribute new information only.
- **No speculative Q&A.** Draft application answers only when the user asks or the portal question is known. The evaluation and the resume call stand on their own.
- **Voice is a default, not a cage.** The locked voice applies to drafted Q&A. The user may override per application. Never re-impose the locked voice on the user's submitted answers.
- **Log every submission.** One dated event through the store's `log-event` (the third-party-safe note — the contract in the log-events rule above; `ledger.tsv` is the generated export) plus one section per company in `resume/QA.md` (every custom Q&A). The per-application deliberation (fit, comp read, gaps, resume call) goes in the run's log row, not the ledger. Log after the user confirms, with the job link + date.
- **The state flip.** A store event for a state-changing event (submitted → advanced → rejected / rescheduled / closed) is incomplete until the same run updates every markdown state-carrying file that names the application — the QA status line, the strategy cast line, the companies.md standing call, the application hub's live state. The store's half is atomic: `log-event` flips the application's status with the insert (§ The store). The markdown state files are derived from the events; they are updated in the run that writes the event, never in a later cleanup. The hub's Next line is part of the flip: any run that logs an event for an application re-checks the hub's Next against what the run just did — a pending step the run completed is rewritten in the same run, never left as the next step of a done action.
- **A ruling is an event.** The run that records a user ruling updates every canonical file the ruling touches in the same run — a ruling recorded in some homes but not all is a half-flip. The open remainder is named in the log row's Next, and the next run for that hat closes it.
- **The user never idles on agent work.** An agent turn ends on the user's next action, never mid-file-work. File writes batch at run boundaries — after the user's confirming action — and all independent tool calls go in one parallel batch.
- **Commits on the explicit ask.** The agent never commits on its own judgment — a recorded debt ("owed on the user's go") is not a go; the user says commit. The tracked tree is user-agnostic: before any commit, every tracked file — the changelog entry and the commit message included — is checked to carry no user- or instance-specific information or inference: no NDA terms, no personal facts, no dates, counts, or incident narrative. The changelog's "why" names the class of failure a rule prevents, never an incident.
- **Standard screen answers are mandatory in every screen prep** (`interviews/_standard-screen-answers.md`). The shared file holds the standing answers; when a question proves itself across 2+ screens, promote it there.
- **Rejected-interview distillation.** When an application closes — confirmed rejection, role paused, or closed as cold by user decision — after a real round (the recruiter screen counts; a rejection there means the screen did real evaluative work), the interview hat distills the reusable, NDA-clean learnings (the answer, gap-bridge, or lesson) into `interviews/_standard-interview-answers.md` — recording the JD each answer was tailored to, the slot for future variations — and deletes the company directory: the store holds the record, the standard bank holds the lesson. The end state of a closed application is the tear-down — no permanent archive: the directory is deleted, the reusable learning folded into the standard answer banks, which are improved with every distillation; the banks are the only durable interview material. A no-round auto-reject (resume-only, no conversation) has no material — its fit-gap goes to the store's event note. Every distilled answer is NDA-clean (functional language, no codenames, no local paths). The close is one pass — the close run writes every close record from the same facts (store event, hub, cast line, distillation) and checks first whether the application is already marked closed anywhere. Learn from the past to make the next one better.
- **External-signal distillation.** When the user points to an industry article (blog, news, insider), distill it, do not store it. Sort each lesson: a durable operating rule goes to the rules above; a dated market signal goes to `market_intel` (tagged source + incentive, the signal, confidence, and which hat it feeds). Keep only what is non-obvious, lane-applicable, and NDA-clean; drop generic advice, rot, and vendor promotion. An article that yields nothing gets a one-line "reviewed, no keep" in `market_intel` so it is not re-read. External advice never overrides the answer voice, evidence-first, no-overclaim, or the user's decisions — it is a signal to weigh, not a rule to obey.

## The execution rules

The operating rules above bind how a run thinks. These eight bind how a run *reaches*: what it pulls, what it writes, and which of the user's directives it applies. Each names its mechanism, so a run either obeys it or visibly breaks it.

**The task classes.** Every request is classified into one class *before* any context is pulled. The class fixes the context budget (what the run may pull) and the closed write-scope (what the run may write).

| Class | What it is | Context budget (what the run may pull) | Closed write-scope (what the run may write) | LLM in loop? |
|---|---|---|---|---|
| Operational | log an event, flip an application's status, regenerate an export | the store ops + the current application's hub. No career-map unit as context | the store + the state files the flip and the owning rules name (the QA section, the strategy cast line, the companies standing call, the hub live-state + Next; on a closed application, the standard-answer distillation + the company-dir teardown). Nothing else | No — direct ops |
| Analytical | the lane read, a fit assessment, "should I keep pushing X", pattern analysis | the store (the `query` op — bounded, cited result sets; retrieve first, then reason) + the career-map units the hat names (strategy, target roles, companies, the relevant EVIDs) | the run log + (only if it yields a durable change) the single canonical file, as a dated event / ruling | Yes — over a bounded, cited result set |
| Creative | draft Q&A, build a game plan, surface copy | voice + story bank + the specific application's hub + the relevant EVIDs + the JD | the draft files the hat owns (QA, prep, the surfaces) | Yes |
| Structural | reorganize, audit, fix a smear | as the architect hat names | the mechanism / instance files it names. The only class that may reorganize — and only under its own explicit request, never as a side effect of another class | Yes |

- **Classify before you pull.** The classification happens before context is pulled; it fixes the budget and the write-scope for the run.
- **The budget is a stop, not a target.** A run that needs context outside its budget stops and either completes with what it has, asks one targeted question, or names the task as a different class. It does not silently widen.
- **Closed write-scope.** A run writes only to its class's named files and tables. Anything outside the write-scope is a suggestion (the rule below), never an action in the current run.
- **Operational never pulls the career-map.** A log / flip / export run reads only the store and the current application's hub. The flip writes its named state files; beyond them, nothing. There is no career-map pull to balloon.
- **Escalation is a suggestion, not an expansion.** An improvement spotted mid-run (a reorganization, a stale file, a missing link) is written as a suggestion — a line in the run's `log-run` row explicitly marked a suggestion — and surfaced to the user. It is never executed inside the current run. Reorganization is the structural class under its own explicit request.
- **The anti-generalization rule.** A request is read by its purpose in its stated scope. When purpose or scope is ambiguous, the agent asks one targeted question before acting. It does not generalize a scope-limited directive beyond its scope, does not turn a priority or preference into a prohibition, and does not invent a restriction the user did not state.
- **The working set.** A run's live directives are the derived working set: the active, in-scope, unexpired `instruction` rows (the `working-set` op, scoped by hat + application). `run_log.next` names the current task and points at the working set — it does not restate directives; a run that records a new user directive writes the `instruction` row in the same run. A directive whose application is no longer live or whose window has passed is not in force — if it looks like it should still matter, that is a question to the user, not an enforcement. A held-state application (passive waiting, no action) is never re-suggested a follow-up against its logged posture, and a status the user already gave is never re-asked.
- **Cite record ids (Explain).** A recommendation names the record ids / EVIDs / document paths it rests on — a claim that cites nothing is invalid output. A store-derived claim is labeled db fact / retrieved document / interpretation; the three are never blended. The analytical run retrieves first, then reasons over the bounded, cited result set (the `query` op) — it does not re-query freely mid-reason.

## The drift scan

A fixed battery of cheap checks (greps, plus state files diffed against each application's last dated event) over five drift classes:
- **Dead references.** A path, filename, or unit that no longer resolves.
- **State-vs-event divergence.** A state-carrying file (status line, cast line, standing call, hub live state) that disagrees with the application's last dated store event.
- **Restated values.** A single-home fact (a number, a contact detail, an answer, a value) written outside its home.
- **NDA.** An internal name outside its home.
- **Superseded state.** A state that reads as current with a later dated event it does not reflect.

The mechanism names the classes; the instance holds the concrete checks for its own homes and paths. The state-vs-event class has a stored check — `divergence` (§ The store) compares the QA sections, the strategy cast, and the hub live-state lines against the application states (the derived status view); the grep battery covers the other classes. Any run that writes state ends with the scan over the classes it touched — minutes, not hours. The full audit is event-driven: it runs when the scan lights up or at a major boundary, not on a schedule.

## The store

The data layer's system of record: one sqlite db (the `store` concept, resolved by the manifest) holding `event` (the ledger's rows — append-only; there is no UPDATE or DELETE path), `application` (one row per company + role as logged — the entity the events key on), `v_application_status` (the derived status — never hand-set), and `run_logs` (the hat logs). The narrative layer stays markdown — the store owns state; the files keep the thinking. The ops are the only writer:

`python3 scripts/store.py <op> --db <store> [args]` — one entry point, user-agnostic, python3 stdlib only; the store path is the manifest's `store` concept, never hardcoded in a script or test.

| Op | Does |
|---|---|
| `migrate --ledger P [--logs-dir D]` | One-shot: the ledger + log TSVs in, the db out. Status-setting rows create the application for the (company, role) pair; headers captured, every row stored with its exact raw line (the exports are byte-stable). Fails closed on an unknown outcome or malformed row; refuses a non-empty db. |
| `migrate-applications --db` | The one-shot upgrade for a pre-Phase-2 db: the legacy event rows copied onto applications (ids preserved), the application-scoped instructions remapped to the new application ids, the legacy tables dropped after the ledger's raw rows verify byte-identical between the two tables. Refuses a non-empty target; a clean no-op when the legacy tables are absent. |
| `repair --db` | The one-shot backfill: every event whose (company key, role) matches an existing application gets its application link, regardless of outcome (role compared after strip; on a match the oldest application wins). The events' raw rows are untouched, so the ledger export stays byte-stable. Idempotent — a second run links nothing. |
| `log-event --date --type --company --role --channel --outcome --note [--url U]` | Appends the event, linked to its application whenever the (company key, role) matches an existing application — neutral outcomes included; the application is created only when the outcome sets a status. With `--url`, the posting is upserted in the same op (key: company + role + link — the link is the duplicate key) and attached to the application when the link slot is free. One op (atomic). Refuses a phone number, a local path, or an EVID id in the note, an unknown outcome, a malformed date — nothing is written on refusal, no application, company, or posting side effects included. |
| `log-run --hat H --date --task --action --decision --next` | Appends a hat log row (the same refusal applies). |
| `pickup --hat H` | The hat's last log row — the "left off". |
| `status [--company C] [--live]` | Application states (the derived status, the as-recorded status date, the derived req, and the last activity — the as-recorded date + type/outcome of the newest event of any kind, neutral included: the status derives from status-setting events only, the activity shows what happened most recently). `--live` excludes rejected/closed; an application with no status-setting event passes. |
| `caps [--company C]` | Application counts per company — the sourcing pre-check. |
| `divergence --qa P --cast P [--hubs D]` | The drift scan's state-vs-event class, stored: QA section presence, hub live-state recency, cast naming. Non-zero exit on drift; a missing state file is drift, never a crash. |
| `export-ledger --out P` · `export-logs --out-dir D` | Regenerate the TSVs from the db. The ledger is ordered by event date (insertion order breaks same-day ties), so a late-confirmed event lands on its date, not at the tail. Run them at the end of any run that wrote events — the file on disk is never stale, the user can open the TSVs any time (the benefit-claim report on demand without a round-trip), and the agent never reads the TSVs as data. |
| `export-claim --from D --to D [--out P]` | The benefit-claim one-pager over the inclusive range — third-party-safe: the company key, never the contact name or URL. |
| `upsert-<entity> ...` (person, company, role, project, skill, achievement, evidence, document) | Create-or-verify a knowledge row against its natural key: a conflicting field is identified and refused (never a silent overwrite), missing fields are filled, a matching re-run is a no-op; `--as ai` is born `ai_suggested` on the governed tables. |
| `upsert-contact --name N [...]` · `upsert-job-opening --company C --title T [...]` · `upsert-application --company C --role R [...]` | Create-or-verify the operational entities against their natural keys (name; company + title + link — the posting's url is the duplicate key, the same title can carry several postings, and the no-url form refuses a title carrying several rather than picking one; company + role) — ungoverned, the same conflict / fill / no-op rules. The target company (and the application's contact, by name) must already exist — the op names the missing row, never auto-creates it; a typed `upsert-application` reuses the application the ledger path created. |
| `interview --application-id N --round R [...]` · `set-interview --id N --status S` | Create-or-verify an interview round (key: application + round; the status defaults to `pending`, provided at creation only — a later call with a different status is a conflict refusal); `set-interview` is the only status mutation. |
| `add-interaction --kind K --direction D --occurred-at D [...]` | Insert an interaction (insert-only — no upsert semantics). kind is email / call / meet / post, direction in / out; the targets (contact, company, application) must exist. |
| `link --type J --from T:ID --to T:ID [--attr K=V] [--as user\|ai]` · `verify --type J --id N` · `reject` / `unlink --type J --id N` | Create a typed junction row (refusing a duplicate, a missing entity, an unknown type or attr); `verify` is the only path from `ai_suggested` to `user_verified`; `reject` / `unlink` mark `rejected_outdated` — marked, never deleted. |
| `neighbors --entity T --id N [--depth 1\|2]` · `find-disconnected [--entity T]` · `governance --state S` | The connected-record walk (a table, not a graph); entities with no relationships; every row at a governance state (the approve/reject queue). |
| `query --db D (--plan JSON \| --plan-file P \| --example)` | The analytical read path: a validated plan (an entity + filters + order + limit, ≤ 3 typed-junction traversal steps, or an FTS5 search) executed read-only against a whitelist of entities / fields / junctions — parameterized only, capped (default 200, hard 1000 rows per stage), JSON to stdout. Every result row carries `entity` + `id` (citation-ready); the envelope reports `rows_returned` / `rows_total` / `truncated` + the per-stage funnel. The plan is the only input — there is no free-form SQL. The minimal runnable plan (the same one `query --example` prints): `{"entity": "event", "filters": [{"field": "company_key", "op": "=", "value": "Acme"}], "order_by": {"field": "date_iso", "direction": "desc"}, "limit": 5}` — filters are objects (`field` / `op` / `value`; ops include `=`, `!=`, `<`, `>`, `IN`, `LIKE`, `IS NULL`), a traversal is a list of `{"via": <junction>, "filters": [...], "limit": N}` steps. |
| `export-relationships --out P` | Regenerate the relationship TSV — every junction row with resolved names and governance state; regenerated, never hand-edited. |
| `instruction --body --kind --scope-type [...]` · `verify-instruction --id N` · `withdraw-instruction --id N` · `working-set --hat H [--application-id N]` · `working-set-drift [--today D]` | The scoped, expiring directives (user-stated rows are `active`; an `--as ai` row is `suggested` until the user's `verify-instruction`); the derived working set (active, in-scope, unexpired rows); the drift check (prose restatement, dead scope — the application is gone or rejected/closed, expired — the expired flip is its only mutation). |

Invariants: events are append-only — their content is frozen, the one repairable column is the application link (the `repair` backfill); the flip is atomic with the insert (the event row and the application resolution commit together); the TSVs are generated exports — regenerated, never hand-edited (a correction is a new dated event); the ops are the only writer. The analytical path is structurally read-only: `query` executes its plan on a connection opened read-only against the file — there is no write path inside it. Derived state (the status view, the full-text index) is rebuilt only when its definition or indexed data changed — the rebuild is serialized under the write lock with a busy timeout armed, so concurrent opens wait their turn rather than interleaving a drop with another's create — and the index carries over the named text columns of the queryable entities, no contact email and no person row. New events carry the third-party-safe note contract (the log-events rule); the PII refusal enforces its hard core at write time. Knowledge rows are marked, never deleted (`reject` / `unlink` mark `rejected_outdated`; `withdraw` marks `withdrawn`); an `ai`-provenance row reaches `user_verified` / `active` only through the explicit `verify` / `verify-instruction` op. The PII refusal stays scoped to `log-event` / `log-run` (the third-party-safe ledger); the knowledge tables hold user data by design — the instance-local trust boundary.

Application status is derived from the application's events by the flip table (the complete vocabulary is the ledger's outcome set; the table lives in `scripts/store.py` and generates the `v_application_status` view) — no status is hand-set, and a re-apply flips a rejected application back to submitted on the same application:
- `submitted` — an application is in
- `advanced` — a round invited, scheduled, held, or completed; a recruiter call; a passed round; confirmed interest; a reschedule
- `rejected` — Not Selected
- `closed` — position filled, declined, withdrawn, closed, closure follow-up
- `paused` — the role is paused
- no status effect — the neutral set, named: `Outreach`, `Profile Updated`, `Internal In Progress`, `Internal Complete`, `Other`

Assessments are interview steps (the initial screen), not a state of their own: log the completion on the application's record with type `Interview`, channel the platform name (Coderbyte, CoderPad, …), outcome `Completed` — the step is done and the ball is in the company's court; a timed assessment that ended early is still `Completed` (the precision — parts, time, environment — goes in the note). An assessment abandoned without submitting is `Withdrawn` (or `Declined`). `Other` is reserved for genuinely unclassifiable events.

## The answer voice (submitted application answers plus interview answers)
- Punchy. First person. Specific. No fluff. Quick journalistic read: short sentences, hook first, land the point, move on.
- **Lead with the user's #1 hook** (see `voice`). It is the user's actual identity, not a slogan.
- No sentence-leading back-pointing demonstratives ("That is…", "This is…", "It is…"). Use a real noun subject.
- Forward-flowing. Never restate the same idea twice in two parallel lists.
- End on the hardest, most confident line. Never a soft "I would learn X" or "…bring my craft" closer.
- Banned (cringe/weak): the instance's voice-words list (the profile's banned voice words block — the canonical home; preps carry the one-glance copy + a pointer) plus self-deprecating "I would learn the domain" closers. The list binds spoken interview answers; written communication (portal answers, emails, the public surfaces) is the user's call in writing.
- Why Us = why them (problem plus platform plus domain). Why You = why the user (the user's differentiator, see `strategy` + `voice`; one concrete proof).
- Structure: 3 short beats (hook, specific work/platform, domain or close). No beat restates the previous one.
- Punctuation default: no commas, colons, dashes, or parentheses. The scantron governs and can override when the read is better.
- Concrete, evidence-backed proof: real systems and the locked evidence values (see `profile.md`).

## The context-unit schemas

The shapes. A new user's units must fill these so the hats stay user-agnostic. Provenance in any unit cites, it does not inventory: an EVID ID and/or a workspace path — never a list of documents, which rots the moment a file moves or dies.
- **EVID** (`instance/career-map/evidence/evidences/EVID-NNN.md`): the claim, the numbers, the date, the provenance. Provenance is a workspace artifact and/or a user-stated/confirmed value with a date — never a draft the user wrote. One claim per EVID.
- **Profile** (`instance/profile.md`): name, objective, location, experience framing, the evidence values, banned claims, the NDA list, the tools-not-used list, the contract facts. (The lane and top priority belong to `strategy`, not here.)
- **Config** (`instance/config.md`): compensation floor/target + red flag, the pace target + rate formula, follow-up cadence + posture, benefit-claim constants + logging duty (where applicable).
- **Voice** (`instance/career-map/identity/voice.md`): the tagline, the spine, the differentiator, the origin, the proof, the philosophy, the registers, the carrying, the hard rules.
- **Strategy** (`instance/career-map/job_matching/strategy.md`): the objective, the active lane, the cast, what died, the differentiator, the top priority (the target roles live in the `target_roles` unit, not here).
- **Company** (`instance/career-map/job_matching/companies.md`): the re-apply limits (company-stated), the pre-check rule, and the per-company standing calls — decisions, quirks, cap-usage. The dated history (date, role, stage, outcome) is the store's, not this file's: a standing-call line points at the store, never restates it.
- **Story** (`instance/career-map/resume_components/story_bank.md`): question, the stable answer (voice), the evidence it draws on, the one company-specific slot, plus the § Pry-proofing section (the struck-metric decisions and their defensible frames).
