import datetime
import pathlib
import sqlite3
import tempfile
import unittest

import scripts.store as store

PHASE1_TABLES = ["person", "company", "role", "project", "skill", "achievement",
                 "evidence", "document", "contact", "job_opening", "application",
                 "interview", "interaction", "note", "note_reference",
                 "achievement_skill", "achievement_evidence", "resume_achievement",
                 "document_achievement", "project_skill", "job_skill",
                 "application_document", "application_contact", "contact_company",
                 "instruction"]

# The pre-Phase-1 DDL (the four original tables), inlined to simulate a legacy db.
OLD_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS run_logs (
  id       INTEGER PRIMARY KEY,
  hat      TEXT NOT NULL,
  date     TEXT NOT NULL,
  date_iso TEXT NOT NULL,
  task     TEXT NOT NULL,
  action   TEXT NOT NULL,
  decision TEXT NOT NULL,
  next     TEXT NOT NULL,
  raw_row  TEXT NOT NULL
);
"""


def _table_names(conn):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(conn, table):
    return {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}


class TestSchema(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_db_has_all_phase1_tables(self):
        conn = store.db_connect(self.db)
        try:
            self.assertTrue(set(PHASE1_TABLES) <= _table_names(conn))
        finally:
            conn.close()

    def test_existing_tables_unchanged(self):
        conn = store.db_connect(self.db)
        try:
            self.assertEqual(_columns(conn, "events"),
                             {"id", "date", "date_iso", "type", "company", "role",
                              "channel", "outcome", "note", "raw_row"})
            self.assertEqual(_columns(conn, "meta"), {"key", "value"})
            self.assertEqual(_columns(conn, "threads"),
                             {"id", "company", "role", "req", "status",
                              "status_date", "status_date_iso", "last_event_id"})
            self.assertEqual(_columns(conn, "run_logs"),
                             {"id", "hat", "date", "date_iso", "task", "action",
                              "decision", "next", "raw_row"})
        finally:
            conn.close()

    def test_old_db_upgrades_on_open(self):
        # A legacy db: only the four pre-Phase-1 tables, one synthetic event.
        legacy = pathlib.Path(self.tmp.name) / "legacy.db"
        conn = sqlite3.connect(str(legacy))
        conn.executescript(OLD_SCHEMA)
        conn.execute(
            "INSERT INTO events (date, date_iso, type, company, role, channel, "
            "outcome, note, raw_row) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("1/2/2026", "2026-01-02", "Job Application", "Acme", "Data Engineer",
             "Company Portal", "Application Submitted", "synthetic", "raw"))
        conn.commit()
        conn.close()
        # Open it with the store: the new tables appear, the old row is intact.
        conn = store.db_connect(legacy)
        try:
            self.assertTrue(set(PHASE1_TABLES) <= _table_names(conn))
            n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            self.assertEqual(n, 1)
        finally:
            conn.close()


class TestUpserts(unittest.TestCase):
    """The create / idempotent-rerun / conflict-refuse shapes, per entity."""

    # (op, create kwargs, conflict kwargs [same key, one non-key field differs],
    #  table, where-dict for the row check)
    def _specs(self):
        return [
            (store.upsert_person,      {"full_name": "P", "location": "SF"},
                                 {"full_name": "P2", "location": "SF"},
                                 "person", {"full_name": "P"}),
            (store.upsert_company,     {"name": "C", "industry": "data"},
                                 {"name": "C", "industry": "analytics"},
                                 "company", {"name": "C"}),
            (store.upsert_role,        {"company": "C", "title": "DE", "end_date": "5/5/2026"},
                                 {"company": "C", "title": "DE", "end_date": "5/6/2026"},
                                 "role", {"title": "DE", "end_date": "2026-05-05"}),
            (store.upsert_project,     {"name": "Pj", "repo_ref": "r1"},
                                 {"name": "Pj", "repo_ref": "r2"},
                                 "project", {"name": "Pj"}),
            (store.upsert_skill,       {"name": "S", "category": "technical"},
                                 {"name": "S", "category": "domain"},
                                 "skill", {"name": "S"}),
            (store.upsert_achievement, {"title": "A", "summary_ref": "s1"},
                                 {"title": "A", "summary_ref": "s2"},
                                 "achievement", {"title": "A"}),
            (store.upsert_evidence,    {"evid_id": "EV-1", "claim": "c1"},
                                 {"evid_id": "EV-1", "claim": "c2"},
                                 "evidence", {"evid_id": "EV-1"}),
            (store.upsert_document,    {"doc_type": "resume", "title": "D1", "path": "p.md"},
                                 {"doc_type": "resume", "title": "D2", "path": "p.md"},
                                 "document", {"path": "p.md"}),
        ]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        self.conn = store.db_connect(self.db)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _row(self, table, **where):
        cur = self.conn.execute(
            "SELECT * FROM %s WHERE " % table + " AND ".join(
                "%s = ?" % k for k in where), list(where.values()))
        r = cur.fetchone()
        return dict(zip([c[0] for c in cur.description], r)) if r else None

    def _count(self, table):
        return self.conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]

    def test_create_returns_id_and_row(self):
        today = datetime.date.today().isoformat()
        for op, create, _conflict, table, where in self._specs():
            with self.subTest(table=table):
                if op is store.upsert_role:
                    store.upsert_company(self.db, "C")
                rowid = op(self.db, **create)
                self.assertIsInstance(rowid, int)
                row = self._row(table, **where)
                self.assertIsNotNone(row)
                self.assertEqual(row["id"], rowid)
                self.assertEqual(row["created_at"], today)
                self.assertEqual(row["updated_at"], today)
                # provenance enum: user / imported / ai; user_fact is the
                # governance_state value (the spec's two enums)
                if table in ("role", "project", "skill", "achievement", "document"):
                    self.assertEqual(row["provenance"], "user")
                    self.assertEqual(row["governance_state"], "user_fact")

    def test_rerun_identical_is_noop(self):
        for op, create, _conflict, table, where in self._specs():
            with self.subTest(table=table):
                if op is store.upsert_role:
                    store.upsert_company(self.db, "C")
                rowid = op(self.db, **create)
                op(self.db, **create)
                self.assertEqual(self._count(table), 1)
                self.assertEqual(self._row(table, **where)["id"], rowid)

    def test_conflicting_field_refused(self):
        for op, create, conflict, table, _where in self._specs():
            with self.subTest(table=table):
                if op is store.upsert_role:
                    store.upsert_company(self.db, "C")
                op(self.db, **create)
                with self.assertRaises(ValueError):
                    op(self.db, **conflict)
                self.assertEqual(self._count(table), 1)

    def test_null_fill_updates_row(self):
        # updated_at is day-granular ISO; a same-day fill writes the same value,
        # so the observable effects are the filled column, the same id, no new row.
        store.upsert_skill(self.db, name="F")
        rowid = store.upsert_skill(self.db, name="F", notes_ref="n.md")
        row = self._row("skill", name="F")
        self.assertEqual(row["id"], rowid)
        self.assertEqual(row["notes_ref"], "n.md")
        self.assertEqual(self._count("skill"), 1)

    def test_person_single_row_rule(self):
        rowid = store.upsert_person(self.db, full_name="P")
        self.assertEqual(store.upsert_person(self.db, full_name="P"), rowid)
        with self.assertRaises(ValueError):
            store.upsert_person(self.db, full_name="Q")
        self.assertEqual(self._count("person"), 1)

    def test_role_unknown_company_refused(self):
        with self.assertRaises(ValueError):
            store.upsert_role(self.db, company="Nobody", title="DE")
        self.assertEqual(self._count("role"), 0)

    def test_ai_provenance_governance(self):
        store.upsert_skill(self.db, name="AI-S", as_user=False)
        row = self._row("skill", name="AI-S")
        self.assertEqual(row["provenance"], "ai")
        self.assertEqual(row["governance_state"], "ai_suggested")

    def test_evidence_defaults(self):
        store.upsert_evidence(self.db, evid_id="EV-9", claim="c")
        row = self._row("evidence", evid_id="EV-9")
        self.assertEqual(row["source_kind"], "user_stated")
        self.assertEqual(row["status"], "current")


if __name__ == "__main__":
    unittest.main()
