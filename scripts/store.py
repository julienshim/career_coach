#!/usr/bin/env python3
"""The career store — the system of record for the data layer.

The store holds the structured state of the job search: events (the ledger),
thread state (derived from events, never hand-set), and hat run logs. The
markdown narrative layer stays in the files; this is the data layer.

User-agnostic mechanism tooling: the db path is always passed in (--db); no
user path is hardcoded here. The ops are the only writer. Events are
append-only — there is no UPDATE or DELETE path. Exports reproduce stored
raw rows verbatim, so `export-ledger` / `export-logs` are byte-stable.

python3 stdlib only. No dependencies.
"""

import argparse
import os
import pathlib
import re
import sqlite3
import sys
import tempfile

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id        INTEGER PRIMARY KEY,        -- insertion order = ledger row number
  date      TEXT NOT NULL,              -- as recorded, e.g. '3/1/2026'
  date_iso  TEXT NOT NULL,              -- '2026-03-01' (range queries, benefit-claim week logic)
  type      TEXT NOT NULL,              -- the Activity Type value, as recorded
  company   TEXT NOT NULL,              -- raw Company/Contact value, as recorded
  role      TEXT NOT NULL,
  channel   TEXT NOT NULL,              -- the Method value, as recorded
  outcome   TEXT NOT NULL,              -- the Stage/Outcome value, as recorded
  note      TEXT NOT NULL,              -- third-party-safe (the standards contract); carries the link
  raw_row   TEXT NOT NULL               -- exact original line; the export reproduces it verbatim
);
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,               -- 'ledger_header', 'log_header:<hat>'
  value TEXT NOT NULL                   -- the file's exact header line
);
CREATE TABLE IF NOT EXISTS threads (
  id              INTEGER PRIMARY KEY,
  company         TEXT NOT NULL,        -- company key: the Company/Contact value before ' / '
  role            TEXT NOT NULL,
  req             TEXT,                 -- first 'req #?digits' found in a thread note, if any
  status          TEXT NOT NULL,        -- submitted | advanced | rejected | closed | paused
  status_date     TEXT NOT NULL,        -- as-recorded date of the event that set the status
  status_date_iso TEXT NOT NULL,
  last_event_id   INTEGER REFERENCES events(id),
  UNIQUE(company, role)
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
"""


# The flip table: outcome -> thread status. None = the event has no thread
# effect (outreach, profile updates, internal work, claims). Complete against
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

REQ_RE = re.compile(r"req #?(\d+)")


def company_key(company):
    """The company key: the Company/Contact value before ' / ' (the contact
    name and any URL never enter the key). 'n/a' stays 'n/a'."""
    if company == "n/a":
        return "n/a"
    return company.split(" / ")[0].strip()


def db_connect(db_path):
    """Open (creating if needed) the store db with WAL on and the schema present."""
    p = pathlib.Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
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


def build_threads(conn):
    """Derive thread state from events (never hand-set).

    One thread per (company key, role). Only status-setting events (FLIP !=
    None) with a real company and role create or update threads. The status
    is the FLIP of the latest such event in (date_iso, id) order; the req is
    the first 'req #?digits' found in a thread note, if any. Returns the
    thread count.
    """
    conn.execute("DELETE FROM threads")  # derived state: rebuilt, never edited
    events = conn.execute(
        "SELECT id, date, date_iso, company, role, outcome, note "
        "FROM events ORDER BY date_iso, id"
    ).fetchall()
    threads = {}
    for eid, date, d_iso, company, role, outcome, note in events:
        if outcome not in FLIP:
            raise ValueError("unknown outcome %r (event %d)" % (outcome, eid))
        if FLIP[outcome] is None or company == "n/a" or role == "n/a":
            continue
        key = (company_key(company), role)
        m = REQ_RE.search(note)
        req = m.group(1) if m else None
        t = threads.get(key)
        if t is None:
            threads[key] = [FLIP[outcome], date, d_iso, eid, req]
        else:
            t[0] = FLIP[outcome]
            t[1] = date
            t[2] = d_iso
            t[3] = eid
            if t[4] is None and req is not None:
                t[4] = req
    for (company, role), (status, date, d_iso, eid, req) in threads.items():
        conn.execute(
            "INSERT INTO threads "
            "(company, role, req, status, status_date, status_date_iso, last_event_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (company, role, req, status, date, d_iso, eid),
        )
    return len(threads)


LOG_HEADER = "Date\tTask\tAction\tDecision\tNext"


def migrate(db_path, ledger_path, logs_dir=None):
    """One-shot: the ledger TSV (and optionally the hat log TSVs) in, the db
    out. Fails closed (unknown shape, unknown outcome, malformed date —
    nothing is written when it raises) and refuses a non-empty db. Headers
    are captured into meta; every row is stored with its exact raw line so
    exports are byte-stable. A 4-field log row (missing trailing empty Next)
    is padded with next=''; any other shape fails.
    Returns {"events": int, "threads": int, "run_logs": int}.
    """
    conn = db_connect(db_path)
    try:
        n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
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
                conn.execute(
                    "INSERT INTO events "
                    "(date, date_iso, type, company, role, channel, outcome, note, raw_row) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (date, to_iso(date), etype, company, role, channel, outcome, note, raw),
                )
            build_threads(conn)
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
            "events": conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "threads": conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0],
            "run_logs": conn.execute("SELECT COUNT(*) FROM run_logs").fetchone()[0],
        }
        return counts
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
            for r in conn.execute("SELECT raw_row FROM events ORDER BY id").fetchall()
        ]
    finally:
        conn.close()
    data = "\n".join([header[0]] + rows) + "\n"
    write_atomic(out_path, data.encode("utf-8"))


def log_event(db_path, date, etype, company, role, channel, outcome, note):
    """Append an event and, when the outcome sets a status, flip its thread —
    one transaction, one op. Refuses PII patterns in the note, unknown
    outcomes, and malformed dates; nothing is written when it refuses.
    Returns the new event id.
    """
    to_iso(date)
    if outcome not in FLIP:
        raise ValueError("unknown outcome %r" % (outcome,))
    check_pii(note, "the note")
    conn = db_connect(db_path)
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO events "
                "(date, date_iso, type, company, role, channel, outcome, note, raw_row) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (date, to_iso(date), etype, company, role, channel, outcome, note,
                 format_tsv_row([date, etype, company, role, channel, outcome, note])),
            )
            eid = cur.lastrowid
            st = FLIP[outcome]
            if st is not None and company != "n/a" and role != "n/a":
                m = REQ_RE.search(note)
                conn.execute(
                    "INSERT INTO threads "
                    "(company, role, req, status, status_date, status_date_iso, last_event_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(company, role) DO UPDATE SET "
                    "status = excluded.status, "
                    "status_date = excluded.status_date, "
                    "status_date_iso = excluded.status_date_iso, "
                    "last_event_id = excluded.last_event_id, "
                    "req = COALESCE(threads.req, excluded.req)",
                    (company_key(company), role, m.group(1) if m else None,
                     st, date, to_iso(date), eid),
                )
        return eid
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
    """Check the markdown state files against thread state. Returns drift
    descriptions (empty = clean); the CLI exits non-zero on drift.

    v1 checks:
      1. QA presence — every company with >=1 Application Submitted event has
         a '## ' section naming it in the QA file.
      2. Hub recency — for each advanced thread whose company has
         <hubs>/<company>/README.md, the hub's '**Live state (M/D/YYYY)**'
         date >= the thread's status date. A missing hub is not drift (a
         round may not be live yet); a stale or malformed hub is.
      3. Cast naming — every advanced/rejected/closed thread's company is
         named in the cast file.
     A naming match is bidirectional and case-insensitive: a section or
     line's company part names a store key when either contains the other
     — naming drift is not drift, a company sharing no name at all is.
    """
    conn = db_connect(db_path)
    try:
        threads = conn.execute(
            "SELECT company, role, status, status_date, status_date_iso "
            "FROM threads ORDER BY id"
        ).fetchall()
        applied = set()
        for (c,) in conn.execute(
            "SELECT company FROM events WHERE outcome = 'Application Submitted'"
        ).fetchall():
            if c != "n/a":
                applied.add(company_key(c))
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

    # 3. Cast naming (per company: one naming covers all of its threads)
    cast_names = [_company_part(ln[2:])
                  for ln in _read_text(cast_path).split("\n")
                  if ln.startswith("- ")]
    cast_targets = sorted({
        company for company, _role, st, _sd, _sd_iso in threads
        if st in ("advanced", "rejected", "closed")
    })
    for company in cast_targets:
        if not any(_names_match(company, n) for n in cast_names):
            drift.append("cast: %r not named" % (company,))

    # 2. Hub recency
    if hubs_dir is not None:
        hubs_dir = pathlib.Path(hubs_dir)
        for company, role, st, sd, sd_iso in threads:
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
                    % (company, m.group(1), role, sd)
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
            "SELECT date, company, role, type FROM events "
            "WHERE date_iso >= ? AND date_iso <= ? ORDER BY date_iso, id",
            (d1, d2),
        ).fetchall()
    finally:
        conn.close()
    lines = [
        "%s  %s  %s  [%s]" % (date, company_key(company), role, etype)
        for date, company, role, etype in rows
    ]
    text = ("\n".join(lines) + "\n") if lines else ""
    if out_path is not None:
        write_atomic(out_path, text.encode("utf-8"))
    return text


def status(db_path, company=None, live=False):
    """Thread states: (company, role, status, status_date, req, last_event_id)
    in thread order. --live excludes rejected/closed."""
    conn = db_connect(db_path)
    try:
        sql = ("SELECT company, role, status, status_date, req, last_event_id "
               "FROM threads")
        where, args = [], []
        if company:
            where.append("company = ?")
            args.append(company)
        if live:
            where.append("status NOT IN ('rejected', 'closed')")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id"
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def caps(db_path, company=None):
    """Application counts per company key: [(company, count)] by count desc,
    then company asc. Companies with no applications are absent."""
    conn = db_connect(db_path)
    try:
        rows = conn.execute(
            "SELECT company FROM events WHERE outcome = 'Application Submitted'"
        ).fetchall()
    finally:
        conn.close()
    counts = {}
    for (c,) in rows:
        k = company_key(c)
        counts[k] = counts.get(k, 0) + 1
    if company:
        counts = {k: v for k, v in counts.items() if k == company}
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="store.py", description="The career store ops (see standards/STANDARDS.md)."
    )
    sub = parser.add_subparsers(dest="op")
    sub.required = True

    p = sub.add_parser("migrate", help="one-shot: the ledger TSV (and log TSVs) in, the db out")
    p.add_argument("--db", required=True)
    p.add_argument("--ledger", required=True)
    p.add_argument("--logs-dir",
                   help="the hat log TSVs directory (each file = one hat)")

    p = sub.add_parser("log-event",
                       help="append an event and flip its thread (one op)")
    p.add_argument("--db", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--type", required=True, dest="etype")
    p.add_argument("--company", required=True)
    p.add_argument("--role", required=True)
    p.add_argument("--channel", required=True)
    p.add_argument("--outcome", required=True)
    p.add_argument("--note", required=True)

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
                       help="check the markdown state files against thread state")
    p.add_argument("--db", required=True)
    p.add_argument("--qa", required=True, help="the QA markdown file")
    p.add_argument("--cast", required=True, help="the strategy cast markdown file")
    p.add_argument("--hubs", help="the interview hubs directory")

    p = sub.add_parser("export-ledger", help="regenerate the ledger TSV from events")
    p.add_argument("--db", required=True)
    p.add_argument("--out", required=True)

    p = sub.add_parser("status", help="thread states")
    p.add_argument("--db", required=True)
    p.add_argument("--company")
    p.add_argument("--live", action="store_true",
                   help="exclude rejected/closed threads")

    p = sub.add_parser("caps", help="application counts per company (the pre-check)")
    p.add_argument("--db", required=True)
    p.add_argument("--company")

    args = parser.parse_args(argv)

    if args.op == "migrate":
        counts = migrate(args.db, args.ledger, logs_dir=args.logs_dir)
        print(
            "events=%(events)d threads=%(threads)d run_logs=%(run_logs)d" % counts
        )
    elif args.op == "log-event":
        eid = log_event(args.db, args.date, args.etype, args.company, args.role,
                        args.channel, args.outcome, args.note)
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
        print("company\trole\tstatus\tstatus_date\treq")
        for company, role, st, sd, req, _le in rows:
            print("%s\t%s\t%s\t%s\t%s" % (company, role, st, sd, req or ""))
    elif args.op == "caps":
        for company, count in caps(args.db, company=args.company):
            print("%s\t%d" % (company, count))


if __name__ == "__main__":
    sys.exit(main())
