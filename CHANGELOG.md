# Changelog

Date-based (YYYY.MM.DD), newest first. One line per change: what changed and why. The design narrative — how and why the structure became what it is — lives in the README's How it evolved.

## 2026.10.23

- **Sourcing:** the Q&A step asks the portal input type per question (textarea / text input / character-limited) and sizes the answer to the field — the employer's stated limit wins and the user can override — so a draft matches what the company actually receives instead of assuming one length.
- **Interview:** the recruiter screen is a real round you can fail (prep it like the technical; a screen rejection counts for distillation), and closed threads (rejection / paused / closed as cold) move to `interviews/_archive/` with the ledger as the status source of truth.
- **Standards + AGENTS:** added the "ask, don't infer" standing rule — uncertain what the user wants or means, ask directly — turning "no narrating the user" into a positive instruction.
- **README:** added the session-close signal — watch the agent's reasoning for a clean finish or the first drift (re-deriving, over-confirming, narrating) as the cue to close and start fresh.
- **Market intel (new):** added `market_intel` — a distilled, dated, tagged log of external industry signals (not a content archive). The external-signal distillation SOP sorts each lesson into a durable rule (→ standards) or a dated signal (→ `market_intel`), tags source + incentive + confidence, and never lets external advice override the voice / evidence / no-overclaim / the user's decisions. Sourcing and strategy consult it. No-keyword-stuffing rule added (the scanner detects it; overclaim and keyword-stuff are the same failure).

## 2026.10.22 — initial public state
