import datetime
import pathlib
import tempfile
import unittest

import scripts.store as store


class TestApplicationStatusView(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        self.conn = store.db_connect(self.db)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _seed(self, company, role, events):
        """events: [(date, outcome), ...] inserted in order; returns the
        application id. Raw-seeds the entity tables — the operational ops
        land in Task 5; the view is the unit under test."""
        cur = self.conn.execute(
            "INSERT INTO company (name, created_at, updated_at) "
            "VALUES (?, '2026-01-01', '2026-01-01')", (company,))
        cid = cur.lastrowid
        cur = self.conn.execute(
            "INSERT INTO application (company_id, role, created_at) "
            "VALUES (?, ?, '2026-01-01')", (cid, role))
        aid = cur.lastrowid
        for date, outcome in events:
            self.conn.execute(
                "INSERT INTO event (date, date_iso, type, application_id, "
                "company_key, role, channel, outcome, note, raw_row, created_at) "
                "VALUES (?, ?, 'Test', ?, ?, ?, 'Email', ?, 'note', 'raw', "
                "'2026-01-01')",
                (date, store.to_iso(date), aid, company, role, outcome))
        return aid

    def _view(self, aid):
        return self.conn.execute(
            "SELECT application_id, company, role, last_outcome, status_date, "
            "last_event_id, status FROM v_application_status "
            "WHERE application_id = ?", (aid,)).fetchone()

    def test_view_flips_each_status(self):
        for role, outcome, expected in [
            ("r1", "Application Submitted", "submitted"),
            ("r2", "Interview Invited", "advanced"),
            ("r3", "Not Selected", "rejected"),
            ("r4", "Position Filled", "closed"),
            ("r5", "Role Paused", "paused"),
        ]:
            aid = self._seed("Acme " + role, role, [("3/1/2026", outcome)])
            row = self._view(aid)
            self.assertEqual(row[6], expected)
            self.assertEqual(row[3], outcome)

    def test_view_last_event_by_date_order(self):
        # The advanced event is appended last but carries the OLDER date —
        # the derived status must follow (date_iso, id), never bare id.
        # A MAX(id) view would say 'advanced'.
        aid = self._seed("Globex", "Data Engineer", [
            ("3/1/2026", "Application Submitted"),
            ("3/5/2026", "Not Selected"),
            ("3/3/2026", "Rescheduled"),
        ])
        row = self._view(aid)
        self.assertEqual(row[6], "rejected")
        self.assertEqual(row[3], "Not Selected")
        # last_event_id is the 3/5 event (the 2nd inserted)
        self.assertEqual(row[5], 2)

    def test_view_no_status_events(self):
        aid = self._seed("Initech", "QA Engineer", [("3/2/2026", "Outreach")])
        row = self._view(aid)
        self.assertIsNotNone(row)
        self.assertIsNone(row[6])
        self.assertIsNone(row[5])

    def test_view_generated_from_flip(self):
        sql = store._status_view_sql()
        for outcome, st in store.FLIP.items():
            if st is None:
                self.assertNotIn("'%s'" % outcome, sql)
            else:
                self.assertIn("WHEN '%s' THEN '%s'" % (outcome, st), sql)


class TestOperationalEntityOps(unittest.TestCase):
    """The operational entity ops (Phase 2): contact / job-opening /
    application / interview / interaction. Ungoverned (no provenance
    columns in the shipped DDL); the create / idempotent-rerun /
    conflict-refuse shape, plus the must-exist target resolution."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.db_connect(self.db)
        # Seed (raw): two companies + one application. The company rows are
        # what the ops' must-exist resolution checks.
        conn = store.db_connect(self.db)
        try:
            cur = conn.execute(
                "INSERT INTO company (name, created_at, updated_at) "
                "VALUES ('Acme', '2026-01-01', '2026-01-01')")
            self.acid = cur.lastrowid
            conn.execute(
                "INSERT INTO application (company_id, role, created_at) "
                "VALUES (?, 'Data Engineer', '2026-01-01')", (self.acid,))
            cur = conn.execute(
                "INSERT INTO company (name, created_at, updated_at) "
                "VALUES ('Globex', '2026-01-01', '2026-01-01')")
            self.gcid = cur.lastrowid
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def row(self, table, rowid):
        conn = store.db_connect(self.db)
        try:
            cur = conn.execute("SELECT * FROM %s WHERE id = ?" % table,
                               (rowid,))
            r = cur.fetchone()
            return dict(zip([c[0] for c in cur.description], r)) if r else None
        finally:
            conn.close()

    def count(self, table):
        conn = store.db_connect(self.db)
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM " + table).fetchone()[0]
        finally:
            conn.close()

    def app_id(self):
        conn = store.db_connect(self.db)
        try:
            return conn.execute("SELECT id FROM application LIMIT 1"
                                ).fetchone()[0]
        finally:
            conn.close()

    # -- upsert-contact -----------------------------------------------------

    def test_contact_create_rerun_conflict(self):
        cid = store.upsert_contact(self.db, name="Jane", title="TA",
                                   company="Acme")
        row = self.row("contact", cid)
        self.assertEqual(row["title"], "TA")
        self.assertEqual(row["company_id"], self.acid)
        # idempotent rerun
        self.assertEqual(store.upsert_contact(self.db, name="Jane",
                                              title="TA", company="Acme"),
                         cid)
        self.assertEqual(self.count("contact"), 1)
        # a provided field differing from the stored non-NULL is refused
        with self.assertRaises(ValueError):
            store.upsert_contact(self.db, name="Jane", company="Globex")
        self.assertEqual(self.count("contact"), 1)

    def test_contact_missing_company_refused(self):
        with self.assertRaises(ValueError) as ctx:
            store.upsert_contact(self.db, name="Jane", company="Nobody")
        self.assertIn("Nobody", str(ctx.exception))
        self.assertEqual(self.count("contact"), 0)

    def test_contact_null_fill(self):
        cid = store.upsert_contact(self.db, name="Jane")
        self.assertIsNone(self.row("contact", cid)["company_id"])
        self.assertEqual(store.upsert_contact(self.db, name="Jane",
                                              how_met="referral"), cid)
        self.assertEqual(self.row("contact", cid)["how_met"], "referral")
        self.assertEqual(self.count("contact"), 1)

    # -- upsert-job-opening -------------------------------------------------

    def test_job_opening_create_default_status(self):
        jid = store.upsert_job_opening(self.db, company="Acme",
                                       title="Data Engineer",
                                       posted_date="3/1/2026")
        row = self.row("job_opening", jid)
        self.assertEqual(row["status"], "open")  # enum default
        self.assertEqual(row["posted_date"], "2026-03-01")  # ISO
        self.assertEqual(row["company_id"], self.acid)
        self.assertEqual(self.count("job_opening"), 1)
        # idempotent rerun
        self.assertEqual(store.upsert_job_opening(self.db, company="Acme",
                                                  title="Data Engineer",
                                                  posted_date="3/1/2026"),
                         jid)
        # a stored NULL may be filled; a stored non-NULL conflict is refused
        store.upsert_job_opening(self.db, company="Acme",
                                 title="Data Engineer", location="NYC")
        with self.assertRaises(ValueError):
            store.upsert_job_opening(self.db, company="Acme",
                                     title="Data Engineer", location="SF")
        self.assertEqual(self.count("job_opening"), 1)

    def test_job_opening_status_enum(self):
        with self.assertRaises(ValueError):
            store.upsert_job_opening(self.db, company="Acme", title="DE2",
                                     status="done")
        self.assertEqual(self.count("job_opening"), 0)
        jid = store.upsert_job_opening(self.db, company="Acme",
                                       title="DE2", status="closed")
        self.assertEqual(self.row("job_opening", jid)["status"], "closed")

    def test_job_opening_missing_company_refused(self):
        with self.assertRaises(ValueError) as ctx:
            store.upsert_job_opening(self.db, company="Nobody", title="DE")
        self.assertIn("Nobody", str(ctx.exception))
        self.assertEqual(self.count("job_opening"), 0)

    # -- upsert-application -------------------------------------------------

    def test_upsert_application_reuses_ledger_application(self):
        # The application the ledger path created is the same entity the
        # typed op resolves: same (company, role) key, one row.
        aid = store.upsert_application(self.db, company="Acme",
                                       role="Data Engineer")
        self.assertEqual(aid, self.app_id())
        self.assertEqual(self.count("application"), 1)

    def test_upsert_application_null_fill_and_conflict(self):
        aid = self.app_id()
        store.upsert_contact(self.db, name="Jane")
        jid = store.upsert_job_opening(self.db, company="Acme",
                                       title="Data Engineer")
        store.upsert_application(self.db, company="Acme",
                                 role="Data Engineer", contact="Jane",
                                 job_opening_id=jid,
                                 applied_date="3/1/2026")
        row = self.row("application", aid)
        self.assertIsNotNone(row["contact_id"])
        self.assertEqual(row["job_opening_id"], jid)
        self.assertEqual(row["applied_date"], "2026-03-01")
        # a stored non-NULL applied_date conflicts
        with self.assertRaises(ValueError):
            store.upsert_application(self.db, company="Acme",
                                     role="Data Engineer",
                                     applied_date="3/2/2026")
        self.assertEqual(self.count("application"), 1)

    def test_upsert_application_new_role_stamp_shape(self):
        aid2 = store.upsert_application(self.db, company="Acme",
                                        role="Search Infra")
        row = self.row("application", aid2)
        self.assertEqual(row["role"], "Search Infra")
        self.assertEqual(row["created_at"],
                         datetime.date.today().isoformat())
        self.assertNotIn("updated_at", row)  # the table has created_at only
        self.assertEqual(self.count("application"), 2)

    def test_upsert_application_missing_targets_refused(self):
        with self.assertRaises(ValueError) as ctx:
            store.upsert_application(self.db, company="Nobody", role="DE")
        self.assertIn("Nobody", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            store.upsert_application(self.db, company="Acme",
                                     role="Search Infra", contact="Nobody")
        self.assertIn("Nobody", str(ctx.exception))
        self.assertEqual(self.count("application"), 1)

    # -- interview / set-interview ------------------------------------------

    def test_interview_create_default_status(self):
        iid = store.interview(self.db, application_id=self.app_id(),
                              round="Phone Screen", kind="recruiter",
                              scheduled_at="3/10/2026")
        row = self.row("interview", iid)
        self.assertEqual(row["status"], "pending")  # enum default
        self.assertEqual(row["scheduled_at"], "2026-03-10")  # ISO
        # idempotent rerun (same application + round key)
        self.assertEqual(store.interview(self.db,
                                         application_id=self.app_id(),
                                         round="Phone Screen",
                                         kind="recruiter",
                                         scheduled_at="3/10/2026"), iid)
        self.assertEqual(self.count("interview"), 1)

    def test_interview_status_conflict_on_rerun(self):
        # A later call providing a different status is a conflict — the
        # lifecycle mutation is set-interview, never the upsert.
        iid = store.interview(self.db, application_id=self.app_id(),
                              round="Phone Screen")
        with self.assertRaises(ValueError):
            store.interview(self.db, application_id=self.app_id(),
                            round="Phone Screen", status="scheduled")
        store.set_interview(self.db, iid, "scheduled")
        self.assertEqual(self.row("interview", iid)["status"], "scheduled")

    def test_interview_kind_enum(self):
        with self.assertRaises(ValueError):
            store.interview(self.db, application_id=self.app_id(),
                            round="R1", kind="panel")
        self.assertEqual(self.count("interview"), 0)

    def test_interview_missing_application_refused(self):
        with self.assertRaises(ValueError):
            store.interview(self.db, application_id=999, round="R1")
        self.assertEqual(self.count("interview"), 0)

    def test_set_interview_enum_and_missing_refused(self):
        with self.assertRaises(ValueError):
            store.set_interview(self.db, 1, "happened")
        with self.assertRaises(ValueError):
            store.set_interview(self.db, 999, "scheduled")
        self.assertEqual(self.count("interview"), 0)

    # -- add-interaction ------------------------------------------------------

    def test_interaction_happy(self):
        store.upsert_contact(self.db, name="Jane")
        iid = store.add_interaction(self.db, kind="email", direction="out",
                                    occurred_at="3/12/2026", contact="Jane",
                                    company="Acme",
                                    application_id=self.app_id(),
                                    summary="sent the follow-up")
        row = self.row("interaction", iid)
        self.assertEqual(row["occurred_at"], "2026-03-12")  # ISO
        self.assertEqual(row["company_id"], self.acid)
        self.assertEqual(row["application_id"], self.app_id())
        self.assertNotIn("updated_at", row)  # insert-only table

    def test_interaction_enum_refusals(self):
        for kwargs in (dict(kind="letter", direction="out"),
                       dict(kind="email", direction="sideways")):
            with self.assertRaises(ValueError):
                store.add_interaction(self.db, occurred_at="3/12/2026",
                                      **kwargs)
        self.assertEqual(self.count("interaction"), 0)

    def test_interaction_missing_targets_refused(self):
        with self.assertRaises(ValueError) as ctx:
            store.add_interaction(self.db, kind="email", direction="out",
                                  occurred_at="3/12/2026", contact="Nobody")
        self.assertIn("Nobody", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            store.add_interaction(self.db, kind="email", direction="out",
                                  occurred_at="3/12/2026", company="Nobody")
        self.assertIn("Nobody", str(ctx.exception))
        with self.assertRaises(ValueError):
            store.add_interaction(self.db, kind="email", direction="out",
                                  occurred_at="3/12/2026",
                                  application_id=999)
        self.assertEqual(self.count("interaction"), 0)


if __name__ == "__main__":
    unittest.main()
