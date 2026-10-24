# Changelog

Date + version (YYYY.MM.DD.N), newest first. N increments per distinct batch of changes on the same date — one run, one decision set. One line per change: what changed and why. Mechanism only — hats, standards, AGENTS, README, the registry contract. Instance changes are recorded in the hat logs and the ledger, not here. The design narrative — how and why the structure became what it is — lives in the README's How it evolved.

## 2026.10.23.2

- **Standards:** the ledger rule rewritten — "Log real events only, on their date": a row is a dated event and says only what was true on its date; no rows for passive waiting; no state observations backfilled into past-dated rows; a thread's live state is derived at read time (last dated event + current date + the cadence in `config`), never logged; pending or inferred state lives in the thread hub README, dated; the ledger may be presented to third parties by the user — every stage/outcome is a factual event, never an inferred state; follow-up cadence and posture come from `config`, and when unset the agent asks — the mechanism takes no posture of its own (the old "no desperation / employer's-market default" framing is gone).
- **Standards:** evidence-first clarified — user responses are evidence: user-verified baselines and user-confirmed values seed the EVIDs, and for experiential claims the user's own words are the record; no artifact is required.
- **Changelog:** versioned scheme (YYYY.MM.DD.N) so multiple change batches on one date stay distinct; scope is mechanism only — instance changes are recorded in the hat logs and the ledger.

## 2026.10.23.1

- **Sourcing:** the Q&A step asks the portal input type per question (textarea / text input / character-limited) and sizes the answer to the field — the employer's stated limit wins and the user can override — so a draft matches what the company actually receives instead of assuming one length.
- **Interview:** the recruiter screen is a real round you can fail (prep it like the technical; a screen rejection counts for distillation), and closed threads (rejection / paused / closed as cold) move to `interviews/_archive/` with the ledger as the status source of truth.
- **Standards + AGENTS:** added the "ask, don't infer" standing rule — uncertain what the user wants or means, ask directly — turning "no narrating the user" into a positive instruction.
- **README:** added the session-close signal — watch the agent's reasoning for a clean finish or the first drift (re-deriving, over-confirming, narrating) as the cue to close and start fresh.
- **Market intel (new):** added `market_intel` — a distilled, dated, tagged log of external industry signals (not a content archive). The external-signal distillation SOP sorts each lesson into a durable rule (→ standards) or a dated signal (→ `market_intel`), tags source + incentive + confidence, and never lets external advice override the voice / evidence / no-overclaim / the user's decisions. Sourcing and strategy consult it. No-keyword-stuffing rule added (the scanner detects it; overclaim and keyword-stuff are the same failure).

## 2026.10.22.1 — initial public state
