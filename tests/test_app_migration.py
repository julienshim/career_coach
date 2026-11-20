import contextlib
import io
import pathlib
import sqlite3
import tempfile
import unittest

import scripts.store as store


# The v1 DDL, carried here as the migration's input contract (it leaves the
# product schema in Task 4; IF NOT EXISTS so the fixture works on both sides
# of that removal — the tables db_connect creates are exactly this shape).
LEGACY_DDL = """
CREATE TABLE IF NOT EXISTS events (
  id        INTEGER PRIMARY KEY,
  date      TEXT NOT NULL,
  date_iso  TEXT NOT NULL,
  type      TEXT NOT NULL,
  company   TEXT NOT NULL,
  role      TEXT NOT NULL,
  channel   TEXT NOT NULL,
  outcome   TEXT NOT NULL,
  note      TEXT NOT NULL,
  raw_row   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS threads (
  id              INTEGER PRIMARY KEY,
  company         TEXT NOT NULL,
  role            TEXT NOT NULL,
  req             TEXT,
  status          TEXT NOT NULL,
  status_date     TEXT NOT NULL,
  status_date_iso TEXT NOT NULL,
  last_event_id   INTEGER REFERENCES events(id),
  UNIQUE(company, role)
);
"""

HEADER = "Date\tType\tCompany/Contact\tRole\tMethod\tStage/Outcome\tNote"

# (date, type, company, role, channel, outcome, note)
EVENTS = [
    ("3/1/2026", "Job Application", "Acme", "Data Pipeline Engineer",
     "Company Portal", "Application Submitted", "portal, req #1001"),
    ("3/5/2026", "Interview", "Acme", "Data Pipeline Engineer",
     "Email", "Not Selected", "no"),
    ("3/2/2026", "Outreach", "Globex", "QA Engineer",
     "LinkedIn", "Outreach", "hi"),
    ("3/3/2026", "Profile", "n/a", "n/a",
     "n/a", "Profile Updated", "updated"),
    ("3/2/2026", "Job Application", "Initech", "Data Engineer",
     "Company Portal", "Application Submitted", "portal"),
]


def make_legacy_db(path):
    """A pre-Phase-2 store db: the current schema (fresh) plus the legacy
    events/threads/meta tables seeded with the fixture rows."""
    conn = store.db_connect(path)
    try:
        conn.executescript(LEGACY_DDL)
        for date, etype, company, role, channel, outcome, note in EVENTS:
            conn.execute(
                "INSERT INTO events (date, date_iso, type, company, role, "
                "channel, outcome, note, raw_row) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (date, store.to_iso(date), etype, company, role, channel,
                 outcome, note,
                 store.format_tsv_row(
                     [date, etype, company, role, channel, outcome, note])))
        conn.execute(
            "INSERT INTO threads (company, role, req, status, status_date, "
            "status_date_iso, last_event_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Acme", "Data Pipeline Engineer", "1001", "rejected",
             "3/5/2026", "2026-03-05", 2))
        conn.execute(
            "INSERT INTO threads (company, role, req, status, status_date, "
            "status_date_iso, last_event_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Initech", "Data Engineer", None, "submitted",
             "3/2/2026", "2026-03-02", 5))
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('ledger_header', ?)",
            (HEADER,))
        conn.execute(
            "INSERT INTO instruction (body, kind, scope_type, scope_ref_type, "
            "scope_ref, scope_ref_text, stated_date, valid_until, "
            "superseded_by, status, created_at, updated_at) "
            "VALUES (?, 'constraint', 'application', 'thread', ?, NULL, "
            "'2026-03-01', NULL, NULL, 'active', '2026-03-01', '2026-03-01')",
            ("thread rule", 1))
        conn.execute(
            "INSERT INTO instruction (body, kind, scope_type, scope_ref_type, "
            "scope_ref, scope_ref_text, stated_date, valid_until, "
            "superseded_by, status, created_at, updated_at) "
            "VALUES (?, 'priority', 'search_wide', NULL, NULL, NULL, "
            "'2026-03-01', NULL, NULL, 'active', '2026-03-01', '2026-03-01')",
            ("wide rule",))
        conn.commit()
    finally:
        conn.close()


def legacy_raw_rows(conn):
    """The legacy events' raw rows in ledger order ((date_iso, id)) — the
    byte-stability reference for the copy."""
    return [r[0] for r in conn.execute(
        "SELECT raw_row FROM events ORDER BY date_iso, id").fetchall()]


def raw_connect(path):
    """A plain connection — store.db_connect re-runs the schema, and the
    legacy DDL lives there until Task 4, so a product open would recreate
    the (empty) legacy tables and hide the drop. The first open after the
    op must be this one."""
    return sqlite3.connect(str(path))


