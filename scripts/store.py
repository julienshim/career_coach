#!/usr/bin/env python3
"""The career store — the system of record for the data layer.

The store holds the structured state of the job search: events (the ledger),
application status (derived from events, never hand-set), and hat run logs.
The markdown narrative layer stays in the files; this is the data layer.

User-agnostic mechanism tooling: the db path is always passed in (--db); no
user path is hardcoded here. The ops are the only writer. Events are
append-only — there is no UPDATE or DELETE path. Exports reproduce stored
raw rows verbatim, so `export-ledger` / `export-logs` are byte-stable.

python3 stdlib only. No dependencies.
"""

import argparse
import datetime
import difflib
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import sys
import tempfile

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,               -- 'ledger_header', 'log_header:<hat>'
  value TEXT NOT NULL                   -- the file's exact header line
);
CREATE TABLE IF NOT EXISTS run_logs (
  id       INTEGER PRIMARY KEY,
  hat      TEXT NOT NULL,               -- the log filename stem
  date     TEXT NOT NULL,
  date_iso TEXT NOT NULL,
  task     TEXT NOT NULL,
  action   TEXT NOT NULL,
  decision TEXT NOT NULL,
  next     TEXT NOT NULL,
  raw_row  TEXT NOT NULL                -- exact original line; the export reproduces it verbatim
);
-- The knowledge layer is additive: a pre-existing db upgrades by being
-- opened (IF NOT EXISTS); run_logs and meta carry forward unchanged. The
-- operational layer is re-modeled on the same tables: event (the ledger,
-- keyed on application.id, defined after the application table) and the
-- v_application_status view (derived, rebuilt on every open). The
-- instruction table carries two deltas from the original design:
-- scope_ref_text (a non-id scope target: a hat name or stage label) and the
-- 'suggested' status (an agent-suggested directive, not in force until the
-- user's verify-instruction).
CREATE TABLE IF NOT EXISTS person (
  id            INTEGER PRIMARY KEY,
  full_name     TEXT NOT NULL,
  objective     TEXT,
  location      TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS company (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,
  industry      TEXT,
  notes_ref     TEXT,               -- pointer to a markdown note (files keep the thinking)
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS role (
  id            INTEGER PRIMARY KEY,
  person_id     INTEGER NOT NULL REFERENCES person(id),
  company_id    INTEGER NOT NULL REFERENCES company(id),
  title         TEXT NOT NULL,
  start_date    TEXT,
  end_date      TEXT,
  is_current    INTEGER NOT NULL DEFAULT 0,  -- 0/1
  summary_ref   TEXT,               -- pointer to markdown (the detailed role file)
  provenance    TEXT NOT NULL DEFAULT 'user_fact',
  governance_state TEXT NOT NULL DEFAULT 'user_fact',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  repo_ref      TEXT,               -- workspace path; a citation, never copied content
  summary_ref   TEXT,               -- pointer to markdown
  start_date    TEXT,
  end_date      TEXT,
  provenance    TEXT NOT NULL DEFAULT 'user_fact',
  governance_state TEXT NOT NULL DEFAULT 'user_fact',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skill (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,
  category      TEXT,               -- technical / domain / methodology
  notes_ref     TEXT,
  provenance    TEXT NOT NULL DEFAULT 'user_fact',
  governance_state TEXT NOT NULL DEFAULT 'user_fact',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS achievement (
  id            INTEGER PRIMARY KEY,
  title         TEXT NOT NULL,
  summary_ref   TEXT,               -- pointer to markdown (the long-form story)
  role_id       INTEGER REFERENCES role(id),
  project_id    INTEGER REFERENCES project(id),
  occurred_date TEXT,
  provenance    TEXT NOT NULL DEFAULT 'user_fact',
  governance_state TEXT NOT NULL DEFAULT 'user_fact',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
  id            INTEGER PRIMARY KEY,
  evid_id       TEXT NOT NULL UNIQUE,   -- e.g. 'EVID-042'
  claim         TEXT NOT NULL,
  value         TEXT,
  source_kind   TEXT NOT NULL,          -- 'code' / 'user_stated'
  source_ref    TEXT,                   -- workspace path, or a dated user statement
  as_of_date    TEXT,
  status        TEXT NOT NULL DEFAULT 'current',  -- current / struck
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS document (
  id            INTEGER PRIMARY KEY,
  doc_type      TEXT NOT NULL,      -- resume / cover / jd / submitted_answer / portfolio / other
  title         TEXT NOT NULL,
  path          TEXT NOT NULL,      -- the markdown file (the canonical long-form home)
  version       INTEGER NOT NULL DEFAULT 1,
  supersedes_id INTEGER REFERENCES document(id),  -- version chain, no content duplication
  is_third_party_safe INTEGER NOT NULL DEFAULT 0, -- may this be exported/hand over?
  provenance    TEXT NOT NULL DEFAULT 'user_fact',
  governance_state TEXT NOT NULL DEFAULT 'user_fact',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contact (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  title         TEXT,
  company_id    INTEGER REFERENCES company(id),   -- 0..1 current affiliation
  email         TEXT,        -- PII: never in a third-party-safe export
  linkedin_ref  TEXT,
  how_met       TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_opening (
  id            INTEGER PRIMARY KEY,
  company_id    INTEGER NOT NULL REFERENCES company(id),
  title         TEXT NOT NULL,
  location      TEXT,
  work_mode     TEXT,
  source        TEXT,
  url           TEXT,
  posted_date   TEXT,
  posted_comp   TEXT,
  jd_ref        TEXT,              -- pointer to the JD markdown (untrusted content, Section 10)
  status        TEXT NOT NULL DEFAULT 'open',  -- open / applied / closed
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS application (
  id            INTEGER PRIMARY KEY,
  company_id    INTEGER NOT NULL REFERENCES company(id),
  job_opening_id INTEGER REFERENCES job_opening(id),
  role          TEXT NOT NULL,           -- the role title as logged (drifts per application; not merged)
  contact_id    INTEGER REFERENCES contact(id),  -- the primary contact, 0..1
  applied_date  TEXT,
  created_at    TEXT NOT NULL,
  UNIQUE (company_id, role)
);
CREATE TABLE IF NOT EXISTS interview (
  id            INTEGER PRIMARY KEY,
  application_id INTEGER NOT NULL REFERENCES application(id),
  round         TEXT NOT NULL,
  kind          TEXT,                  -- recruiter / technical / system / onsite / ai_voice
  scheduled_at  TEXT,
  status        TEXT NOT NULL DEFAULT 'pending',  -- pending / scheduled / held / passed / failed
  feedback_ref  TEXT,                  -- pointer to markdown (the in-room narrative)
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interaction (
  id            INTEGER PRIMARY KEY,
  kind          TEXT NOT NULL,         -- email / call / meet / post
  direction     TEXT NOT NULL,         -- in / out
  occurred_at   TEXT NOT NULL,
  contact_id    INTEGER REFERENCES contact(id),
  company_id    INTEGER REFERENCES company(id),
  application_id INTEGER REFERENCES application(id),
  summary       TEXT,
  created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS note (
  id            INTEGER PRIMARY KEY,
  body_ref      TEXT,                  -- pointer to markdown when long
  body_inline   TEXT,                  -- when short
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS note_reference (
  note_id       INTEGER NOT NULL REFERENCES note(id),
  target_type   TEXT NOT NULL,         -- application / company / contact / document / job_opening
  target_id     INTEGER NOT NULL,
  PRIMARY KEY (note_id, target_type, target_id)
);
CREATE TABLE IF NOT EXISTS event (
  id            INTEGER PRIMARY KEY,   -- insertion order = ledger row number
  date          TEXT NOT NULL,         -- as recorded
  date_iso      TEXT NOT NULL,         -- ISO (range queries)
  type          TEXT NOT NULL,
  application_id INTEGER REFERENCES application(id),
  company_key   TEXT NOT NULL,         -- company key as logged (denormalized for third-party-safe export)
  role          TEXT NOT NULL,
  channel       TEXT NOT NULL,
  outcome       TEXT NOT NULL,         -- the flip-table vocabulary
  note          TEXT NOT NULL,         -- third-party-safe (write-time PII guard)
  raw_row       TEXT NOT NULL,         -- exact original line; exports reproduce verbatim
  created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS achievement_skill (
  id            INTEGER PRIMARY KEY,
  achievement_id INTEGER NOT NULL REFERENCES achievement(id),
  skill_id      INTEGER NOT NULL REFERENCES skill(id),
  level         TEXT,                  -- e.g. daily / working / conceptual
  evidence_id   INTEGER REFERENCES evidence(id),
  created_at    TEXT NOT NULL,
  provenance    TEXT NOT NULL DEFAULT 'user_fact',
  governance_state TEXT NOT NULL DEFAULT 'user_fact',
  UNIQUE (achievement_id, skill_id)
);
CREATE TABLE IF NOT EXISTS job_skill (
  id            INTEGER PRIMARY KEY,
  job_opening_id INTEGER NOT NULL REFERENCES job_opening(id),
  skill_id      INTEGER NOT NULL REFERENCES skill(id),
  required_level TEXT,
  source        TEXT NOT NULL DEFAULT 'jd',  -- jd (stated) / inferred (AI or user read)
  created_at    TEXT NOT NULL,
  provenance    TEXT NOT NULL DEFAULT 'imported',
  governance_state TEXT NOT NULL DEFAULT 'imported',
  UNIQUE (job_opening_id, skill_id)
);
CREATE TABLE IF NOT EXISTS resume_achievement (
  id            INTEGER PRIMARY KEY,
  document_id   INTEGER NOT NULL REFERENCES document(id),
  achievement_id INTEGER NOT NULL REFERENCES achievement(id),
  placement     TEXT,                  -- e.g. section / bullet order hint
  created_at    TEXT NOT NULL,
  provenance    TEXT NOT NULL DEFAULT 'user_fact',
  governance_state TEXT NOT NULL DEFAULT 'user_fact',
  UNIQUE (document_id, achievement_id)
);
CREATE TABLE IF NOT EXISTS application_document (
  id            INTEGER PRIMARY KEY,
  application_id INTEGER NOT NULL REFERENCES application(id),
  document_id   INTEGER NOT NULL REFERENCES document(id),
  purpose       TEXT NOT NULL,         -- resume / cover / take_home / other
  created_at    TEXT NOT NULL,
  provenance    TEXT NOT NULL DEFAULT 'user_fact',
  governance_state TEXT NOT NULL DEFAULT 'user_fact',
  UNIQUE (application_id, document_id, purpose)
);
CREATE TABLE IF NOT EXISTS project_skill (
  id            INTEGER PRIMARY KEY,
  project_id    INTEGER NOT NULL REFERENCES project(id),
  skill_id      INTEGER NOT NULL REFERENCES skill(id),
  level         TEXT,
  created_at    TEXT NOT NULL,
  provenance    TEXT NOT NULL DEFAULT 'user_fact',
  governance_state TEXT NOT NULL DEFAULT 'user_fact',
  UNIQUE (project_id, skill_id)
);
CREATE TABLE IF NOT EXISTS contact_company (
  id            INTEGER PRIMARY KEY,
  contact_id    INTEGER NOT NULL REFERENCES contact(id),
  company_id    INTEGER NOT NULL REFERENCES company(id),
  role          TEXT,
  start_date    TEXT,
  end_date      TEXT,
  is_current    INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL,
  provenance    TEXT NOT NULL DEFAULT 'user_fact',
  governance_state TEXT NOT NULL DEFAULT 'user_fact',
  UNIQUE (contact_id, company_id, start_date)
);
CREATE TABLE IF NOT EXISTS application_contact (
  id            INTEGER PRIMARY KEY,
  application_id INTEGER NOT NULL REFERENCES application(id),
  contact_id    INTEGER NOT NULL REFERENCES contact(id),
  relationship  TEXT NOT NULL,         -- referral / recruiter / interviewer / peer
  created_at    TEXT NOT NULL,
  provenance    TEXT NOT NULL DEFAULT 'user_fact',
  governance_state TEXT NOT NULL DEFAULT 'user_fact',
  UNIQUE (application_id, contact_id)
);
CREATE TABLE IF NOT EXISTS document_achievement (
  id            INTEGER PRIMARY KEY,
  document_id   INTEGER NOT NULL REFERENCES document(id),
  achievement_id INTEGER NOT NULL REFERENCES achievement(id),
  created_at    TEXT NOT NULL,
  provenance    TEXT NOT NULL DEFAULT 'user_fact',
  governance_state TEXT NOT NULL DEFAULT 'user_fact',
  UNIQUE (document_id, achievement_id)
);
-- Ruling: the plain two-column junction shape is superseded by the
-- cross-cutting governance rule (governance applies to every junction row)
-- and by the junction ops (link/verify/reject/unlink target rows by id) —
-- this junction carries the same shape as the others.
CREATE TABLE IF NOT EXISTS achievement_evidence (
  id             INTEGER PRIMARY KEY,
  achievement_id INTEGER NOT NULL REFERENCES achievement(id),
  evidence_id    INTEGER NOT NULL REFERENCES evidence(id),
  created_at     TEXT NOT NULL,
  provenance     TEXT NOT NULL DEFAULT 'user_fact',
  governance_state TEXT NOT NULL DEFAULT 'user_fact',
  UNIQUE (achievement_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS instruction (
  id             INTEGER PRIMARY KEY,
  body           TEXT NOT NULL,         -- the directive as stated (its purpose, not a rule of its own)
  kind           TEXT NOT NULL,         -- priority / preference / constraint / prohibition
  scope_type     TEXT NOT NULL,         -- task / application / company / interview_stage / search_wide / hat
  scope_ref_type TEXT,                  -- the table scope_ref points at: application / company / interview / hat
  scope_ref      INTEGER,               -- the id of the scoped entity; NULL for task / search_wide / hat
  scope_ref_text TEXT,                  -- a non-id scope target: a hat name or a stage label
  stated_date    TEXT NOT NULL,         -- when the user stated it (ISO)
  valid_until    TEXT,                  -- explicit expiry (ISO); NULL = until superseded / withdrawn
  superseded_by  INTEGER REFERENCES instruction(id),
  status         TEXT NOT NULL DEFAULT 'active',  -- suggested / active / superseded / expired / withdrawn
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);
"""


# The flip table: outcome -> application status. None = the event sets no
# status (outreach, profile updates, internal work, claims). Complete against
# the ledger's outcome vocabulary; anything else is refused, never guessed.
FLIP = {
    "Application Submitted": "submitted",
    "Interview Invited": "advanced",
    "Interview Scheduled": "advanced",
    "Phone Screen Scheduled": "advanced",
    "Recruiter Call Scheduled": "advanced",
    "Interview Held": "advanced",
    "Completed": "advanced",
    "AI Voice Interview Completed": "advanced",
    "Round Passed": "advanced",
    "Interest Confirmed": "advanced",
    "Rescheduled": "advanced",
    "Reschedule Confirmed": "advanced",
    "Not Selected": "rejected",
    "Position Filled": "closed",
    "Declined": "closed",
    "Withdrawn": "closed",
    "Closed": "closed",
    "Follow-up \u2014 closure request": "closed",
    "Role Paused": "paused",
    "Outreach": None,
    "Profile Updated": None,
    "Internal In Progress": None,
    "Internal Complete": None,
    "Other": None,
}

def _status_view_sql():
    """The v_application_status view, generated from FLIP (the single source
    of truth for the flip table). Last status-setting event in
    (date_iso, id) order — the v1 ordering, exactly as the legacy
    derivation ran it — plus the last activity: the newest event of any
    kind, neutral included. The status derives from status-setting
    events only; the activity is a second, wider read."""
    cases, setting = [], []
    for outcome, st in FLIP.items():
        if st is None:
            continue
        esc = outcome.replace("'", "''")
        cases.append("    WHEN '%s' THEN '%s'" % (esc, st))
        setting.append("'%s'" % esc)
    return (
        "CREATE VIEW v_application_status AS "
        "SELECT a.id AS application_id, c.name AS company, a.role, "
        "e.outcome AS last_outcome, e.date_iso AS status_date, "
        "e.id AS last_event_id, "
        "CASE e.outcome\n" + "\n".join(cases) + "\n  END AS status, "
        "ea.id AS activity_event_id, ea.type AS activity_type, "
        "ea.outcome AS activity_outcome "
        "FROM application a "
        "JOIN company c ON c.id = a.company_id "
        "LEFT JOIN event e ON e.application_id = a.id "
        "AND e.id = (SELECT e2.id FROM event e2 "
        "WHERE e2.application_id = a.id "
        "AND e2.outcome IN (" + ", ".join(setting) + ") "
        # both DESC: the last event in (date_iso, id) order. A bare
        # 'date_iso, id DESC' would sort the date ASC — the DESC binds to
        # the last term only. The activity join has the same shape minus
        # the outcome filter — any kind, neutral included.
        "ORDER BY e2.date_iso DESC, e2.id DESC LIMIT 1) "
        "LEFT JOIN event ea ON ea.application_id = a.id "
        "AND ea.id = (SELECT e3.id FROM event e3 "
        "WHERE e3.application_id = a.id "
        "ORDER BY e3.date_iso DESC, e3.id DESC LIMIT 1)"
    )


REQ_RE = re.compile(r"req #?(\d+)")


def company_key(company):
    """The company key: the Company/Contact value before ' / ' (the contact
    name and any URL never enter the key). 'n/a' stays 'n/a'."""
    if company == "n/a":
        return "n/a"
    return company.split(" / ")[0].strip()


def _derived_state_hash(conn, seed):
    """Hash a derived object's rebuild inputs: the seed statements plus, for
    each indexed entity, the exact indexed text per row (the fill's input),
    in id order. The rebuild fires exactly when the fill input changes —
    appends and in-place edits alike. The store is small; the probe cost is
    a full read of the indexed columns, which is cheap at this scale."""
    h = hashlib.sha256()
    for part in seed:
        h.update(part.encode("utf-8"))
    for entity, cols in SEARCHED_COLUMNS.items():
        text = " || ' ' || ".join("IFNULL(%s, '')" % (c,) for c in cols)
        for row in conn.execute(
                "SELECT id, %s FROM %s ORDER BY id" % (text, entity)):
            h.update(("%s:%s:%s" % (entity, row[0], row[1])).encode("utf-8"))
    return h.hexdigest()


def _meta_value(conn, key):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _meta_put(conn, key, value):
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value))


def _rebuild_derived(conn, meta_key, hash_value, statements):
    """Rebuild a derived object only when its hash differs from the stored
    one. The drop/create runs under the write lock (BEGIN IMMEDIATE) with
    the busy timeout armed, so concurrent opens wait their turn instead of
    interleaving a drop with another's create."""
    if _meta_value(conn, meta_key) == hash_value:
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        for sql in statements:
            conn.execute(sql)
        _meta_put(conn, meta_key, hash_value)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def db_connect(db_path):
    """Open (creating if needed) the store db with WAL on, the busy timeout
    armed, and the schema present. Derived state (the status view, the FTS
    index) is rebuilt only when its definition or data changed — never a
    blind drop/create on every open."""
    p = pathlib.Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA)
    # the view is derived state — generated from FLIP so the flip table
    # stays single-sourced; rebuilt only when the definition changed
    view_sql = _status_view_sql()
    _rebuild_derived(conn, "view_hash",
                     hashlib.sha256(view_sql.encode("utf-8")).hexdigest(),
                     ["DROP VIEW IF EXISTS v_application_status", view_sql])
    # the FTS index is derived state — rebuilt only when the indexed data
    # changed; the fill's commit makes it durable so the query service's
    # separate read-only connection sees it
    si_hash = _derived_state_hash(
        conn, [_search_index_ddl(), _search_index_fill()])
    _rebuild_derived(conn, "search_index_hash", si_hash,
                     ["DROP TABLE IF EXISTS search_index",
                      _search_index_ddl(), _search_index_fill()])
    conn.commit()
    return conn


def to_iso(date):
    """'3/1/2026' -> '2026-03-01'. Raises ValueError on anything else."""
    parts = date.split("/")
    if len(parts) != 3:
        raise ValueError("bad date %r (want M/D/YYYY)" % (date,))
    m, d, y = parts
    if not (m.isdigit() and d.isdigit() and y.isdigit()):
        raise ValueError("bad date %r (want M/D/YYYY)" % (date,))
    if not (1 <= int(m) <= 12 and 1 <= int(d) <= 31 and len(y) == 4):
        raise ValueError("bad date %r (want M/D/YYYY)" % (date,))
    return "%s-%02d-%02d" % (y, int(m), int(d))


# PII refusals for new writes. The phone patterns are context-bounded so long
# digit runs inside links (job ids) don't trip them: a separated phone
# (415-555-0100, 415.555.0100, (415) 555 0100) always trips; a bare 10-digit
# run trips only outside a URL context (not right after / = or :). The
# migration takes historical data as-is; only log-event / log-run run this
# gate.
PII_PATTERNS = [
    ("a phone number", re.compile(r"(?<!\d)\d{3}[-.\s]\d{3}[-.\s]?\d{4}(?!\d)")),
    ("a phone number", re.compile(r"\(\d{3}\)[-. ]?\d{3}[-. ]?\d{4}")),
    ("a phone number", re.compile(r"(?<![\d/=:])\d{10}(?!\d)")),
    ("a local path", re.compile(r"/Users/|/Volumes/|~/Documents")),
    ("an evidence id", re.compile(r"EVID-\d+")),
]


def check_pii(text, what):
    for name, rx in PII_PATTERNS:
        m = rx.search(text)
        if m:
            raise ValueError(
                "refused: %s (%r) in %s" % (name, m.group(0), what)
            )


def format_tsv_row(fields):
    """Serialize fields to one TSV line: quote only when a field contains a
    tab, a double-quote, or a newline (QUOTE_MINIMAL with a tab delimiter)."""
    out = []
    for f in fields:
        if any(c in f for c in ("\t", '"', "\n")):
            out.append('"' + f.replace('"', '""') + '"')
        else:
            out.append(f)
    return "\t".join(out)


def parse_tsv_line(line):
    """Parse one TSV line into a list of field values.

    Handles the house formats: quoted fields with "" doubling, gratuitously
    quoted fields (quoted with no trigger char), and unquoted fields that
    contain commas or double-quotes. A field starting with a double-quote is
    read as quoted; everything else is read to the next tab.
    """
    fields = []
    i, n = 0, len(line)
    while True:
        if i < n and line[i] == '"':
            i += 1
            buf = []
            while i < n:
                if line[i] == '"':
                    if i + 1 < n and line[i + 1] == '"':
                        buf.append('"')
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    buf.append(line[i])
                    i += 1
            fields.append("".join(buf))
        else:
            buf = []
            while i < n and line[i] != "\t":
                buf.append(line[i])
                i += 1
            fields.append("".join(buf))
        if i < n and line[i] == "\t":
            i += 1
            continue
        break
    return fields


def read_tsv(path):
    """Return (header_line, [raw data lines]) — raw, unmodified, no newlines."""
    raw = pathlib.Path(path).read_bytes().decode("utf-8")
    if raw.endswith("\n"):
        raw = raw[:-1]
    lines = raw.split("\n")
    if not lines:
        raise ValueError("empty file: %s" % (path,))
    return lines[0], lines[1:]


def write_atomic(out_path, data):
    """Write bytes via a temp file in the target dir, then replace (sync-safe)."""
    out_path = pathlib.Path(out_path)
    fd, tmp = tempfile.mkstemp(dir=str(out_path.parent), prefix=".store-tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, out_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _find_application(conn, company_raw, role):
    """The application for (company key, role), or None — read-only. The
    role is compared after strip on both sides: whitespace drift is not a
    new application."""
    key = company_key(company_raw)
    if key == "n/a" or role == "n/a":
        return None
    row = conn.execute(
        "SELECT a.id FROM application a "
        "JOIN company c ON a.company_id = c.id "
        "WHERE LOWER(c.name) = LOWER(?) AND TRIM(a.role) = ?",
        (key, role.strip())).fetchone()
    return row[0] if row else None


def _resolve_application(conn, company_raw, role):
    """Create-or-reuse the application for (company key, role) — the v1
    thread-creation behavior, on the entity. company_raw is the value as
    recorded (it may carry a ' / ' contact part); the key is computed here,
    so an already-keyed value passes through unchanged. The stored role is
    the stripped form; the lookup tolerates whitespace drift.
    Returns the application id, or None for the n/a pairs (they have no
    application)."""
    existing = _find_application(conn, company_raw, role)
    if existing is not None:
        return existing
    key = company_key(company_raw)
    if key == "n/a" or role == "n/a":
        return None
    # A case-drifted key reuses the existing company: the ledger's
    # vocabulary is case-insensitive, so "globex" is not a second
    # company next to "Globex".
    row = conn.execute(
        "SELECT id FROM company WHERE LOWER(name) = LOWER(?)",
        (key,)).fetchone()
    cid = row[0] if row else _upsert(conn, "company", {"name": key}, {}, {})
    cur = conn.execute(
        "INSERT INTO application (company_id, role, created_at) "
        "VALUES (?, ?, ?)", (cid, role.strip(), _today_iso()))
    return cur.lastrowid


def _event_application(conn, company_raw, role, outcome):
    """The application link for an event: every event whose
    (company key, role) matches an existing application is linked to it,
    regardless of outcome; an application is created only when the
    outcome sets a status (the flip's None semantics kept for status).
    Returns the application id, or None (n/a pairs, or a neutral event
    with no application yet)."""
    if FLIP[outcome] is not None:
        return _resolve_application(conn, company_raw, role)
    return _find_application(conn, company_raw, role)


def _link_orphans(conn):
    """Backfill: set application_id on every event that has no link
    but whose (company_key, role) matches an existing application. Role
    compared after strip; on a match the oldest application wins (a
    whitespace-drift duplicate is not the record). The link column
    is repairable; raw_row is untouched, so the ledger's exports stay
    byte-stable. Returns the number of events linked."""
    match = ("SELECT MIN(a.id) FROM application a "
             "JOIN company c ON a.company_id = c.id "
             "WHERE LOWER(c.name) = LOWER(event.company_key) "
             "AND TRIM(a.role) = TRIM(event.role)")
    cur = conn.execute(
        "UPDATE event SET application_id = (" + match + ") "
        "WHERE application_id IS NULL "
        "AND company_key != 'n/a' AND TRIM(role) != 'n/a' "
        "AND EXISTS (" + match.replace("MIN(a.id)", "1") + ")")
    return cur.rowcount


def repair(db_path):
    """One-shot backfill: link every orphaned event to
    its application on (company key, role) match. The events are
    append-only as to content; the link column is repairable. The ledger's
    raw rows are untouched, so the export is byte-stable. Idempotent — a
    second run links nothing. Returns {"linked": int}."""
    conn = db_connect(db_path)
    try:
        with conn:
            return {"linked": _link_orphans(conn)}
    finally:
        conn.close()


LOG_HEADER = "Date\tTask\tAction\tDecision\tNext"


def migrate(db_path, ledger_path, logs_dir=None):
    """One-shot: the ledger TSV (and optionally the hat log TSVs) in, the db
    out. Fails closed (unknown shape, unknown outcome, malformed date —
    nothing is written when it raises) and refuses a non-empty db. Headers
    are captured into meta; every row is stored with its exact raw line so
    exports are byte-stable. A row whose (company key, role) matches an
    existing application is linked to it, regardless of outcome; a
    row whose outcome sets a status creates the application if there is
    none, in first-status-event order (the v1 thread order); a final
    backfill pass links the neutral rows that precede their pair's first
    status-setting row. A 4-field log row (missing trailing empty Next) is
    padded with next=''; any other shape fails.
    Returns {"events": int, "applications": int, "run_logs": int}.
    """
    conn = db_connect(db_path)
    try:
        n = conn.execute("SELECT COUNT(*) FROM event").fetchone()[0]
        if n:
            raise ValueError("refusing to migrate into a non-empty db (%d events)" % n)
        with conn:  # one transaction: all or nothing
            header, rows = read_tsv(ledger_path)
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('ledger_header', ?)", (header,)
            )
            for raw in rows:
                fields = parse_tsv_line(raw)
                if len(fields) != 7:
                    raise ValueError(
                        "ledger row does not have 7 fields: %r" % (raw[:80],)
                    )
                date, etype, company, role, channel, outcome, note = fields
                to_iso(date)  # validate
                if outcome not in FLIP:
                    raise ValueError(
                        "unknown outcome %r (row: %r)" % (outcome, raw[:80])
                    )
                app_id = _event_application(conn, company, role, outcome)
                conn.execute(
                    "INSERT INTO event "
                    "(date, date_iso, type, application_id, company_key, "
                    "role, channel, outcome, note, raw_row, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (date, to_iso(date), etype, app_id, company_key(company),
                     role, channel, outcome, note, raw, _today_iso()),
                )
            # a neutral row can precede the pair's first
            # status-setting row in the ledger — the one backfill pass
            # links those orphans to the applications the load created.
            _link_orphans(conn)
            if logs_dir is not None:
                for log_path in sorted(pathlib.Path(logs_dir).glob("*.tsv")):
                    hat = log_path.stem
                    lheader, lrows = read_tsv(log_path)
                    conn.execute(
                        "INSERT INTO meta (key, value) VALUES (?, ?)",
                        ("log_header:" + hat, lheader),
                    )
                    for raw in lrows:
                        fields = parse_tsv_line(raw)
                        if len(fields) == 4:
                            fields = fields + [""]
                        if len(fields) != 5:
                            raise ValueError(
                                "log row for %s does not have 5 fields: %r"
                                % (hat, raw[:80])
                            )
                        ldate, task, action, decision, nxt = fields
                        to_iso(ldate)  # validate
                        conn.execute(
                            "INSERT INTO run_logs "
                            "(hat, date, date_iso, task, action, decision, next, raw_row) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (hat, ldate, to_iso(ldate), task, action, decision, nxt, raw),
                        )
        counts = {
            "events": conn.execute("SELECT COUNT(*) FROM event").fetchone()[0],
            "applications": conn.execute(
                "SELECT COUNT(*) FROM application").fetchone()[0],
            "run_logs": conn.execute(
                "SELECT COUNT(*) FROM run_logs").fetchone()[0],
        }
        return counts
    finally:
        conn.close()


def migrate_applications(db_path):
    """One-shot upgrade for a pre-Phase-2 db: the legacy event rows are
    copied onto the new event table keyed on application (ids preserved —
    insertion order is the ledger row number), the application rows are
    created for the legacy thread set, the thread-scoped instructions are
    remapped to the new application ids (scope_ref_type renamed to
    'application'), and the legacy tables are dropped — after the ledger's
    raw rows are verified byte-identical between the two tables. One
    transaction; nothing is written on refusal. Refuses a non-empty new
    event table; a clean no-op when the legacy tables are absent. Returns
    {"applications", "events", "instructions_remapped", "dropped"}."""
    conn = db_connect(db_path)
    try:
        has_legacy = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'events'").fetchone()
        n_legacy = conn.execute(
            "SELECT COUNT(*) FROM events").fetchone()[0] if has_legacy else 0
        # No legacy data to migrate (no legacy tables at all, or empty
        # ones — a fresh db still carries the empty legacy tables until
        # their DDL leaves the schema): a no-op, nothing dropped, so the
        # op's result is the same either way.
        if has_legacy is None or n_legacy == 0:
            return {"applications": 0, "events": 0,
                    "instructions_remapped": 0, "dropped": []}
        n_new = conn.execute("SELECT COUNT(*) FROM event").fetchone()[0]
        if n_new:
            raise ValueError(
                "refusing to migrate: the new event table already holds %d "
                "row(s)" % n_new)
        with conn:  # one transaction: all or nothing
            threads = conn.execute(
                "SELECT id, company, role FROM threads ORDER BY id"
            ).fetchall()
            mapping = {}
            for tid, company, role in threads:
                mapping[tid] = _resolve_application(conn, company, role)
            events = conn.execute(
                "SELECT id, date, date_iso, type, company, role, channel, "
                "outcome, note, raw_row FROM events ORDER BY id").fetchall()
            for (eid, date, d_iso, etype, company, role, channel, outcome,
                 note, raw) in events:
                conn.execute(
                    "INSERT INTO event (id, date, date_iso, type, "
                    "application_id, company_key, role, channel, outcome, "
                    "note, raw_row, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (eid, date, d_iso, etype,
                     _event_application(conn, company, role, outcome),
                     company_key(company), role, channel,
                     outcome, note, raw, _today_iso()))
            # the legacy rows carried thread links only on the
            # thread's own rows — the backfill gives every row whose
            # pair matches an application its link.
            _link_orphans(conn)
            remapped = 0
            for tid, app_id in mapping.items():
                cur = conn.execute(
                    "UPDATE instruction SET scope_ref = ?, "
                    "scope_ref_type = 'application', updated_at = ? "
                    "WHERE scope_ref_type = 'thread' AND scope_ref = ?",
                    (app_id, _today_iso(), tid))
                remapped += cur.rowcount
            old_rows = [r[0] for r in conn.execute(
                "SELECT raw_row FROM events ORDER BY date_iso, id")]
            new_rows = [r[0] for r in conn.execute(
                "SELECT raw_row FROM event ORDER BY date_iso, id")]
            if old_rows != new_rows:
                raise ValueError(
                    "refusing to drop the legacy tables: the ledger's raw "
                    "rows are not byte-identical between the two tables")
            conn.execute("DROP TABLE threads")
            conn.execute("DROP TABLE events")
            return {
                "applications": len(mapping),
                "events": len(events),
                "instructions_remapped": remapped,
                "dropped": ["threads", "events"],
            }
    finally:
        conn.close()


def export_ledger(db_path, out_path):
    """Regenerate the ledger TSV: the meta header + every stored raw_row, verbatim."""
    conn = db_connect(db_path)
    try:
        header = conn.execute(
            "SELECT value FROM meta WHERE key = 'ledger_header'"
        ).fetchone()
        if header is None:
            raise ValueError("no ledger header in db (was migrate run?)")
        rows = [
            r[0]
            for r in conn.execute(
                "SELECT raw_row FROM event ORDER BY date_iso, id"
            ).fetchall()
        ]
    finally:
        conn.close()
    data = "\n".join([header[0]] + rows) + "\n"
    write_atomic(out_path, data.encode("utf-8"))


def log_event(db_path, date, etype, company, role, channel, outcome, note,
              url=None):
    """Append an event, linked to its application: the (company key, role)
    match resolves regardless of outcome, and the application is
    created only when the outcome sets a status — one transaction, one op.
    With url, the posting is upserted in the same op (key: company + role
    as title + the link — the link is the duplicate key) and attached to
    the application when the link slot is free. The
    validations run before any write: a refusal (a PII pattern in the note,
    an unknown outcome, a malformed date) leaves nothing behind, no
    application/company side effects included. Returns the new event id.
    """
    to_iso(date)
    if outcome not in FLIP:
        raise ValueError("unknown outcome %r" % (outcome,))
    check_pii(note, "the note")
    conn = db_connect(db_path)
    try:
        with conn:
            # link the event to its application whenever the
            # (company key, role) matches — neutral outcomes included;
            # create the application only when the outcome sets a status.
            app_id = _event_application(conn, company, role, outcome)
            if url is not None:
                # the posting's link is the duplicate key: upsert the
                # posting in the same op and attach it to the
                # application when the link slot is free
                jo_id = _job_opening_upsert(
                    conn, company_key(company), role, url, {})
                if app_id is not None:
                    conn.execute(
                        "UPDATE application SET job_opening_id = ? "
                        "WHERE id = ? AND job_opening_id IS NULL",
                        (jo_id, app_id))
            cur = conn.execute(
                "INSERT INTO event "
                "(date, date_iso, type, application_id, company_key, role, "
                "channel, outcome, note, raw_row, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (date, to_iso(date), etype, app_id, company_key(company),
                 role, channel, outcome, note,
                 format_tsv_row([date, etype, company, role, channel,
                                 outcome, note]),
                 _today_iso()),
            )
            return cur.lastrowid
    finally:
        conn.close()


def log_run(db_path, hat, date, task, action, decision, next_field):
    """Append a hat log row. Refuses PII patterns in any field; nothing is
    written when it refuses. Returns the new row id."""
    to_iso(date)
    for what, value in (("task", task), ("action", action),
                        ("decision", decision), ("next", next_field)):
        check_pii(value, what)
    conn = db_connect(db_path)
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO run_logs "
                "(hat, date, date_iso, task, action, decision, next, raw_row) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (hat, date, to_iso(date), task, action, decision, next_field,
                 format_tsv_row([date, task, action, decision, next_field])),
            )
            return cur.lastrowid
    finally:
        conn.close()


def pickup(db_path, hat):
    """That hat's last row: (date, task, action, decision, next), or None."""
    conn = db_connect(db_path)
    try:
        return conn.execute(
            "SELECT date, task, action, decision, next FROM run_logs "
            "WHERE hat = ? ORDER BY id DESC LIMIT 1",
            (hat,),
        ).fetchone()
    finally:
        conn.close()


def export_logs(db_path, out_dir):
    """Regenerate each hat's log TSV from run_logs: the meta header (or the
    mechanism default) + every stored raw_row, verbatim. Returns the paths
    written."""
    conn = db_connect(db_path)
    try:
        headers = dict(conn.execute(
            "SELECT key, value FROM meta WHERE key LIKE 'log_header:%'"
        ).fetchall())
        rows = conn.execute(
            "SELECT hat, raw_row FROM run_logs ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    by_hat = {}
    for hat, raw in rows:
        by_hat.setdefault(hat, []).append(raw)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    hats = {k.split(":", 1)[1] for k in headers} | set(by_hat)
    for hat in sorted(hats):
        header = headers.get("log_header:" + hat, LOG_HEADER)
        p = out_dir / (hat + ".tsv")
        write_atomic(p, ("\n".join([header] + by_hat.get(hat, [])) + "\n").encode("utf-8"))
        written.append(p)
    return written


LIVE_STATE_RE = re.compile(r"\*\*Live state \((\d{1,2}/\d{1,2}/\d{4})\)\.?\*\*")


def _read_text(path):
    """The file's text, or '' when the file does not exist (missing state
    files are drift, never a crash)."""
    p = pathlib.Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def _company_part(name_line):
    """The company part of a QA section or cast line: the text before the
    first ' — ' separator; a line without the separator is its own part.
    Markdown emphasis is stripped (narrative files may bold the name)."""
    return name_line.split(" — ")[0].replace("*", "").strip()


def _names_match(key, name):
    """Bidirectional, case-insensitive: the key names the narrative company
    or the narrative name names the key. Naming drift (suffixes, wrappers)
    is not drift; a company sharing no name at all is."""
    k, n = key.lower(), name.lower()
    return bool(n) and (k in n or n in k)


def divergence(db_path, qa_path, cast_path, hubs_dir=None):
    """Check the markdown state files against application state (the derived
    status view). Returns drift descriptions (empty = clean); the CLI exits
    non-zero on drift.

    v1 checks:
      1. QA presence — every company with >=1 Application Submitted event has
         a '## ' section naming it in the QA file.
      2. Hub recency — for each advanced application whose company has
         <hubs>/<company>/README.md, the hub's '**Live state (M/D/YYYY)**'
         date >= the application's status date. A missing hub is not drift
         (a round may not be live yet); a stale or malformed hub is.
      3. Cast naming — every advanced/rejected/closed application's company
         is named in the cast file.
     A naming match is bidirectional and case-insensitive: a section or
     line's company part names a store key when either contains the other
     — naming drift is not drift, a company sharing no name at all is.
    """
    conn = db_connect(db_path)
    try:
        apps = conn.execute(
            "SELECT company, role, status, status_date, last_event_id "
            "FROM v_application_status ORDER BY application_id"
        ).fetchall()
        dates = dict(conn.execute("SELECT id, date FROM event").fetchall())
        applied = {
            c for (c,) in conn.execute(
                "SELECT company_key FROM event "
                "WHERE outcome = 'Application Submitted' "
                "AND company_key != 'n/a'")
        }
    finally:
        conn.close()

    drift = []

    # 1. QA presence
    qa_text = _read_text(qa_path)
    sections = [_company_part(ln[3:]) for ln in qa_text.split("\n")
                if ln.startswith("## ")]
    for comp in sorted(applied):
        if not any(_names_match(comp, s) for s in sections):
            drift.append("qa: no '## ' section naming %r" % (comp,))

    # 3. Cast naming (per company: one naming covers all of its applications)
    cast_names = [_company_part(ln[2:])
                  for ln in _read_text(cast_path).split("\n")
                  if ln.startswith("- ")]
    cast_targets = sorted({
        company for company, _role, st, _sd_iso, _le in apps
        if st in ("advanced", "rejected", "closed")
    })
    for company in cast_targets:
        if not any(_names_match(company, n) for n in cast_names):
            drift.append("cast: %r not named" % (company,))

    # 2. Hub recency
    if hubs_dir is not None:
        hubs_dir = pathlib.Path(hubs_dir)
        for company, role, st, sd_iso, le in apps:
            if st != "advanced":
                continue
            readme = hubs_dir / company / "README.md"
            if not readme.exists():
                continue
            m = LIVE_STATE_RE.search(readme.read_text(encoding="utf-8"))
            if m is None:
                drift.append(
                    "hub: %s hub has no '**Live state (M/D/YYYY)**' line" % (company,)
                )
                continue
            if to_iso(m.group(1)) < sd_iso:
                drift.append(
                    "hub: %s hub dated %s is older than %s status date %s"
                    % (company, m.group(1), role, dates.get(le))
                )
    return drift


def export_claim(db_path, date_from, date_to, out_path=None):
    """The benefit-claim one-pager over the inclusive range: one line per event,
    '{date}  {company key}  {role}  [{type}]', sorted by (date_iso, id).
    The company key never the contact name or URL (third-party-safe).
    Writes to out_path (atomically) when given; returns the text either way.
    """
    d1, d2 = to_iso(date_from), to_iso(date_to)
    conn = db_connect(db_path)
    try:
        rows = conn.execute(
            "SELECT date, company_key, role, type FROM event "
            "WHERE date_iso >= ? AND date_iso <= ? ORDER BY date_iso, id",
            (d1, d2),
        ).fetchall()
    finally:
        conn.close()
    lines = [
        "%s  %s  %s  [%s]" % (date, key, role, etype)
        for date, key, role, etype in rows
    ]
    text = ("\n".join(lines) + "\n") if lines else ""
    if out_path is not None:
        write_atomic(out_path, text.encode("utf-8"))
    return text


def status(db_path, company=None, live=False):
    """Application states: (company, role, status, status_date, req,
    last_event_id, activity_date, activity_type, activity_outcome) in
    application-id order. The status is derived (the view over the
    application's events) from status-setting events only; status_date is
    the as-recorded date of the last status-setting event (None when it
    has none); req is the first 'req #?digits' among the application's
    status-setting events in (date_iso, id) order (the v1 derivation).
    The activity triple is the as-recorded date, type, and outcome of
    the newest event of any kind — neutral included (None when it has
    none). --live excludes rejected / closed; a NULL status passes
    --live."""
    conn = db_connect(db_path)
    try:
        rows = conn.execute(
            "SELECT application_id, company, role, status, last_event_id, "
            "activity_event_id, activity_type, activity_outcome "
            "FROM v_application_status ORDER BY application_id"
        ).fetchall()
        dates = dict(conn.execute("SELECT id, date FROM event").fetchall())
        setting = ",".join(
            "'%s'" % o.replace("'", "''")
            for o, st in FLIP.items() if st is not None)
        reqs = {}
        for aid, note in conn.execute(
                "SELECT application_id, note FROM event "
                "WHERE outcome IN (%s) AND application_id IS NOT NULL "
                "ORDER BY application_id, date_iso, id" % setting):
            if aid in reqs:
                continue
            m = REQ_RE.search(note)
            if m:
                reqs[aid] = m.group(1)
        out = []
        for aid, comp, role, st, le, ae, at, ao in rows:
            if company and comp.lower() != company.lower():
                continue
            if live and st in ("rejected", "closed"):
                continue
            out.append((comp, role, st, dates.get(le), reqs.get(aid), le,
                        dates.get(ae), at, ao))
        return out
    finally:
        conn.close()


def caps(db_path, company=None):
    """Application counts per company key: [(company, count)] by count desc,
    then company asc. Companies with no applications are absent."""
    conn = db_connect(db_path)
    try:
        rows = conn.execute(
            "SELECT company_key FROM event "
            "WHERE outcome = 'Application Submitted'"
        ).fetchall()
    finally:
        conn.close()
    counts = {}
    for (k,) in rows:
        counts[k] = counts.get(k, 0) + 1
    if company:
        counts = {k: v for k, v in counts.items() if k.lower() == company.lower()}
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def near_companies(db_path, name):
    """Company names near `name` that are not a case-insensitive match of
    it — the no-match companion to the case-insensitive filters: a typo or
    wrong-case key surfaces the candidates instead of a silent empty
    result. Close matches first (difflib, cutoff 0.6), then substring
    matches; deduped, at most 5, canonical spellings as stored."""
    conn = db_connect(db_path)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM company ORDER BY name").fetchall()]
    finally:
        conn.close()
    low = name.lower()
    names = [n for n in names if n.lower() != low]
    out = []
    for n in difflib.get_close_matches(name, names, n=5, cutoff=0.6):
        if n not in out:
            out.append(n)
    for n in names:
        if len(out) == 5:
            break
        if low in n.lower() or n.lower() in low:
            out.append(n)
    return out[:5]


# ---- Operational entity ops (Phase 2) --------------------------------------
# Ungoverned (the shipped DDL carries no provenance columns); M/D/YYYY
# inputs are stored ISO; target companies / contacts must already exist
# (the ledger's vocabulary is the source of target companies — only
# log-event and the migrations auto-create).

JOB_OPENING_STATUSES = ("open", "applied", "closed")
INTERVIEW_KINDS = ("recruiter", "technical", "system", "onsite", "ai_voice")
INTERVIEW_STATUSES = ("pending", "scheduled", "held", "passed", "failed")
INTERACTION_KINDS = ("email", "call", "meet", "post")
INTERACTION_DIRECTIONS = ("in", "out")


def _company_id_or_refuse(conn, company):
    """Resolve a company by exact name; refuse (naming the missing name)
    when it does not exist."""
    row = conn.execute(
        "SELECT id FROM company WHERE name = ?", (company,)).fetchone()
    if row is None:
        raise ValueError("no company named %r" % (company,))
    return row[0]


def _contact_id_or_refuse(conn, contact):
    row = conn.execute(
        "SELECT id FROM contact WHERE name = ?", (contact,)).fetchone()
    if row is None:
        raise ValueError("no contact named %r" % (contact,))
    return row[0]


def upsert_contact(db_path, name, title=None, company=None, email=None,
                   linkedin_ref=None, how_met=None):
    """Create-or-verify a contact row keyed by name (exact). `company` is
    by name and must exist. Returns the row id."""
    conn = db_connect(db_path)
    try:
        with conn:
            provided = {"name": name}
            for col, val in (("title", title), ("email", email),
                             ("linkedin_ref", linkedin_ref),
                             ("how_met", how_met)):
                if val is not None:
                    provided[col] = val
            if company is not None:
                provided["company_id"] = _company_id_or_refuse(conn, company)
            return _upsert(conn, "contact", {"name": name}, provided, {})
    finally:
        conn.close()


def upsert_job_opening(db_path, company, title, location=None, work_mode=None,
                       source=None, url=None, posted_date=None,
                       posted_comp=None, jd_ref=None, status=None):
    """Create-or-verify a job opening keyed by (company, title, url) — the
    posting's link is the duplicate key: the
    same title at the same company can carry several postings, one per
    link. The legacy form (no url) resolves the unambiguous title (zero
    or one posting) and refuses — naming every link — when the title
    carries several. The company must exist. status is enum-validated
    (open / applied / closed), default 'open'. posted_date is M/D/YYYY
    as stated, stored ISO. Returns the row id."""
    if status is not None and status not in JOB_OPENING_STATUSES:
        raise ValueError("bad status %r (want one of: %s)"
                         % (status, ", ".join(JOB_OPENING_STATUSES)))
    if posted_date is not None:
        posted_date = to_iso(posted_date)
    conn = db_connect(db_path)
    try:
        with conn:
            extra = {}
            for col, val in (("location", location),
                             ("work_mode", work_mode),
                             ("source", source),
                             ("posted_date", posted_date),
                             ("posted_comp", posted_comp),
                             ("jd_ref", jd_ref), ("status", status)):
                if val is not None:
                    extra[col] = val
            return _job_opening_upsert(conn, company, title, url, extra)
    finally:
        conn.close()


def _job_opening_upsert(conn, company_key_value, title, url, provided_extra):
    """The conn-level core of upsert_job_opening (key: company + title +
    url — the link is the duplicate key; the legacy no-url form resolves
    the unambiguous title and refuses the ambiguous one, naming every
    link). company_key_value is the company key as the caller holds it;
    provided_extra carries the non-key fields for the create-or-verify.
    Returns the row id."""
    cid = _company_id_or_refuse(conn, company_key_value)
    if url is None:
        rows = conn.execute(
            "SELECT id, url FROM job_opening "
            "WHERE company_id = ? AND title = ? ORDER BY id",
            (cid, title)).fetchall()
        if len(rows) > 1:
            raise ValueError(
                "refusing to upsert job opening (%s, %r) without a url: "
                "%d postings share the title (%s) — pass --url to name "
                "the posting"
                % (company_key_value, title, len(rows),
                   ", ".join(r[1] or "(no link)" for r in rows)))
    provided = {"company_id": cid, "title": title}
    key_cols = {"company_id": cid, "title": title}
    if url is not None:
        provided["url"] = url
        key_cols["url"] = url
    provided.update(provided_extra)
    return _upsert(conn, "job_opening", key_cols, provided,
                   {"status": "open"})


def upsert_application(db_path, company, role, job_opening_id=None,
                       contact=None, applied_date=None):
    """Create-or-verify an application keyed by (company, role) — the same
    key the ledger path uses, so a typed call reuses the application a
    status-setting event created. The company (and `contact`, by name)
    must exist. Stored NULLs (job_opening_id, contact_id, applied_date)
    may be filled by a re-run. Returns the row id."""
    if applied_date is not None:
        applied_date = to_iso(applied_date)
    conn = db_connect(db_path)
    try:
        with conn:
            cid = _company_id_or_refuse(conn, company)
            provided = {"company_id": cid, "role": role}
            if job_opening_id is not None:
                provided["job_opening_id"] = job_opening_id
            if contact is not None:
                provided["contact_id"] = _contact_id_or_refuse(conn, contact)
            if applied_date is not None:
                provided["applied_date"] = applied_date
            return _upsert(conn, "application",
                           {"company_id": cid, "role": role}, provided, {},
                           stamps=("created_at",))
    finally:
        conn.close()


def interview(db_path, application_id, round, kind=None, scheduled_at=None,
              status=None, feedback_ref=None):
    """Create-or-verify an interview row keyed by (application_id, round).
    The application must exist. kind is enum-validated; status is
    enum-validated with default 'pending' and provided at creation only —
    a later call providing a different status is a conflict refusal (the
    lifecycle mutation is set-interview). scheduled_at is M/D/YYYY as
    stated, stored ISO. Returns the row id."""
    if kind is not None and kind not in INTERVIEW_KINDS:
        raise ValueError("bad kind %r (want one of: %s)"
                         % (kind, ", ".join(INTERVIEW_KINDS)))
    if status is not None and status not in INTERVIEW_STATUSES:
        raise ValueError("bad status %r (want one of: %s)"
                         % (status, ", ".join(INTERVIEW_STATUSES)))
    if scheduled_at is not None:
        scheduled_at = to_iso(scheduled_at)
    conn = db_connect(db_path)
    try:
        with conn:
            app = conn.execute(
                "SELECT id FROM application WHERE id = ?",
                (application_id,)).fetchone()
            if app is None:
                raise ValueError("no application with id %d" % (application_id,))
            provided = {"application_id": application_id, "round": round}
            for col, val in (("kind", kind), ("scheduled_at", scheduled_at),
                             ("status", status),
                             ("feedback_ref", feedback_ref)):
                if val is not None:
                    provided[col] = val
            return _upsert(conn, "interview",
                           {"application_id": application_id, "round": round},
                           provided, {"status": "pending"})
    finally:
        conn.close()


def set_interview(db_path, row_id, status):
    """The only interview status mutation. Enum-validated; refuses a
    missing row."""
    if status not in INTERVIEW_STATUSES:
        raise ValueError("bad status %r (want one of: %s)"
                         % (status, ", ".join(INTERVIEW_STATUSES)))
    conn = db_connect(db_path)
    try:
        with conn:
            row = conn.execute(
                "SELECT status FROM interview WHERE id = ?",
                (row_id,)).fetchone()
            if row is None:
                raise ValueError("no interview with id %d" % (row_id,))
            conn.execute(
                "UPDATE interview SET status = ?, updated_at = ? "
                "WHERE id = ?", (status, _today_iso(), row_id))
    finally:
        conn.close()


def add_interaction(db_path, kind, direction, occurred_at, contact=None,
                    company=None, application_id=None, summary=None):
    """Insert an interaction row (insert-only — the table has no
    updated_at and no natural key). kind is email / call / meet / post,
    direction in / out; the targets (contact by name, company by name,
    application by id) must exist. occurred_at is M/D/YYYY as stated,
    stored ISO. Returns the row id."""
    if kind not in INTERACTION_KINDS:
        raise ValueError("bad kind %r (want one of: %s)"
                         % (kind, ", ".join(INTERACTION_KINDS)))
    if direction not in INTERACTION_DIRECTIONS:
        raise ValueError("bad direction %r (want one of: %s)"
                         % (direction, ", ".join(INTERACTION_DIRECTIONS)))
    occurred_at = to_iso(occurred_at)
    conn = db_connect(db_path)
    try:
        with conn:
            contact_id = (_contact_id_or_refuse(conn, contact)
                          if contact is not None else None)
            company_id = (_company_id_or_refuse(conn, company)
                          if company is not None else None)
            if application_id is not None:
                app = conn.execute(
                    "SELECT id FROM application WHERE id = ?",
                    (application_id,)).fetchone()
                if app is None:
                    raise ValueError(
                        "no application with id %d" % (application_id,))
            cur = conn.execute(
                "INSERT INTO interaction (kind, direction, occurred_at, "
                "contact_id, company_id, application_id, summary, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (kind, direction, occurred_at, contact_id, company_id,
                 application_id, summary, _today_iso()))
            return cur.lastrowid
    finally:
        conn.close()


# ---- Constrained query service (Phase 3) -----------------------------------
# The analytical read path: a validated plan executes on a structurally
# read-only connection as SQL assembled only from whitelisted identifiers
# (the registry / the live schema — never plan strings) + bound ? params.

def _read_only_connect(db_path):
    """Open the store structurally read-only: the file itself refuses a
    write, so the analytical path cannot write (spec section 9)."""
    uri = pathlib.Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _plan_from(plan):
    """dict | JSON str -> dict. Bad JSON or a non-object is refused."""
    if isinstance(plan, (bytes, bytearray)):
        plan = plan.decode("utf-8")
    if isinstance(plan, str):
        try:
            plan = json.loads(plan)
        except ValueError as e:
            raise ValueError("bad plan JSON: %s" % (e,))
    if not isinstance(plan, dict):
        raise ValueError("bad plan: want a JSON object")
    return plan


def _columns_of(conn, entity):
    """The live-schema columns of a whitelisted entity (the double gate's
    schema half — P2). entity comes from QUERY_ENTITIES, so it is safe
    to interpolate."""
    rows = conn.execute("PRAGMA table_info(%s)" % (entity,)).fetchall()
    return [r[1] for r in rows]


def _gate_entity(conn, entity):
    if entity not in QUERY_ENTITIES:
        raise ValueError(
            "unknown entity %r (want one of: %s)"
            % (entity, ", ".join(QUERY_ENTITIES)))
    if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (entity,)).fetchone() is None:
        raise ValueError("unknown entity %r (not in this db)" % (entity,))
    return entity


def _gate_filters(conn, entity, filters):
    """Gate a filter list against the entity's live columns (P2)."""
    if filters is None:
        return
    if not isinstance(filters, list):
        raise ValueError("bad filters: want a list")
    cols = _columns_of(conn, entity)
    for i, f in enumerate(filters):
        if not isinstance(f, dict):
            raise ValueError("bad filter %d: want an object" % (i,))
        field = f.get("field")
        op = f.get("op")
        if field not in cols:
            raise ValueError("unknown field %r on %s" % (field, entity))
        if op not in FILTER_OPS:
            raise ValueError(
                "bad filter op %r (want one of: %s)"
                % (op, ", ".join(FILTER_OPS)))
        if op in ("IS NULL", "IS NOT NULL"):
            if f.get("value") is not None:
                raise ValueError("filter op %r takes no value" % (op,))
        else:
            if f.get("value") is None:
                raise ValueError("filter op %r requires a value" % (op,))
            if op == "IN" and not (isinstance(f["value"], list)
                                   and f["value"]):
                raise ValueError("filter op IN requires a non-empty list")


def _gate_order_by(conn, entity, order_by):
    if order_by is None:
        return
    if not isinstance(order_by, dict):
        raise ValueError("bad order_by: want an object")
    cols = _columns_of(conn, entity)
    if order_by.get("field") not in cols:
        raise ValueError(
            "unknown order_by field %r on %s" % (order_by.get("field"),
                                                 entity))
    if order_by.get("direction") not in ("asc", "desc"):
        raise ValueError("bad order_by direction %r"
                         % (order_by.get("direction"),))


def _gate_limit(limit):
    """A limit is a positive int <= MAX_LIMIT; None takes the default."""
    if limit is None:
        return DEFAULT_LIMIT
    if not isinstance(limit, int) or isinstance(limit, bool) \
            or limit < 1 or limit > MAX_LIMIT:
        raise ValueError("bad limit %r (max %d)" % (limit, MAX_LIMIT))
    return limit


def _junction_direction(via, current):
    """(target entity, target join column, stage join column) for
    following `via` from `current` — both directions (P7). Refuses a
    junction that does not touch the current entity, naming the
    endpoints."""
    spec = JUNCTIONS[via]
    if current == spec["from"][0]:
        return spec["to"][0], spec["to"][1], spec["from"][1]
    if current == spec["to"][0]:
        return spec["from"][0], spec["from"][1], spec["to"][1]
    raise ValueError(
        "junction %s does not touch %s (endpoints: %s, %s)"
        % (via, current, spec["from"][0], spec["to"][0]))


def _path_end_entity(entity, traverse):
    """The entity at the end of the traversal path (walks the junction
    endpoints; a disconnected step is refused here, at validation)."""
    current = entity
    for step in traverse:
        current, _tcol, _jcol = _junction_direction(step["via"], current)
    return current


def _validate_plan(plan, conn):
    """Full validation against the registry + the live schema (P2, P4,
    P9, P10) — runs before any SQL. Refusals name the bad token.
    Returns the normalized plan (limit / mode filled in)."""
    if ("entity" in plan) == ("search" in plan):
        raise ValueError("exactly one of 'entity' / 'search' is required")
    plan = dict(plan)
    if "search" in plan:
        if not isinstance(plan["search"], str) or not plan["search"]:
            raise ValueError("bad search: want a non-empty string")
        entities = plan.get("entities")
        if entities is not None:
            if not isinstance(entities, list) or not entities:
                raise ValueError(
                    "bad search entities %r (want a non-empty list drawn "
                    "from: %s)"
                    % (entities, ", ".join(sorted(SEARCHED_COLUMNS))))
            bad = [e for e in entities if e not in SEARCHED_COLUMNS]
            if bad:
                raise ValueError(
                    "bad search entities %r (want them drawn from: %s)"
                    % (bad, ", ".join(sorted(SEARCHED_COLUMNS))))
        plan["limit"] = _gate_limit(plan.get("limit"))
        return plan
    entity = _gate_entity(conn, plan["entity"])
    plan.setdefault("mode", "rows")
    if plan["mode"] not in ("rows", "count", "group"):
        raise ValueError("bad mode %r (want one of: rows, count, group)"
                         % (plan["mode"],))
    plan["limit"] = _gate_limit(plan.get("limit"))
    _gate_filters(conn, entity, plan.get("filters"))
    _gate_order_by(conn, entity, plan.get("order_by"))
    traverse = plan.get("traverse")
    if traverse is not None:
        if not isinstance(traverse, list) or not traverse:
            raise ValueError("bad traverse: want a non-empty list of steps")
        if len(traverse) > MAX_TRAVERSAL_STEPS:
            raise ValueError("too many traversal steps (max %d)"
                             % (MAX_TRAVERSAL_STEPS,))
        for i, step in enumerate(traverse):
            if not isinstance(step, dict):
                raise ValueError("bad traversal step %d: want an object"
                                 % (i,))
            if step.get("via") not in JUNCTIONS:
                raise ValueError(
                    "unknown junction %r (want one of: %s)"
                    % (step.get("via"), ", ".join(JUNCTIONS)))
            step_limit = step.get("limit")
            if step_limit is not None:
                step["limit"] = _gate_limit(step_limit)
            _gate_filters(conn, _path_end_entity(entity, traverse[:i + 1]),
                          step.get("filters"))
            _gate_order_by(conn, _path_end_entity(entity, traverse[:i + 1]),
                           step.get("order_by"))
    if plan["mode"] == "group":
        gb = plan.get("group_by")
        if not isinstance(gb, dict) or gb.get("field") is None:
            raise ValueError("group_by is required for group mode")
        final = _path_end_entity(entity, traverse or [])
        if gb["field"] not in _columns_of(conn, final):
            raise ValueError("unknown group_by field %r on %s"
                             % (gb["field"], final))
    elif "group_by" in plan:
        raise ValueError("group_by is only for group mode")
    return plan


def _where_sql(filters, prefix=""):
    """(AND-joined clause or '', params) for a gated filter list. Field
    identifiers were validated against the live schema; every value is
    bound. prefix qualifies the identifiers (a traversal step's filters
    run on a joined table — bare names would be ambiguous there)."""
    if not filters:
        return "", []
    conds = []
    params = []
    for f in filters:
        field, op = f["field"], f["op"]
        col = prefix + field
        if op == "IN":
            conds.append(
                "%s IN (%s)" % (col, ",".join("?" * len(f["value"]))))
            params.extend(f["value"])
        elif op == "IS NULL":
            conds.append("%s IS NULL" % (col,))
        elif op == "IS NOT NULL":
            conds.append("%s IS NOT NULL" % (col,))
        else:
            sym = {"=": "=", "!=": "<>", ">": ">", "<": "<",
                   ">=": ">=", "<=": "<=", "LIKE": "LIKE"}[op]
            conds.append("%s %s ?" % (col, sym))
            params.append(f["value"])
    return " AND ".join(conds), params


def _stage_sql(entity, filters, order_by, limit):
    """SELECT * FROM <entity> [WHERE …] [ORDER BY …] [LIMIT ?] —
    identifiers from the validated set, values bound. A stage without
    order_by orders by id, so caps are deterministic (P9)."""
    where, params = _where_sql(filters)
    sql = "SELECT * FROM %s" % (entity,)
    if where:
        sql += " WHERE " + where
    if order_by:
        sql += " ORDER BY %s %s" % (order_by["field"],
                                    order_by["direction"].upper())
    else:
        sql += " ORDER BY id"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return sql, params


def _rows_for(entity, rows):
    """P6 row dicts: entity + id first, then the table's columns in
    live-schema order."""
    out = []
    for r in rows:
        d = dict(r)
        row = {"entity": entity, "id": d.pop("id")}
        row.update(d)
        out.append(row)
    return out


def _traverse_step(conn, stage_entity, stage_rows, step, cap):
    """One hop along a typed junction (P7): the stage's ids join the
    junction to the other endpoint. One SQL; the stage's step filters
    and order_by were validated against the target entity; the cap is
    None only in aggregate modes without an explicit step limit.
    Returns (target entity, rows) — deduped by id, first-seen order
    (a many-to-many fan-out revisiting a target keeps one row)."""
    via = step["via"]
    target, tcol, jcol = _junction_direction(via, stage_entity)
    ids = [r["id"] for r in stage_rows]
    where, wparams = _where_sql(step.get("filters"), prefix="T.")
    sql = ("SELECT T.* FROM %s AS J JOIN %s AS T ON T.id = J.%s "
           "WHERE J.%s IN (%s)"
           % (JUNCTIONS[via]["table"], target, tcol, jcol,
              ",".join("?" * len(ids))))
    params = list(ids)
    if where:
        sql += " AND " + where
        params.extend(wparams)
    if step.get("order_by"):
        sql += " ORDER BY T.%s %s" % (step["order_by"]["field"],
                                      step["order_by"]["direction"].upper())
    else:
        sql += " ORDER BY T.id"
    if cap is not None:
        sql += " LIMIT ?"
        params.append(cap)
    rows = conn.execute(sql, params).fetchall()
    seen = set()
    out = []
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        out.append(r)
    return target, out


def _search_execute(conn, vplan):
    """The FTS5 search plan (P10): the query string is bound into MATCH
    (never interpolated); a malformed FTS5 query is refused naming the
    string. Matches resolve to real entity rows (citation-ready); order
    is rank (bm25 — lower is better) then entity, id; capped at the
    plan limit. The funnel is the per-entity pre-cap counts."""
    search = vplan["search"]
    entities = vplan.get("entities")
    limit = vplan["limit"]
    base = ("SELECT entity, id, rank FROM search_index "
            "WHERE search_index MATCH ?")
    params = [search]
    if entities:
        base += " AND entity IN (%s)" % (",".join("?" * len(entities)),)
        params.extend(entities)
    try:
        total = conn.execute(
            base.replace("SELECT entity, id, rank",
                         "SELECT COUNT(*)"), params).fetchone()[0]
        matched = conn.execute(
            base + " ORDER BY rank, entity, id", params).fetchall()
    except sqlite3.OperationalError as e:
        raise ValueError("bad search query %r: %s" % (search, e))
    returned = matched[:limit]
    per_entity = {}
    for m in returned:
        per_entity.setdefault(m["entity"], []).append(m["id"])
    cache = {
        e: {r["id"]: r for r in conn.execute(
            "SELECT * FROM %s WHERE id IN (%s)"
            % (e, ",".join("?" * len(ids))), list(ids)).fetchall()}
        for e, ids in per_entity.items()
    }
    results = []
    for m in returned:
        d = dict(cache[m["entity"]][m["id"]])
        row = {"entity": m["entity"], "id": d.pop("id")}
        row.update(d)
        results.append(row)
    funnel_counts = {}
    order = []
    for m in matched:
        e = m["entity"]
        if e not in funnel_counts:
            order.append(e)
        funnel_counts[e] = funnel_counts.get(e, 0) + 1
    meta = {
        "mode": "search",
        "rows_returned": len(results),
        "rows_total": total,
        "truncated": total > len(results),
        "stages": [{"entity": e, "rows": funnel_counts[e]} for e in order],
    }
    return {"results": results, "meta": meta}


EXAMPLE_PLAN = ('{"entity": "event", "filters": '
                '[{"field": "company_key", "op": "=", "value": "Acme"}], '
                '"order_by": {"field": "date_iso", "direction": "desc"}, '
                '"limit": 5}')


def query(db_path, plan):
    """The constrained query service (spec section 9). The plan is
    validated fully, then executed on a structurally read-only
    connection (P3). Returns the envelope {"results": [...], "meta":
    {...}} — every result row carries entity + id (citation-ready), and
    the meta reports rows_returned / rows_total / truncated + the
    per-stage funnel (P1, P4, P6)."""
    plan = _plan_from(plan)
    conn = db_connect(db_path)  # the derived-state rebuild pass
    conn.close()
    ro = _read_only_connect(db_path)
    try:
        vplan = _validate_plan(plan, ro)
        if "search" in vplan:
            return _search_execute(ro, vplan)
        entity = vplan["entity"]
        mode = vplan["mode"]
        traverse = vplan.get("traverse") or []
        # rows mode caps every stage (P4); count / group are uncapped
        # row-wise (they return an aggregate) — an explicit step limit
        # still applies in every mode.
        root_limit = vplan["limit"] if mode == "rows" else None

        def execute_path(uncap_final=False):
            rsql, rparams = _stage_sql(entity, vplan.get("filters"),
                                       vplan.get("order_by"), root_limit)
            stage = ro.execute(rsql, rparams).fetchall()
            funnel = [{"entity": entity, "rows": len(stage)}]
            cur = entity
            n = len(traverse)
            for i, step in enumerate(traverse):
                cap = step.get("limit")
                if mode == "rows" and cap is None \
                        and not (uncap_final and i == n - 1):
                    cap = vplan["limit"]
                cur, stage = _traverse_step(ro, cur, stage, step, cap)
                funnel.append({"entity": cur, "rows": len(stage)})
            return cur, stage, funnel

        current, stage, funnel = execute_path()
        if mode == "count":
            n = len(stage)
            meta = {
                "entity": current,
                "mode": "count",
                "rows_returned": 1,
                "rows_total": n,
                "truncated": False,
                "stages": funnel,
            }
            return {"results": [{"count": n}], "meta": meta}
        if mode == "group":
            gb = vplan["group_by"]["field"]
            counts = {}
            for r in stage:
                counts[r[gb]] = counts.get(r[gb], 0) + 1
            groups = [{gb: k, "count": v} for k, v in counts.items()]
            none_groups = [g for g in groups if g[gb] is None]
            valued = sorted((g for g in groups if g[gb] is not None),
                            key=lambda g: g[gb])
            valued.sort(key=lambda g: -g["count"])  # stable: key order kept
            all_groups = none_groups + valued
            total = len(all_groups)
            groups = all_groups[:vplan["limit"]]
            meta = {
                "entity": current,
                "mode": "group",
                "rows_returned": len(groups),
                "rows_total": total,
                "truncated": total > len(groups),
                "stages": funnel,
            }
            return {"results": groups, "meta": meta}
        rows = _rows_for(current, stage)
        if traverse:
            _cur, total_stage, _f = execute_path(uncap_final=True)
            rows_total = len(total_stage)
        else:
            csql, cparams = _stage_sql(entity, vplan.get("filters"),
                                       vplan.get("order_by"), None)
            csql = csql.replace("SELECT * FROM", "SELECT COUNT(*) FROM", 1)
            rows_total = ro.execute(csql, cparams).fetchone()[0]
        meta = {
            "entity": current,
            "mode": "rows",
            "rows_returned": len(rows),
            "rows_total": rows_total,
            "truncated": rows_total > len(rows),
            "stages": funnel,
        }
        return {"results": rows, "meta": meta}
    finally:
        ro.close()


# ---- Phase-1 knowledge layer ops -------------------------------------------

# entity type -> table + the label column (shown as the entity's name).
ENTITIES = {
    "person":      {"table": "person",      "label": "full_name"},
    "company":     {"table": "company",     "label": "name"},
    "role":        {"table": "role",        "label": "title"},
    "project":     {"table": "project",     "label": "name"},
    "skill":       {"table": "skill",       "label": "name"},
    "achievement": {"table": "achievement", "label": "title"},
    "evidence":    {"table": "evidence",    "label": "evid_id"},
    "document":    {"table": "document",    "label": "title"},
    "contact":     {"table": "contact",     "label": "name"},
    "job_opening": {"table": "job_opening", "label": "title"},
    "application": {"table": "application", "label": "role"},
    "interview":   {"table": "interview",   "label": "round"},
}

# junction type -> table, (type, column) endpoints, and typed attrs. An attr
# value of kind "evidence" is an FK into evidence(id); "date" is M/D/YYYY as
# recorded (stored ISO); "int" is 0/1; "text" is free text. The attr name is
# the user-facing --attr key; the second element is the table column.
JUNCTIONS = {
    "achievement_skill":    {"table": "achievement_skill",
                             "from": ("achievement", "achievement_id"),
                             "to": ("skill", "skill_id"),
                             "attrs": {"level": ("text", "level"),
                                       "evidence": ("evidence", "evidence_id")}},
    "achievement_evidence": {"table": "achievement_evidence",
                             "from": ("achievement", "achievement_id"),
                             "to": ("evidence", "evidence_id"),
                             "attrs": {}},
    "resume_achievement":   {"table": "resume_achievement",
                             "from": ("document", "document_id"),
                             "to": ("achievement", "achievement_id"),
                             "attrs": {"placement": ("text", "placement")}},
    "document_achievement": {"table": "document_achievement",
                             "from": ("document", "document_id"),
                             "to": ("achievement", "achievement_id"),
                             "attrs": {}},
    "project_skill":        {"table": "project_skill",
                             "from": ("project", "project_id"),
                             "to": ("skill", "skill_id"),
                             "attrs": {"level": ("text", "level")}},
    "job_skill":            {"table": "job_skill",
                             "from": ("job_opening", "job_opening_id"),
                             "to": ("skill", "skill_id"),
                             "attrs": {"required_level": ("text", "required_level")}},
    "application_document": {"table": "application_document",
                             "from": ("application", "application_id"),
                             "to": ("document", "document_id"),
                             "attrs": {"purpose": ("text", "purpose")}},
    "application_contact":  {"table": "application_contact",
                             "from": ("application", "application_id"),
                             "to": ("contact", "contact_id"),
                             "attrs": {"relationship": ("text", "relationship")}},
    "contact_company":      {"table": "contact_company",
                             "from": ("contact", "contact_id"),
                             "to": ("company", "company_id"),
                             "attrs": {"role": ("text", "role"),
                                       "start": ("date", "start_date"),
                                       "end": ("date", "end_date"),
                                       "current": ("int", "is_current")}},
}

# Direct FK edges for the walker: (entity_type, own_column, other_type,
# rel_name, direction). "out" = the entity's column points at the other;
# "in" = rows of the other type carry the entity's id in their column
# (reverse walk). Every entry's column sits on the entity_type side, so
# every entry is "out"; a walker reaching an edge from the other side
# derives "in" from which side it sits on. rel names: the named relationship types.
FKS = [
    ("role",          "person_id",       "person",      "held",               "out"),
    ("role",          "company_id",      "company",     "employs",            "out"),
    ("job_opening",   "company_id",      "company",     "posts",              "out"),
    ("application",   "company_id",      "company",     "receives",           "out"),
    ("application",   "job_opening_id",  "job_opening", "targeted_by",        "out"),
    ("application",   "contact_id",      "contact",     "primary contact",    "out"),
    ("achievement",   "role_id",         "role",        "context_for",        "out"),
    ("achievement",   "project_id",      "project",     "produces",           "out"),
    ("document",      "supersedes_id",   "document",    "supersedes",         "out"),
    ("contact",       "company_id",      "company",     "affiliated (current)", "out"),
    ("interview",     "application_id",  "application", "has_rounds",         "out"),
    ("event",         "application_id",  "application", "logged_on",          "out"),
]

# Tables carrying provenance + governance_state (the governance op's query
# set): the five governed entity tables + all nine junction tables. Fixed
# order (deterministic output); a set literal would iterate non-deterministically.
GOVERNED = ["role", "project", "skill", "achievement", "document"] + [
    "achievement_skill", "achievement_evidence", "resume_achievement",
    "document_achievement", "project_skill", "job_skill",
    "application_document", "application_contact", "contact_company",
]

GOV_STATES = ("user_fact", "imported", "ai_suggested",
              "user_verified", "rejected_outdated")

# ---- Constrained query service (Phase 3) -----------------------------------
# The analytical read path (spec section 9): a validated plan over a
# whitelist of entities / fields / junctions, parameterized only, bounded,
# executed on a structurally read-only connection. There is no free-form
# SQL anywhere in this path.

# The queryable entity roots. Excluded: meta / run_logs (mechanism tables),
# search_index (the index itself), instruction (the working-set op is its
# reader), note / note_reference (no write op — out of v1 scope),
# v_application_status (view — the status op is its reader), and the nine
# junction tables as roots (a traversal is the only path through a junction).
QUERY_ENTITIES = [
    "person", "company", "role", "project", "skill", "achievement",
    "evidence", "document", "contact", "job_opening", "application",
    "interview", "interaction", "event",
]

# The full-text index surface: entity -> the pinned text columns (the FTS
# index is derived state, rebuilt at every open). Excluded: person (the
# single PII-dense identity row), contact.email / contact.linkedin_ref
# (PII), every *_ref / path pointer column (pointers are citations, not
# searchable text), event.raw_row, and all id / date / stamp / governance
# columns.
SEARCHED_COLUMNS = {
    "company": ("name", "industry"),
    "role": ("title",),
    "project": ("name",),
    "skill": ("name",),
    "achievement": ("title",),
    "evidence": ("evid_id", "claim", "value"),
    "document": ("title",),
    "contact": ("name", "title"),
    "job_opening": ("title",),
    "application": ("role",),
    "interview": ("round",),
    "interaction": ("summary",),
    "event": ("note", "type", "outcome"),
}

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000
MAX_TRAVERSAL_STEPS = 3

FILTER_OPS = ("=", "!=", ">", "<", ">=", "<=", "IN", "LIKE",
              "IS NULL", "IS NOT NULL")


def _search_index_ddl():
    return ("CREATE VIRTUAL TABLE search_index "
            "USING fts5(text, entity UNINDEXED, id UNINDEXED)")


def _search_index_fill():
    """The one-shot fill: one row per indexed (entity, id) — the pinned
    text columns (SEARCHED_COLUMNS) space-joined, NULLs as empty."""
    parts = []
    for entity, cols in SEARCHED_COLUMNS.items():
        text = " || ' ' || ".join("IFNULL(%s, '')" % (c,) for c in cols)
        parts.append("SELECT '%s', id, %s FROM %s"
                     % (entity, text, entity))
    return ("INSERT INTO search_index (entity, id, text) "
            + " UNION ALL ".join(parts))


def _today_iso():
    return datetime.date.today().isoformat()


def _upsert(conn, table, key_where, provided, defaults,
            stamps=("created_at", "updated_at")):
    """Create-or-verify a knowledge row against its natural key.

    key_where: the natural key as {column: value} ({} for the single-row
    table, person). provided: the non-None fields the caller passed (key
    columns included, so the create insert is complete). defaults:
    create-only values for columns not in provided (governance defaults,
    enum defaults). stamps: the timestamp columns the table carries
    (application has created_at only). Returns the row id.

    The conflict rule (duplicate + conflict handling): a provided
    value that differs from a stored non-NULL value is refused — a
    ValueError naming the table, key, field, stored and given values — and
    nothing is written. Stored NULLs may be filled by a re-run (those
    columns + updated_at when the table has one). An all-matching re-run
    is an idempotent no-op. Key comparisons are NULL-safe (IS ?).
    """
    if key_where:
        where_sql = " AND ".join("%s IS ?" % k for k in key_where)
        cur = conn.execute(
            "SELECT * FROM %s WHERE %s" % (table, where_sql),
            list(key_where.values()))
        row = cur.fetchone()
    else:
        cur = conn.execute("SELECT * FROM %s ORDER BY id" % table)
        rows = cur.fetchall()
        if len(rows) > 1:
            raise ValueError(
                "%s: expected a single row, found %d" % (table, len(rows)))
        row = rows[0] if rows else None

    if row is None:
        cols = list(dict.fromkeys(
            list(provided) + list(key_where)
            + [c for c in defaults if c not in provided]))
        values = [provided[c] if c in provided
                  else key_where[c] if c in key_where else defaults[c]
                  for c in cols]
        stamp_cols = [c for c in stamps if c not in cols]
        cols += stamp_cols
        values += [_today_iso() for _ in stamp_cols]
        cur = conn.execute(
            "INSERT INTO %s (%s) VALUES (%s)"
            % (table, ",".join(cols), ",".join("?" * len(cols))),
            values)
        return cur.lastrowid

    stored = dict(zip([c[0] for c in cur.description], row))
    fills = {}
    for col, val in provided.items():
        cur_val = stored.get(col)
        if cur_val is not None and cur_val != val:
            raise ValueError(
                "conflict: %s key %s field %s: stored %r, given %r"
                % (table, key_where, col, cur_val, val))
        if cur_val is None and val is not None:
            fills[col] = val
    if fills:
        set_sql = ", ".join("%s = ?" % c for c in fills)
        vals = list(fills.values())
        if "updated_at" in stamps:
            set_sql += ", updated_at = ?"
            vals.append(_today_iso())
        conn.execute(
            "UPDATE %s SET %s WHERE id = ?" % (table, set_sql),
            vals + [stored["id"]])
    return stored["id"]


def _non_null(mapping):
    return {k: v for k, v in mapping.items() if v is not None}


def _provenance(as_user):
    return ("user", "user_fact") if as_user else ("ai", "ai_suggested")


def upsert_person(db_path, full_name, objective=None, location=None,
                  as_user=True):
    """Create-or-verify the single person row. as_user is accepted and
    ignored (person carries no governance columns). Returns the row id."""
    conn = db_connect(db_path)
    try:
        with conn:
            return _upsert(
                conn, "person", {},
                _non_null({"full_name": full_name, "objective": objective,
                           "location": location}), {})
    finally:
        conn.close()


def upsert_company(db_path, name, industry=None, notes_ref=None,
                   as_user=True):
    """Create-or-verify a company row (key: name). Returns the row id."""
    conn = db_connect(db_path)
    try:
        with conn:
            return _upsert(
                conn, "company", {"name": name},
                _non_null({"name": name, "industry": industry,
                           "notes_ref": notes_ref}), {})
    finally:
        conn.close()


def upsert_role(db_path, company, title, start_date=None, end_date=None,
                is_current=0, summary_ref=None, as_user=True):
    """Create-or-verify a role row (key: company + title + start_date).
    The company is given by name and resolved to its row (refused when the
    company row is missing). Returns the row id."""
    if is_current not in (0, 1):
        raise ValueError("is_current must be 0 or 1")
    conn = db_connect(db_path)
    try:
        with conn:
            c = conn.execute(
                "SELECT id FROM company WHERE name = ?", (company,)
            ).fetchone()
            if c is None:
                raise ValueError("no company %r (upsert-company first)"
                                 % (company,))
            p = conn.execute("SELECT id FROM person ORDER BY id").fetchone()
            if p is None:
                raise ValueError("no person row (upsert-person first)")
            prov = _provenance(as_user)
            return _upsert(
                conn, "role",
                {"company_id": c[0], "title": title,
                 "start_date": to_iso(start_date) if start_date else None},
                _non_null({"person_id": p[0],
                           "end_date": to_iso(end_date) if end_date else None,
                           "is_current": is_current,
                           "summary_ref": summary_ref}),
                {"provenance": prov[0], "governance_state": prov[1]})
    finally:
        conn.close()


def upsert_project(db_path, name, repo_ref=None, summary_ref=None,
                   start_date=None, end_date=None, as_user=True):
    """Create-or-verify a project row (key: name). Returns the row id."""
    conn = db_connect(db_path)
    try:
        with conn:
            prov = _provenance(as_user)
            return _upsert(
                conn, "project", {"name": name},
                _non_null({"name": name, "repo_ref": repo_ref,
                           "summary_ref": summary_ref,
                           "start_date": to_iso(start_date) if start_date else None,
                           "end_date": to_iso(end_date) if end_date else None}),
                {"provenance": prov[0], "governance_state": prov[1]})
    finally:
        conn.close()


def upsert_skill(db_path, name, category=None, notes_ref=None,
                 as_user=True):
    """Create-or-verify a skill row (key: name). Returns the row id."""
    conn = db_connect(db_path)
    try:
        with conn:
            prov = _provenance(as_user)
            return _upsert(
                conn, "skill", {"name": name},
                _non_null({"name": name, "category": category,
                           "notes_ref": notes_ref}),
                {"provenance": prov[0], "governance_state": prov[1]})
    finally:
        conn.close()


def upsert_achievement(db_path, title, summary_ref=None, role_id=None,
                       project_id=None, occurred_date=None, as_user=True):
    """Create-or-verify an achievement row (key: title). Returns the row id."""
    conn = db_connect(db_path)
    try:
        with conn:
            prov = _provenance(as_user)
            return _upsert(
                conn, "achievement", {"title": title},
                _non_null({"title": title, "summary_ref": summary_ref,
                           "role_id": role_id, "project_id": project_id,
                           "occurred_date": to_iso(occurred_date) if occurred_date else None}),
                {"provenance": prov[0], "governance_state": prov[1]})
    finally:
        conn.close()


def upsert_evidence(db_path, evid_id, claim, value=None, source_kind=None,
                    source_ref=None, as_of_date=None, status=None):
    """Create-or-verify an evidence row (key: evid_id). source_kind defaults
    to 'user_stated', status to 'current'. Returns the row id."""
    source_kind = source_kind or "user_stated"
    if source_kind not in ("code", "user_stated"):
        raise ValueError("bad source_kind %r" % (source_kind,))
    status = status or "current"
    if status not in ("current", "struck"):
        raise ValueError("bad evidence status %r" % (status,))
    conn = db_connect(db_path)
    try:
        with conn:
            return _upsert(
                conn, "evidence", {"evid_id": evid_id},
                _non_null({"evid_id": evid_id, "claim": claim, "value": value,
                           "source_ref": source_ref,
                           "as_of_date": to_iso(as_of_date) if as_of_date else None}),
                {"source_kind": source_kind, "status": status})
    finally:
        conn.close()


def upsert_document(db_path, doc_type, title, path, version=1,
                    supersedes_id=None, is_third_party_safe=0):
    """Create-or-verify a document row (key: doc_type + path + version).
    Returns the row id."""
    if is_third_party_safe not in (0, 1):
        raise ValueError("is_third_party_safe must be 0 or 1")
    conn = db_connect(db_path)
    try:
        with conn:
            prov = _provenance(True)
            return _upsert(
                conn, "document",
                {"doc_type": doc_type, "path": path, "version": version},
                _non_null({"doc_type": doc_type, "title": title, "path": path,
                           "version": version,
                           "supersedes_id": supersedes_id,
                           "is_third_party_safe": is_third_party_safe}),
                {"provenance": prov[0], "governance_state": prov[1]})
    finally:
        conn.close()


def _parse_ref(ref, expected_type, side):
    """Parse a 'type:id' ref. The type must be a known entity and must match
    the junction's expected endpoint; the id must be digits. Returns
    (type, int id)."""
    if ":" not in ref:
        raise ValueError("bad %s ref %r (want type:id)" % (side, ref))
    etype, _sep, eid = ref.partition(":")
    if etype not in ENTITIES:
        raise ValueError("unknown entity type %r in the %s ref" % (etype, side))
    if etype != expected_type:
        raise ValueError(
            "%s ref type %r does not match the junction endpoint %r"
            % (side, etype, expected_type))
    if not eid.isdigit():
        raise ValueError("bad id in the %s ref %r (want a digit id)" % (side, ref))
    return etype, int(eid)


def link(db_path, junction, from_ref, to_ref, attrs=None, as_user=True):
    """Create a typed junction row. Refuses an unknown junction, a bad or
    mismatched ref, a missing entity row, an invalid attr (name, kind, or a
    missing evidence id), and a duplicate (from, to) row — nothing is written
    on refusal. --as user -> provenance 'user' / user_fact; --as ai ->
    'ai' / ai_suggested. Returns the new row id."""
    if junction not in JUNCTIONS:
        raise ValueError("unknown junction type %r" % (junction,))
    spec = JUNCTIONS[junction]
    ftype, fid = _parse_ref(from_ref, spec["from"][0], "from")
    ttype, tid = _parse_ref(to_ref, spec["to"][0], "to")
    attrs = attrs or {}
    for k in attrs:
        if k not in spec["attrs"]:
            raise ValueError(
                "bad attr %r for junction %r (valid: %s)"
                % (k, junction, ", ".join(spec["attrs"]) or "none"))
    conn = db_connect(db_path)
    try:
        with conn:
            for etype, eid in ((ftype, fid), (ttype, tid)):
                if conn.execute(
                        "SELECT id FROM %s WHERE id = ?"
                        % (ENTITIES[etype]["table"],), (eid,)).fetchone() is None:
                    raise ValueError("no %s with id %d" % (etype, eid))
            dup = conn.execute(
                "SELECT id FROM %s WHERE %s = ? AND %s = ?"
                % (spec["table"], spec["from"][1], spec["to"][1]),
                (fid, tid)).fetchone()
            if dup is not None:
                raise ValueError(
                    "duplicate %s link: existing row id %d" % (junction, dup[0]))
            values = {}
            for k, (kind, _col) in spec["attrs"].items():
                v = attrs.get(k)
                if v is None:
                    values[k] = None
                elif kind == "evidence":
                    if not str(v).isdigit():
                        raise ValueError("attr %s must be an evidence id" % (k,))
                    v = int(v)
                    if conn.execute("SELECT id FROM evidence WHERE id = ?",
                                    (v,)).fetchone() is None:
                        raise ValueError("no evidence with id %d" % (v,))
                    values[k] = v
                elif kind == "date":
                    values[k] = to_iso(v)
                elif kind == "int":
                    if isinstance(v, str):
                        if v not in ("0", "1"):
                            raise ValueError("attr %s must be 0 or 1" % (k,))
                        v = int(v)
                    elif v not in (0, 1):
                        raise ValueError("attr %s must be 0 or 1" % (k,))
                    values[k] = v
                else:
                    values[k] = v
            prov = _provenance(as_user)
            cols = [spec["from"][1], spec["to"][1]]
            vals = [fid, tid]
            cols += [spec["attrs"][k][1] for k in spec["attrs"]]
            vals += [values[k] for k in spec["attrs"]]
            cols += ["created_at", "provenance", "governance_state"]
            vals += [_today_iso(), prov[0], prov[1]]
            try:
                cur = conn.execute(
                    "INSERT INTO %s (%s) VALUES (%s)"
                    % (spec["table"], ",".join(cols),
                       ",".join("?" * len(cols))), vals)
            except sqlite3.IntegrityError as e:
                raise ValueError("link %s: %s" % (junction, e))
            return cur.lastrowid
    finally:
        conn.close()


def verify(db_path, junction, row_id):
    """The only path from ai_suggested to user_verified. Refuses a missing
    row and any row that is not provenance 'ai' at 'ai_suggested'."""
    if junction not in JUNCTIONS:
        raise ValueError("unknown junction type %r" % (junction,))
    table = JUNCTIONS[junction]["table"]
    conn = db_connect(db_path)
    try:
        with conn:
            row = conn.execute(
                "SELECT id, provenance, governance_state FROM %s WHERE id = ?"
                % (table,), (row_id,)).fetchone()
            if row is None:
                raise ValueError("no %s row with id %d" % (junction, row_id))
            prov, state = row[1], row[2]
            if prov != "ai" or state != "ai_suggested":
                raise ValueError(
                    "refusing to verify: %s row %d is %s/%s (only an ai row "
                    "at ai_suggested may be verified)"
                    % (junction, row_id, prov, state))
            conn.execute(
                "UPDATE %s SET governance_state = 'user_verified' WHERE id = ?"
                % (table,), (row_id,))
    finally:
        conn.close()


def _mark_rejected(db_path, junction, row_id, op_name):
    """Mark a junction row rejected_outdated (reject / unlink are the same
    transition: marked, never deleted). Refuses a missing row and a row
    already marked."""
    if junction not in JUNCTIONS:
        raise ValueError("unknown junction type %r" % (junction,))
    table = JUNCTIONS[junction]["table"]
    conn = db_connect(db_path)
    try:
        with conn:
            row = conn.execute(
                "SELECT governance_state FROM %s WHERE id = ?"
                % (table,), (row_id,)).fetchone()
            if row is None:
                raise ValueError("no %s row with id %d" % (junction, row_id))
            if row[0] == "rejected_outdated":
                raise ValueError(
                    "%s: %s row %d is already rejected_outdated"
                    % (op_name, junction, row_id))
            conn.execute(
                "UPDATE %s SET governance_state = 'rejected_outdated' "
                "WHERE id = ?" % (table,), (row_id,))
    finally:
        conn.close()


def reject(db_path, junction, row_id):
    """Mark a junction row rejected_outdated (kept, not deleted)."""
    _mark_rejected(db_path, junction, row_id, "reject")


def unlink(db_path, junction, row_id):
    """Mark a junction row rejected_outdated (kept, not deleted)."""
    _mark_rejected(db_path, junction, row_id, "unlink")


def governance(db_path, state):
    """List every GOVERNED row in the given state as
    (table, id, name, state, provenance, created_at). A junction row's name
    is 'from_name -> to_name'. state is validated against the five-value
    enum (the GOV_STATES constant). Deterministic order: GOVERNED table order,
    then row id."""
    if state not in GOV_STATES:
        raise ValueError("bad governance state %r (want one of: %s)"
                         % (state, ", ".join(GOV_STATES)))
    conn = db_connect(db_path)
    try:
        rows = []
        for table in GOVERNED:
            if table in JUNCTIONS:
                spec = JUNCTIONS[table]
                ft, fcol = spec["from"]
                tt, tcol = spec["to"]
                cur = conn.execute(
                    "SELECT j.id, e1.%s, e2.%s, j.governance_state, "
                    "j.provenance, j.created_at "
                    "FROM %s j "
                    "JOIN %s e1 ON e1.id = j.%s "
                    "JOIN %s e2 ON e2.id = j.%s "
                    "WHERE j.governance_state = ? ORDER BY j.id"
                    % (ENTITIES[ft]["label"], ENTITIES[tt]["label"], table,
                       ENTITIES[ft]["table"], fcol,
                       ENTITIES[tt]["table"], tcol),
                    (state,))
                for r in cur.fetchall():
                    rows.append((table, r[0], "%s -> %s" % (r[1], r[2]),
                                 r[3], r[4], r[5]))
            else:
                label = ENTITIES[table]["label"]
                cur = conn.execute(
                    "SELECT id, %s, governance_state, provenance, created_at "
                    "FROM %s WHERE governance_state = ? ORDER BY id"
                    % (label, table), (state,))
                for r in cur.fetchall():
                    rows.append((table, r[0], r[1], r[2], r[3], r[4]))
        return rows
    finally:
        conn.close()


def find_disconnected(db_path, entity_type=None):
    """Report entities with no junction row on either side, no non-NULL own
    FK (FKS), and no inbound FK reference (v1 scope: note_reference is out).
    Returns [(type, id, name)] in ENTITIES order, then row id.
    entity_type narrows to one type; an unknown type is a ValueError."""
    if entity_type is not None and entity_type not in ENTITIES:
        raise ValueError("unknown entity type %r" % (entity_type,))
    conn = db_connect(db_path)
    try:
        rows = []
        types = [entity_type] if entity_type else list(ENTITIES)
        for etype in types:
            table = ENTITIES[etype]["table"]
            label = ENTITIES[etype]["label"]
            for eid, name in conn.execute(
                    "SELECT id, %s FROM %s ORDER BY id" % (label, table)):
                connected = False
                for spec in JUNCTIONS.values():
                    for side in ("from", "to"):
                        if spec[side][0] == etype and conn.execute(
                                "SELECT 1 FROM %s WHERE %s = ? LIMIT 1"
                                % (spec["table"], spec[side][1]),
                                (eid,)).fetchone():
                            connected = True
                            break
                    if connected:
                        break
                if not connected:
                    for f_type, f_col, _other, _rel, _d in FKS:
                        if f_type == etype and conn.execute(
                                "SELECT 1 FROM %s WHERE id = ? AND %s IS NOT NULL"
                                % (table, f_col), (eid,)).fetchone():
                            connected = True
                            break
                if not connected:
                    for f_type, f_col, f_other, _rel, _d in FKS:
                        if f_other == etype and conn.execute(
                                "SELECT 1 FROM %s WHERE %s = ? LIMIT 1"
                                % (ENTITIES[f_type]["table"], f_col),
                                (eid,)).fetchone():
                            connected = True
                            break
                if not connected:
                    rows.append((etype, eid, name))
        return rows
    finally:
        conn.close()


def _walk_one(conn, etype, eid):
    """One level of the walk for a single entity: its junction edges (both
    sides, JUNCTIONS order, row id) then its FK edges (FKS order: out,
    then in). Each edge is (rel, direction, other_type, other_id, attrs,
    provenance, governance_state, created_at) — junction rows carry their
    governance fields; FK edges carry empty attrs and governance fields.
    direction: junction rows — which endpoint the neighbor sits on
    ('to' / 'from'); FK edges — 'out' / 'in' per the FKS semantics.
    A type outside ENTITIES (event — the target of the logged_on edge)
    is a walk leaf: no outgoing edges."""
    edges = []
    if etype not in ENTITIES:
        return edges
    table = ENTITIES[etype]["table"]
    for jname, spec in JUNCTIONS.items():
        if spec["from"][0] == etype:
            side, other = "from", spec["to"]
        elif spec["to"][0] == etype:
            side, other = "to", spec["from"]
        else:
            continue
        attr_cols = ", ".join(
            "j.%s" % spec["attrs"][k][1] for k in spec["attrs"])
        sel = ("SELECT j.%s, j.provenance, j.governance_state, j.created_at%s "
               "FROM %s j WHERE j.%s = ? ORDER BY j.id"
               % (other[1],
                  (", " + attr_cols) if attr_cols else "",
                  spec["table"], spec[side][1]))
        for r in conn.execute(sel, (eid,)):
            attr_vals = r[4:4 + len(spec["attrs"])]
            attrs = ",".join(
                "%s=%s" % (k, v)
                for k, v in zip(spec["attrs"], attr_vals)
                if v is not None)
            edges.append(
                (jname, "to" if side == "from" else "from",
                 other[0], r[0], attrs, r[1], r[2], r[3]))
    for f_type, f_col, f_other, rel, _d in FKS:
        if f_type == etype:
            r = conn.execute("SELECT %s FROM %s WHERE id = ?"
                             % (f_col, table), (eid,)).fetchone()
            if r[0] is not None:
                edges.append((rel, "out", f_other, r[0], "", "", "", ""))
    for f_type, f_col, f_other, rel, _d in FKS:
        if f_other == etype:
            otable = ENTITIES[f_type]["table"] \
                if f_type in ENTITIES else f_type
            for (oid,) in conn.execute(
                    "SELECT id FROM %s WHERE %s = ? ORDER BY id"
                    % (otable, f_col), (eid,)):
                edges.append((rel, "in", f_type, oid, "", "", "", ""))
    return edges


INSTR_KINDS = ("priority", "preference", "constraint", "prohibition")
INSTR_SCOPES = ("task", "application", "company", "interview_stage",
                "search_wide", "hat")
INSTR_SCOPE_REFS = ("application", "company", "interview", "hat")


def instruction(db_path, body, kind, scope_type, scope_ref_type=None,
                scope_ref=None, scope_ref_text=None, stated_date=None,
                valid_until=None, supersedes=None, as_user=True):
    """Create an instruction row (the pinned enums, validated before any
    write). as_user -> status 'active'; ai -> 'suggested' (not in force
    until verify-instruction). stated_date defaults to today; dates are
    M/D/YYYY as stated, stored ISO. supersedes N is atomic with the
    insert: N must exist with status 'active' or 'suggested'; N becomes
    'superseded' with superseded_by = the new row id (one transaction).
    Returns the new row id."""
    if kind not in INSTR_KINDS:
        raise ValueError("bad kind %r (want one of: %s)"
                         % (kind, ", ".join(INSTR_KINDS)))
    if scope_type not in INSTR_SCOPES:
        raise ValueError("bad scope_type %r (want one of: %s)"
                         % (scope_type, ", ".join(INSTR_SCOPES)))
    if scope_ref_type is not None and scope_ref_type not in INSTR_SCOPE_REFS:
        raise ValueError("bad scope_ref_type %r (want one of: %s)"
                         % (scope_ref_type, ", ".join(INSTR_SCOPE_REFS)))
    status = "active" if as_user else "suggested"
    conn = db_connect(db_path)
    try:
        with conn:
            if supersedes is not None:
                t = conn.execute(
                    "SELECT id, status FROM instruction WHERE id = ?",
                    (supersedes,)).fetchone()
                if t is None:
                    raise ValueError(
                        "no instruction with id %d to supersede"
                        % (supersedes,))
                if t[1] not in ("active", "suggested"):
                    raise ValueError(
                        "refusing to supersede instruction %d: status %r "
                        "(only an active or suggested row may be superseded)"
                        % (supersedes, t[1]))
            cur = conn.execute(
                "INSERT INTO instruction "
                "(body, kind, scope_type, scope_ref_type, scope_ref, "
                "scope_ref_text, stated_date, valid_until, superseded_by, "
                "status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (body, kind, scope_type, scope_ref_type, scope_ref,
                 scope_ref_text,
                 to_iso(stated_date) if stated_date else _today_iso(),
                 to_iso(valid_until) if valid_until else None,
                 None, status, _today_iso(), _today_iso()))
            new_id = cur.lastrowid
            if supersedes is not None:
                conn.execute(
                    "UPDATE instruction SET status = 'superseded', "
                    "superseded_by = ?, updated_at = ? WHERE id = ?",
                    (new_id, _today_iso(), supersedes))
            return new_id
    finally:
        conn.close()


def verify_instruction(db_path, row_id):
    """The only path from 'suggested' to 'active'. Refuses a missing row
    and any row that is not 'suggested'."""
    conn = db_connect(db_path)
    try:
        with conn:
            row = conn.execute(
                "SELECT status FROM instruction WHERE id = ?",
                (row_id,)).fetchone()
            if row is None:
                raise ValueError("no instruction with id %d" % (row_id,))
            if row[0] != "suggested":
                raise ValueError(
                    "refusing to verify instruction %d: status %r (only a "
                    "suggested row may be verified)" % (row_id, row[0]))
            conn.execute(
                "UPDATE instruction SET status = 'active', updated_at = ? "
                "WHERE id = ?", (_today_iso(), row_id))
    finally:
        conn.close()


def withdraw_instruction(db_path, row_id):
    """Mark an instruction 'withdrawn' (from any state; kept, never
    deleted). Refuses a missing row and an already-withdrawn row."""
    conn = db_connect(db_path)
    try:
        with conn:
            row = conn.execute(
                "SELECT status FROM instruction WHERE id = ?",
                (row_id,)).fetchone()
            if row is None:
                raise ValueError("no instruction with id %d" % (row_id,))
            if row[0] == "withdrawn":
                raise ValueError(
                    "instruction %d is already withdrawn" % (row_id,))
            conn.execute(
                "UPDATE instruction SET status = 'withdrawn', "
                "updated_at = ? WHERE id = ?", (_today_iso(), row_id))
    finally:
        conn.close()


def working_set(db_path, hat, application_id=None, today=None):
    """The derived working set (the working-set rule in standards): rows
    where status='active' AND
    unexpired (valid_until IS NULL OR valid_until >= today ISO — a window
    ending today is still in force; expiry is the drift check's flip, and
    application liveness is its finding, neither is a clause of this query)
    AND the scope matches: search_wide, hat rows whose scope_ref_text is
    the hat, application rows scoped to applications (all of them without
    an application_id, only the matching one with). Ordered by id.
    Returns [(id, kind, scope, body, valid_until)] with scope rendered
    search_wide / hat:<name> / application:<id>."""
    today = today or _today_iso()
    conn = db_connect(db_path)
    try:
        cur = conn.execute(
            "SELECT id, kind, "
            "CASE scope_type "
            "  WHEN 'search_wide' THEN 'search_wide' "
            "  WHEN 'hat' THEN 'hat:' || scope_ref_text "
            "  ELSE 'application:' || scope_ref END, "
            "body, valid_until "
            "FROM instruction "
            "WHERE status = 'active' "
            "  AND (valid_until IS NULL OR valid_until >= ?) "
            "  AND (scope_type = 'search_wide' "
            "       OR (scope_type = 'hat' AND scope_ref_text = ?) "
            "       OR (scope_type = 'application' "
            "           AND scope_ref_type = 'application' "
            "           AND (? IS NULL OR scope_ref = ?))) "
            "ORDER BY id",
            (today, hat, application_id, application_id))
        return cur.fetchall()
    finally:
        conn.close()


def working_set_drift(db_path, today=None):
    """The working-set drift check (the drift-scan pattern pointed at the
    working set). Findings, in pinned order:
    (a) restated — for each hat, its latest run_logs row: an active
        instruction whose body occurs in that next verbatim
        (case-insensitive substring; rephrased restatement is caught by
        review, not here);
    (b) dead scope — an active application-scoped instruction whose
        application id is missing from the derived status view or whose
        derived status is rejected / closed (a NULL status is live);
    (c) expired — an active instruction with valid_until < today ISO:
        flipped to status='expired' (the op's one mutation, same
        transaction as the reads) and reported.
    Returns the finding lines."""
    today = today or _today_iso()
    conn = db_connect(db_path)
    try:
        with conn:
            findings = []
            active = conn.execute(
                "SELECT id, body, scope_ref_type, scope_ref, valid_until "
                "FROM instruction WHERE status = 'active' ORDER BY id"
            ).fetchall()
            for hat, next_text in conn.execute(
                    "SELECT r.hat, r.next FROM run_logs r "
                    "WHERE r.id = (SELECT MAX(id) FROM run_logs "
                    "               WHERE hat = r.hat)"):
                low_next = (next_text or "").lower()
                for iid, body, _srt, _sr, _vu in active:
                    if body and body.lower() in low_next:
                        findings.append(
                            "restated: instruction %d restated in %s's "
                            "last next" % (iid, hat))
            for iid, _body, srt, sr, _vu in active:
                if srt != "application":
                    continue
                t = conn.execute(
                    "SELECT company, role, status FROM v_application_status "
                    "WHERE application_id = ?", (sr,)).fetchone()
                if t is None:
                    findings.append(
                        "dead scope: instruction %d (application %d is gone)"
                        % (iid, sr))
                elif t[2] in ("rejected", "closed"):
                    findings.append(
                        "dead scope: instruction %d (application %s / %s is %s)"
                        % (iid, t[0], t[1], t[2]))
            for iid, _body, _srt, _sr, vu in active:
                if vu is not None and vu < today:
                    conn.execute(
                        "UPDATE instruction SET status = 'expired', "
                        "updated_at = ? WHERE id = ?", (today, iid))
                    findings.append(
                        "expired: instruction %d (window ended %s)"
                        % (iid, vu))
            return findings
    finally:
        conn.close()


def neighbors(db_path, entity_type, entity_id, depth=1):
    """Walk the connected records around an entity, depth 1 or 2.
    Returns [(depth, rel, direction, other_type, other_id, attrs,
    provenance, governance_state, created_at)]. Visited (type, id) pairs
    are deduped; depth-2 neighbors are not walked (bounded). Unknown
    entity type, a missing row, or depth not in {1, 2} -> ValueError."""
    if entity_type not in ENTITIES:
        raise ValueError("unknown entity type %r" % (entity_type,))
    if depth not in (1, 2):
        raise ValueError("depth must be 1 or 2")
    conn = db_connect(db_path)
    try:
        table = ENTITIES[entity_type]["table"]
        if conn.execute("SELECT id FROM %s WHERE id = ?" % table,
                        (entity_id,)).fetchone() is None:
            raise ValueError("no %s with id %d" % (entity_type, entity_id))
        results = []
        visited = {(entity_type, entity_id)}
        frontier = [(entity_type, entity_id)]
        for d in (1, 2):
            if d > depth:
                break
            next_frontier = []
            for etype, eid in frontier:
                for edge in _walk_one(conn, etype, eid):
                    rel, direction, otype, oid = edge[0], edge[1], edge[2], edge[3]
                    if (otype, oid) in visited:
                        continue
                    visited.add((otype, oid))
                    results.append((d,) + edge)
                    next_frontier.append((otype, oid))
            frontier = next_frontier
        return results
    finally:
        conn.close()


def export_relationships(db_path, out_path):
    """Write one TSV row per junction row across all nine junction tables
    (pinned header; names resolved; attrs as k=v pairs; provenance +
    governance_state emitted from the rows). Atomic write. Returns the
    pathlib.Path."""
    out_path = pathlib.Path(out_path)
    header = ["junction", "from_type", "from_id", "from_name", "to_type",
              "to_id", "to_name", "attrs", "provenance", "governance_state",
              "created_at"]
    lines = [format_tsv_row(header)]
    conn = db_connect(db_path)
    try:
        for jname, spec in JUNCTIONS.items():
            table = spec["table"]
            ft, fcol = spec["from"]
            tt, tcol = spec["to"]
            attr_cols = ", ".join(
                "j.%s" % spec["attrs"][k][1] for k in spec["attrs"])
            sel = (
                "SELECT j.id, j.%s, e1.%s, j.%s, e2.%s, "
                "j.provenance, j.governance_state, j.created_at%s "
                "FROM %s j "
                "JOIN %s e1 ON e1.id = j.%s "
                "JOIN %s e2 ON e2.id = j.%s "
                "ORDER BY j.id"
                % (fcol, ENTITIES[ft]["label"], tcol,
                   ENTITIES[tt]["label"],
                   (", " + attr_cols) if attr_cols else "",
                   table,
                   ENTITIES[ft]["table"], fcol,
                   ENTITIES[tt]["table"], tcol))
            for r in conn.execute(sel):
                _id, fid, fname, tid, tname, prov, gov, created = r[:8]
                attr_vals = r[8:8 + len(spec["attrs"])]
                attrs = ",".join(
                    "%s=%s" % (k, v)
                    for k, v in zip(spec["attrs"], attr_vals)
                    if v is not None)
                lines.append(format_tsv_row(
                    [jname, ft, str(fid), fname, tt, str(tid), tname,
                     attrs, prov, gov, created]))
    finally:
        conn.close()
    write_atomic(out_path, ("\n".join(lines) + "\n").encode("utf-8"))
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="store.py", description="The career store ops (see standards/STANDARDS.md)."
    )
    sub = parser.add_subparsers(dest="op")
    sub.required = True

    p = sub.add_parser("migrate-applications",
                       help="one-shot: upgrade a pre-Phase-2 db onto the "
                            "application-keyed event table (byte-verified; "
                            "the legacy tables are dropped)")
    p.add_argument("--db", required=True)

    p = sub.add_parser(
        "repair",
        help="one-shot: link every orphaned event to its application on "
             "(company key, role) match; the ledger stays byte-stable")
    p.add_argument("--db", required=True)

    p = sub.add_parser("migrate", help="one-shot: the ledger TSV (and log TSVs) in, the db out")
    p.add_argument("--db", required=True)
    p.add_argument("--ledger", required=True)
    p.add_argument("--logs-dir",
                   help="the hat log TSVs directory (each file = one hat)")

    p = sub.add_parser("log-event",
                       help="append an event, linked to its application on "
                            "(company key, role) match; the application is "
                            "created only when the outcome sets a status")
    p.add_argument("--db", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--type", required=True, dest="etype")
    p.add_argument("--company", required=True)
    p.add_argument("--role", required=True)
    p.add_argument("--channel", required=True)
    p.add_argument("--outcome", required=True)
    p.add_argument("--note", required=True)
    p.add_argument("--url",
                   help="the posting's link — upserts the job_opening "
                        "(key: company + role + link) and attaches it to "
                        "the application in the same op")

    p = sub.add_parser("log-run", help="append a hat log row")
    p.add_argument("--db", required=True)
    p.add_argument("--hat", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--action", required=True)
    p.add_argument("--decision", required=True)
    p.add_argument("--next", required=True, dest="next_field")

    p = sub.add_parser("pickup", help="print a hat's last log row")
    p.add_argument("--db", required=True)
    p.add_argument("--hat", required=True)

    p = sub.add_parser("export-logs", help="regenerate the hat log TSVs")
    p.add_argument("--db", required=True)
    p.add_argument("--out-dir", required=True)

    p = sub.add_parser("export-claim", help="the benefit-claim one-pager for a date range")
    p.add_argument("--db", required=True)
    p.add_argument("--from", required=True, dest="date_from")
    p.add_argument("--to", required=True, dest="date_to")
    p.add_argument("--out", help="default: print to stdout")

    p = sub.add_parser("divergence",
                       help="check the markdown state files against "
                            "application state")
    p.add_argument("--db", required=True)
    p.add_argument("--qa", required=True, help="the QA markdown file")
    p.add_argument("--cast", required=True, help="the strategy cast markdown file")
    p.add_argument("--hubs", help="the interview hubs directory")

    p = sub.add_parser("export-ledger", help="regenerate the ledger TSV from events")
    p.add_argument("--db", required=True)
    p.add_argument("--out", required=True)

    p = sub.add_parser("status", help="application states")
    p.add_argument("--db", required=True)
    p.add_argument("--company")
    p.add_argument("--live", action="store_true",
                   help="exclude rejected/closed applications")

    p = sub.add_parser("caps", help="application counts per company (the pre-check)")
    p.add_argument("--db", required=True)
    p.add_argument("--company")

    p = sub.add_parser("upsert-contact",
                       help="create-or-verify a contact (key: name)")
    p.add_argument("--db", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--title")
    p.add_argument("--company")
    p.add_argument("--email")
    p.add_argument("--linkedin-ref", dest="linkedin_ref")
    p.add_argument("--how-met", dest="how_met")

    p = sub.add_parser("upsert-job-opening",
                       help="create-or-verify a job opening (key: company "
                            "+ title + link; the no-url form refuses a "
                            "title carrying several postings)")
    p.add_argument("--db", required=True)
    p.add_argument("--company", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--location")
    p.add_argument("--work-mode", dest="work_mode")
    p.add_argument("--source")
    p.add_argument("--url")
    p.add_argument("--posted-date", dest="posted_date")
    p.add_argument("--posted-comp", dest="posted_comp")
    p.add_argument("--jd-ref", dest="jd_ref")
    p.add_argument("--status", choices=list(JOB_OPENING_STATUSES))

    p = sub.add_parser("upsert-application",
                       help="create-or-verify an application "
                            "(key: company + role; reuses the ledger's row)")
    p.add_argument("--db", required=True)
    p.add_argument("--company", required=True)
    p.add_argument("--role", required=True)
    p.add_argument("--job-opening-id", type=int, dest="job_opening_id")
    p.add_argument("--contact")
    p.add_argument("--applied-date", dest="applied_date")

    p = sub.add_parser("interview",
                       help="create-or-verify an interview round "
                            "(key: application + round; status is set by "
                            "set-interview)")
    p.add_argument("--db", required=True)
    p.add_argument("--application-id", required=True, type=int,
                   dest="application_id")
    p.add_argument("--round", required=True)
    p.add_argument("--kind", choices=list(INTERVIEW_KINDS))
    p.add_argument("--scheduled-at", dest="scheduled_at")
    p.add_argument("--status", choices=list(INTERVIEW_STATUSES))
    p.add_argument("--feedback-ref", dest="feedback_ref")

    p = sub.add_parser("set-interview",
                       help="the only interview status mutation")
    p.add_argument("--db", required=True)
    p.add_argument("--id", required=True, type=int, dest="row_id")
    p.add_argument("--status", required=True,
                   choices=list(INTERVIEW_STATUSES))

    p = sub.add_parser("add-interaction",
                       help="insert an interaction (insert-only)")
    p.add_argument("--db", required=True)
    p.add_argument("--kind", required=True, choices=list(INTERACTION_KINDS))
    p.add_argument("--direction", required=True,
                   choices=list(INTERACTION_DIRECTIONS))
    p.add_argument("--occurred-at", required=True, dest="occurred_at")
    p.add_argument("--contact")
    p.add_argument("--company")
    p.add_argument("--application-id", type=int, dest="application_id")
    p.add_argument("--summary")

    p = sub.add_parser(
        "query",
        help="execute a validated retrieval plan (read-only; the "
             "analytical path — standards, The store)")
    p.add_argument("--db", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan")
    g.add_argument("--plan-file", dest="plan_file")
    g.add_argument("--example", action="store_true",
                   help="print the runnable sample plan (the one the "
                        "STANDARDS ops row carries) and exit")

    p = sub.add_parser("upsert-person", help="create-or-verify the single person row")
    p.add_argument("--db", required=True)
    p.add_argument("--full-name", required=True, dest="full_name")
    p.add_argument("--objective")
    p.add_argument("--location")
    p.add_argument("--as", choices=["user", "ai"], default="user", dest="as_user_flag")

    p = sub.add_parser("upsert-company", help="create-or-verify a company row (key: name)")
    p.add_argument("--db", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--industry")
    p.add_argument("--notes-ref", dest="notes_ref")
    p.add_argument("--as", choices=["user", "ai"], default="user", dest="as_user_flag")

    p = sub.add_parser("upsert-role", help="create-or-verify a role row (key: company + title + start_date)")
    p.add_argument("--db", required=True)
    p.add_argument("--company", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--start-date", dest="start_date")
    p.add_argument("--end-date", dest="end_date")
    p.add_argument("--is-current", type=int, choices=[0, 1], default=0, dest="is_current")
    p.add_argument("--summary-ref", dest="summary_ref")
    p.add_argument("--as", choices=["user", "ai"], default="user", dest="as_user_flag")

    p = sub.add_parser("upsert-project", help="create-or-verify a project row (key: name)")
    p.add_argument("--db", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--repo-ref", dest="repo_ref")
    p.add_argument("--summary-ref", dest="summary_ref")
    p.add_argument("--start-date", dest="start_date")
    p.add_argument("--end-date", dest="end_date")
    p.add_argument("--as", choices=["user", "ai"], default="user", dest="as_user_flag")

    p = sub.add_parser("upsert-skill", help="create-or-verify a skill row (key: name)")
    p.add_argument("--db", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--category")
    p.add_argument("--notes-ref", dest="notes_ref")
    p.add_argument("--as", choices=["user", "ai"], default="user", dest="as_user_flag")

    p = sub.add_parser("upsert-achievement", help="create-or-verify an achievement row (key: title)")
    p.add_argument("--db", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--summary-ref", dest="summary_ref")
    p.add_argument("--role-id", type=int, dest="role_id")
    p.add_argument("--project-id", type=int, dest="project_id")
    p.add_argument("--occurred-date", dest="occurred_date")
    p.add_argument("--as", choices=["user", "ai"], default="user", dest="as_user_flag")

    p = sub.add_parser("upsert-evidence", help="create-or-verify an evidence row (key: evid_id)")
    p.add_argument("--db", required=True)
    p.add_argument("--evid-id", required=True, dest="evid_id")
    p.add_argument("--claim", required=True)
    p.add_argument("--value")
    p.add_argument("--source-kind", choices=["code", "user_stated"], dest="source_kind")
    p.add_argument("--source-ref", dest="source_ref")
    p.add_argument("--as-of-date", dest="as_of_date")
    p.add_argument("--status", choices=["current", "struck"])

    p = sub.add_parser("upsert-document", help="create-or-verify a document row (key: doc_type + path + version)")
    p.add_argument("--db", required=True)
    p.add_argument("--doc-type", required=True, dest="doc_type")
    p.add_argument("--title", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--version", type=int, default=1)
    p.add_argument("--supersedes-id", type=int, dest="supersedes_id")
    p.add_argument("--third-party-safe", type=int, choices=[0, 1],
                   default=0, dest="is_third_party_safe")

    p = sub.add_parser("link", help="create a typed junction row")
    p.add_argument("--db", required=True)
    p.add_argument("--type", required=True, dest="junction")
    p.add_argument("--from", required=True, dest="from_ref")
    p.add_argument("--to", required=True, dest="to_ref")
    p.add_argument("--attr", action="append", default=[], dest="attrs")
    p.add_argument("--as", choices=["user", "ai"], default="user", dest="as_user_flag")

    p = sub.add_parser("verify", help="promote an ai_suggested junction row to user_verified")
    p.add_argument("--db", required=True)
    p.add_argument("--type", required=True, dest="junction")
    p.add_argument("--id", required=True, type=int, dest="row_id")

    p = sub.add_parser("reject", help="mark a junction row rejected_outdated")
    p.add_argument("--db", required=True)
    p.add_argument("--type", required=True, dest="junction")
    p.add_argument("--id", required=True, type=int, dest="row_id")

    p = sub.add_parser("unlink", help="mark a junction row rejected_outdated")
    p.add_argument("--db", required=True)
    p.add_argument("--type", required=True, dest="junction")
    p.add_argument("--id", required=True, type=int, dest="row_id")

    p = sub.add_parser("instruction", help="create an instruction row")
    p.add_argument("--db", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--kind", required=True, choices=list(INSTR_KINDS))
    p.add_argument("--scope-type", required=True, dest="scope_type",
                   choices=list(INSTR_SCOPES))
    p.add_argument("--scope-ref-type", dest="scope_ref_type",
                   choices=list(INSTR_SCOPE_REFS))
    p.add_argument("--scope-ref", type=int, dest="scope_ref")
    p.add_argument("--scope-ref-text", dest="scope_ref_text")
    p.add_argument("--stated-date", dest="stated_date")
    p.add_argument("--valid-until", dest="valid_until")
    p.add_argument("--supersedes", type=int)
    p.add_argument("--as", choices=["user", "ai"], default="user",
                   dest="as_user_flag")

    p = sub.add_parser("verify-instruction",
                       help="the only path from suggested to active")
    p.add_argument("--db", required=True)
    p.add_argument("--id", required=True, type=int, dest="row_id")

    p = sub.add_parser("withdraw-instruction",
                       help="mark an instruction withdrawn")
    p.add_argument("--db", required=True)
    p.add_argument("--id", required=True, type=int, dest="row_id")

    p = sub.add_parser("working-set-drift",
                       help="drift check over the working set (exit 1 on findings)")
    p.add_argument("--db", required=True)
    p.add_argument("--today")

    p = sub.add_parser("working-set",
                       help="the derived working set for a hat (standards: "
                            "the working-set rule)")
    p.add_argument("--db", required=True)
    p.add_argument("--hat", required=True)
    p.add_argument("--application-id", type=int, dest="application_id")

    p = sub.add_parser("neighbors",
                       help="walk the connected records around an entity")
    p.add_argument("--db", required=True)
    p.add_argument("--entity", required=True)
    p.add_argument("--id", required=True, type=int, dest="entity_id")
    p.add_argument("--depth", type=int, choices=[1, 2], default=1)

    p = sub.add_parser("governance", help="list governed rows in a state")
    p.add_argument("--db", required=True)
    p.add_argument("--state", required=True, choices=list(GOV_STATES))

    p = sub.add_parser("find-disconnected",
                       help="entities with no link, own FK, or inbound FK")
    p.add_argument("--db", required=True)
    p.add_argument("--entity")

    p = sub.add_parser("export-relationships",
                       help="write the junction rows as TSV (atomic)")
    p.add_argument("--db", required=True)
    p.add_argument("--out", required=True)

    args = parser.parse_args(argv)

    if args.op == "migrate-applications":
        res = migrate_applications(args.db)
        print("applications=%d events=%d instructions_remapped=%d "
              "dropped=%s" % (res["applications"], res["events"],
                              res["instructions_remapped"],
                              ",".join(res["dropped"])))
    elif args.op == "repair":
        res = repair(args.db)
        print("linked=%d" % res["linked"])
    elif args.op == "migrate":
        counts = migrate(args.db, args.ledger, logs_dir=args.logs_dir)
        print(
            "events=%(events)d applications=%(applications)d "
            "run_logs=%(run_logs)d" % counts
        )
    elif args.op == "log-event":
        eid = log_event(args.db, args.date, args.etype, args.company, args.role,
                        args.channel, args.outcome, args.note,
                        url=args.url)
        print("event %d" % eid)
    elif args.op == "log-run":
        rid = log_run(args.db, args.hat, args.date, args.task, args.action,
                      args.decision, args.next_field)
        print("log row %d" % rid)
    elif args.op == "pickup":
        row = pickup(args.db, args.hat)
        if row is None:
            print("(no rows for %s)" % args.hat)
        else:
            print(format_tsv_row(list(row)))
    elif args.op == "export-logs":
        for p in export_logs(args.db, args.out_dir):
            print("wrote %s" % (p,))
    elif args.op == "export-claim":
        text = export_claim(args.db, args.date_from, args.date_to, out_path=args.out)
        if args.out:
            print("wrote %s" % (args.out,))
        else:
            sys.stdout.write(text)
    elif args.op == "divergence":
        drift = divergence(args.db, args.qa, args.cast, hubs_dir=args.hubs)
        for line in drift:
            print(line)
        if drift:
            print("%d drift finding(s)" % len(drift))
            return 1
        print("clean")
        return 0
    elif args.op == "export-ledger":
        export_ledger(args.db, args.out)
        print("wrote %s" % (args.out,))
    elif args.op == "status":
        rows = status(args.db, company=args.company, live=args.live)
        print("company\trole\tstatus\tstatus_date\treq\tlast_activity")
        for company, role, st, sd, req, _le, ad, at, ao in rows:
            act = ("%s %s/%s" % (ad, at, ao)) if ad else ""
            print("%s\t%s\t%s\t%s\t%s\t%s"
                  % (company, role, st, sd, req or "", act))
        if args.company and not rows:
            near = near_companies(args.db, args.company)
            if near:
                print("no company matching %r; near: %s"
                      % (args.company, ", ".join(near)), file=sys.stderr)
    elif args.op == "caps":
        for company, count in caps(args.db, company=args.company):
            print("%s\t%d" % (company, count))
    elif args.op == "upsert-contact":
        rowid = upsert_contact(args.db, args.name, args.title, args.company,
                               args.email, args.linkedin_ref, args.how_met)
        print("id %d" % rowid)
    elif args.op == "upsert-job-opening":
        rowid = upsert_job_opening(
            args.db, args.company, args.title, args.location, args.work_mode,
            args.source, args.url, args.posted_date, args.posted_comp,
            args.jd_ref, args.status)
        print("id %d" % rowid)
    elif args.op == "upsert-application":
        rowid = upsert_application(args.db, args.company, args.role,
                                   args.job_opening_id, args.contact,
                                   args.applied_date)
        print("id %d" % rowid)
    elif args.op == "interview":
        rowid = interview(args.db, args.application_id, args.round,
                          args.kind, args.scheduled_at, args.status,
                          args.feedback_ref)
        print("id %d" % rowid)
    elif args.op == "set-interview":
        set_interview(args.db, args.row_id, args.status)
        print("interview %d -> %s" % (args.row_id, args.status))
    elif args.op == "add-interaction":
        rowid = add_interaction(args.db, args.kind, args.direction,
                                args.occurred_at, args.contact, args.company,
                                args.application_id, args.summary)
        print("id %d" % rowid)
    elif args.op == "query":
        if args.example:
            print(EXAMPLE_PLAN)
        else:
            plan = args.plan if args.plan is not None else \
                pathlib.Path(args.plan_file).read_text(encoding="utf-8")
            print(json.dumps(query(args.db, plan), indent=2))
    elif args.op == "upsert-person":
        rowid = upsert_person(args.db, args.full_name, args.objective,
                              args.location, as_user=(args.as_user_flag != "ai"))
        print("id %d" % rowid)
    elif args.op == "upsert-company":
        rowid = upsert_company(args.db, args.name, args.industry,
                               args.notes_ref, as_user=(args.as_user_flag != "ai"))
        print("id %d" % rowid)
    elif args.op == "upsert-role":
        rowid = upsert_role(args.db, args.company, args.title, args.start_date,
                            args.end_date, is_current=args.is_current,
                            summary_ref=args.summary_ref,
                            as_user=(args.as_user_flag != "ai"))
        print("id %d" % rowid)
    elif args.op == "upsert-project":
        rowid = upsert_project(args.db, args.name, args.repo_ref,
                               args.summary_ref, args.start_date, args.end_date,
                               as_user=(args.as_user_flag != "ai"))
        print("id %d" % rowid)
    elif args.op == "upsert-skill":
        rowid = upsert_skill(args.db, args.name, args.category,
                             args.notes_ref, as_user=(args.as_user_flag != "ai"))
        print("id %d" % rowid)
    elif args.op == "upsert-achievement":
        rowid = upsert_achievement(args.db, args.title, args.summary_ref,
                                   args.role_id, args.project_id,
                                   args.occurred_date,
                                   as_user=(args.as_user_flag != "ai"))
        print("id %d" % rowid)
    elif args.op == "upsert-evidence":
        rowid = upsert_evidence(args.db, args.evid_id, args.claim, args.value,
                                args.source_kind, args.source_ref,
                                args.as_of_date, args.status)
        print("id %d" % rowid)
    elif args.op == "upsert-document":
        rowid = upsert_document(args.db, args.doc_type, args.title, args.path,
                                args.version, args.supersedes_id,
                                args.is_third_party_safe)
        print("id %d" % rowid)
    elif args.op == "link":
        attrs = {}
        for a in args.attrs:
            if "=" not in a:
                parser.error("bad --attr %r (want K=V)" % (a,))
            k, v = a.split("=", 1)
            attrs[k] = v
        rowid = link(args.db, args.junction, args.from_ref, args.to_ref,
                     attrs, as_user=(args.as_user_flag != "ai"))
        print("link %d" % rowid)
    elif args.op == "verify":
        verify(args.db, args.junction, args.row_id)
        print("ok")
    elif args.op == "reject":
        reject(args.db, args.junction, args.row_id)
        print("ok")
    elif args.op == "unlink":
        unlink(args.db, args.junction, args.row_id)
        print("ok")
    elif args.op == "working-set-drift":
        drift = working_set_drift(
            args.db, to_iso(args.today) if args.today else None)
        for line in drift:
            print(line)
        if drift:
            print("%d drift finding(s)" % len(drift))
            return 1
        print("clean")
        return 0
    elif args.op == "working-set":
        print(format_tsv_row(["id", "kind", "scope", "body", "valid_until"]))
        for row in working_set(args.db, args.hat, args.application_id):
            print(format_tsv_row(
                ["" if v is None else str(v) for v in row]))
    elif args.op == "instruction":
        rowid = instruction(
            args.db, args.body, args.kind, args.scope_type,
            args.scope_ref_type, args.scope_ref, args.scope_ref_text,
            args.stated_date, args.valid_until, args.supersedes,
            as_user=(args.as_user_flag != "ai"))
        print("instruction %d" % rowid)
    elif args.op == "verify-instruction":
        verify_instruction(args.db, args.row_id)
        print("ok")
    elif args.op == "withdraw-instruction":
        withdraw_instruction(args.db, args.row_id)
        print("ok")
    elif args.op == "neighbors":
        print(format_tsv_row(
            ["depth", "rel", "direction", "type", "id", "attrs",
             "provenance", "governance_state", "created_at"]))
        for row in neighbors(args.db, args.entity, args.entity_id,
                             args.depth):
            print(format_tsv_row([str(v) for v in row]))
    elif args.op == "governance":
        print(format_tsv_row(
            ["table", "id", "name", "state", "provenance", "created_at"]))
        for table, rid, name, state, prov, created in \
                governance(args.db, args.state):
            print(format_tsv_row(
                [table, str(rid), name, state, prov, created]))
    elif args.op == "find-disconnected":
        for etype, eid, name in find_disconnected(args.db, args.entity):
            print(format_tsv_row([etype, str(eid), name]))
    elif args.op == "export-relationships":
        out = export_relationships(args.db, args.out)
        print("wrote %s" % out)


if __name__ == "__main__":
    sys.exit(main())