class TestMigrateApplications(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "legacy.db"
        make_legacy_db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_happy_path(self):
        res = store.migrate_applications(self.db)
        self.assertEqual(
            res, {"applications": 2, "events": 5, "instructions_remapped": 1,
                  "dropped": ["threads", "events"]})
        conn = raw_connect(self.db)
        try:
            apps = conn.execute(
                "SELECT a.role, c.name FROM application a "
                "JOIN company c ON c.id = a.company_id ORDER BY a.id"
            ).fetchall()
            self.assertEqual(
                apps, [("Data Pipeline Engineer", "Acme"),
                       ("Data Engineer", "Initech")])
            acme = conn.execute(
                "SELECT id FROM application WHERE role = 'Data Pipeline "
                "Engineer'").fetchone()[0]
            initech = conn.execute(
                "SELECT id FROM application WHERE role = 'Data Engineer'"
            ).fetchone()[0]
            linked = dict(conn.execute(
                "SELECT id, application_id FROM event").fetchall())
            self.assertEqual(linked[1], acme)
            self.assertEqual(linked[2], acme)
            self.assertIsNone(linked[3])   # Globex outreach: no thread pair
            self.assertIsNone(linked[4])   # n/a
            self.assertEqual(linked[5], initech)
            keys = dict(conn.execute(
                "SELECT id, company_key FROM event").fetchall())
            self.assertEqual(keys[3], "Globex")
            self.assertEqual(keys[4], "n/a")
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertNotIn("threads", tables)
            self.assertNotIn("events", tables)
        finally:
            conn.close()

    def test_outreach_only_pair_gets_null_application(self):
        store.migrate_applications(self.db)
        conn = store.db_connect(self.db)
        try:
            self.assertIsNone(conn.execute(
                "SELECT application_id FROM event WHERE company_key = 'Globex'"
            ).fetchone()[0])
            self.assertIsNone(conn.execute(
                "SELECT a.id FROM application a JOIN company c "
                "ON c.id = a.company_id WHERE c.name = 'Globex'").fetchone())
        finally:
            conn.close()

    def test_event_raw_rows_byte_identical(self):
        # Data-level byte identity (the op's internal verification, pinned
        # from outside).
        conn = store.db_connect(self.db)
        expected = legacy_raw_rows(conn)
        conn.close()
        store.migrate_applications(self.db)
        conn = store.db_connect(self.db)
        try:
            got = [r[0] for r in conn.execute(
                "SELECT raw_row FROM event ORDER BY date_iso, id").fetchall()]
        finally:
            conn.close()
        self.assertEqual(got, expected)

    def test_export_ledger_file_byte_identical(self):
        # File-level pin (the plan's Task-2 deferral, now that
        # export-ledger reads the new table): the post-migration export
        # equals the header + legacy raw rows, byte for byte.
        conn = store.db_connect(self.db)
        header = conn.execute(
            "SELECT value FROM meta WHERE key = 'ledger_header'"
        ).fetchone()[0]
        expected = "\n".join([header] + legacy_raw_rows(conn)) + "\n"
        conn.close()
        store.migrate_applications(self.db)
        out = pathlib.Path(self.tmp.name) / "ledger.tsv"
        store.export_ledger(self.db, out)
        self.assertEqual(out.read_bytes().decode("utf-8"), expected)

    def test_cli_output_shape(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            store.main(["migrate-applications", "--db", str(self.db)])
        self.assertEqual(buf.getvalue().strip(),
                         "applications=2 events=5 instructions_remapped=1 "
                         "dropped=threads,events")

    def test_refuses_nonempty_new_event_table(self):
        conn = store.db_connect(self.db)
        try:
            conn.execute(
                "INSERT INTO event (date, date_iso, type, application_id, "
                "company_key, role, channel, outcome, note, raw_row, created_at) "
                "VALUES ('3/1/2026', '2026-03-01', 'Test', NULL, 'X', 'Y', "
                "'Email', 'Outreach', 'n', 'r', '2026-03-01')")
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(ValueError) as ctx:
            store.migrate_applications(self.db)
        self.assertIn("1", str(ctx.exception))
        conn = store.db_connect(self.db)
        try:
            # nothing was written: the legacy data is fully intact and the
            # new table still holds only the pre-seeded row
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], 5)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0], 2)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM event").fetchone()[0], 1)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM application").fetchone()[0],
                0)
        finally:
            conn.close()

    def test_noop_when_legacy_absent(self):
        fresh = pathlib.Path(self.tmp.name) / "fresh.db"
        store.db_connect(fresh)
        self.assertEqual(
            store.migrate_applications(fresh),
            {"applications": 0, "events": 0, "instructions_remapped": 0,
             "dropped": []})

    def test_instruction_without_thread_scope_untouched(self):
        store.migrate_applications(self.db)
        conn = store.db_connect(self.db)
        try:
            row = conn.execute(
                "SELECT kind, scope_type, scope_ref_type, scope_ref, status "
                "FROM instruction WHERE body = 'wide rule'").fetchone()
            self.assertEqual(
                row, ("priority", "search_wide", None, None, "active"))
            row = conn.execute(
                "SELECT scope_ref_type, scope_ref FROM instruction "
                "WHERE body = 'thread rule'").fetchone()
            self.assertEqual(row[0], "application")
            app_id = conn.execute(
                "SELECT id FROM application WHERE role = 'Data Pipeline "
                "Engineer'").fetchone()[0]
            self.assertEqual(row[1], app_id)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
