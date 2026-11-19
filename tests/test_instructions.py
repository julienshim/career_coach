import contextlib
import datetime
import io
import pathlib
import tempfile
import unittest

import scripts.store as store


class TestInstructions(unittest.TestCase):
    """instruction / verify-instruction / withdraw-instruction."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        self.conn = store.db_connect(self.db)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _row(self, rowid):
        cur = self.conn.execute("SELECT * FROM instruction WHERE id = ?",
                                (rowid,))
        r = cur.fetchone()
        return dict(zip([c[0] for c in cur.description], r)) if r else None

    def _count(self):
        return self.conn.execute("SELECT COUNT(*) FROM instruction").fetchone()[0]

    def test_user_instruction_active(self):
        today = datetime.date.today().isoformat()
        rowid = store.instruction(self.db, "keep follow-ups under 2",
                                  "preference", "search_wide")
        row = self._row(rowid)
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["stated_date"], today)  # defaults to today
        self.assertEqual(row["created_at"], today)
        self.assertEqual(row["updated_at"], today)
        # explicit dates are M/D/YYYY as stated, stored ISO
        r2 = store.instruction(self.db, "chase X by Friday", "priority",
                               "search_wide",
                               stated_date="1/15/2026",
                               valid_until="1/23/2026")
        row2 = self._row(r2)
        self.assertEqual(row2["stated_date"], "2026-01-15")
        self.assertEqual(row2["valid_until"], "2026-01-23")

    def test_ai_instruction_suggested(self):
        rowid = store.instruction(self.db, "try the SQL framing",
                                  "preference", "search_wide", as_user=False)
        self.assertEqual(self._row(rowid)["status"], "suggested")

    def test_verify_flips_suggested_to_active(self):
        rowid = store.instruction(self.db, "draft the cover letter",
                                  "preference", "search_wide", as_user=False)
        self.assertEqual(self._row(rowid)["status"], "suggested")
        store.verify_instruction(self.db, rowid)
        self.assertEqual(self._row(rowid)["status"], "active")

    def test_verify_refuses_non_suggested(self):
        rowid = store.instruction(self.db, "active row", "preference",
                                  "search_wide")
        with self.assertRaises(ValueError):
            store.verify_instruction(self.db, rowid)
        with self.assertRaises(ValueError):
            store.verify_instruction(self.db, 99)

    def test_withdraw_marks(self):
        a = store.instruction(self.db, "active one", "preference",
                              "search_wide")
        s = store.instruction(self.db, "suggested one", "preference",
                              "search_wide", as_user=False)
        store.withdraw_instruction(self.db, a)
        self.assertEqual(self._row(a)["status"], "withdrawn")
        store.withdraw_instruction(self.db, s)
        self.assertEqual(self._row(s)["status"], "withdrawn")
        with self.assertRaises(ValueError):
            store.withdraw_instruction(self.db, a)
        with self.assertRaises(ValueError):
            store.withdraw_instruction(self.db, 99)

    def test_supersede_atomic(self):
        old = store.instruction(self.db, "old directive", "preference",
                                "search_wide")
        new = store.instruction(self.db, "new directive", "preference",
                                "search_wide", supersedes=old)
        orow, nrow = self._row(old), self._row(new)
        self.assertEqual(orow["status"], "superseded")
        self.assertEqual(orow["superseded_by"], new)
        self.assertEqual(nrow["status"], "active")

    def test_supersede_refuses_dead_target(self):
        old = store.instruction(self.db, "old", "preference", "search_wide")
        store.withdraw_instruction(self.db, old)
        with self.assertRaises(ValueError):
            store.instruction(self.db, "new", "preference", "search_wide",
                              supersedes=old)
        self.assertEqual(self._row(old)["status"], "withdrawn")  # untouched
        with self.assertRaises(ValueError):
            store.instruction(self.db, "new2", "preference", "search_wide",
                              supersedes=99)
        self.assertEqual(self._count(), 1)

    def test_bad_enums_refused(self):
        with self.assertRaises(ValueError):
            store.instruction(self.db, "b", "urgency", "search_wide")
        with self.assertRaises(ValueError):
            store.instruction(self.db, "b", "preference", "global")
        with self.assertRaises(ValueError):
            store.instruction(self.db, "b", "preference", "application",
                              scope_ref_type="thread2")
        self.assertEqual(self._count(), 0)

    def test_thread_scope_shape(self):
        # the Phase-1 workhorse: an application-scoped directive pointed at
        # a live thread
        store.log_event(self.db, "11/17/2026", "Job Application", "Acme",
                        "Data Engineer", "Company Portal",
                        "Application Submitted", "synthetic")
        tid = self.conn.execute("SELECT id FROM threads ORDER BY id"
                                ).fetchone()[0]
        rowid = store.instruction(self.db, "keep the follow-up cadence here",
                                  "constraint", "application",
                                  scope_ref_type="thread", scope_ref=tid)
        row = self._row(rowid)
        self.assertEqual(row["scope_type"], "application")
        self.assertEqual(row["scope_ref_type"], "thread")
        self.assertEqual(row["scope_ref"], tid)


def _md(iso_date):
    """ISO -> M/D/YYYY (as stated), the input shape the ops take."""
    d = datetime.date.fromisoformat(iso_date)
    return "%d/%d/%d" % (d.month, d.day, d.year)


class TestWorkingSet(unittest.TestCase):
    """The derived working set: active + in-scope + unexpired (spec 5.7)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        self.conn = store.db_connect(self.db)
        # Three threads: live A (submitted), live B (submitted),
        # rejected C (submitted, then not selected).
        for role in ("Role A", "Role B", "Role C"):
            store.log_event(self.db, "11/10/2026", "Job Application", "Acme",
                            role, "Company Portal", "Application Submitted",
                            "synthetic")
        store.log_event(self.db, "11/15/2026", "Follow-up", "Acme", "Role C",
                        "Email", "Not Selected", "synthetic")
        self.tA = self.conn.execute(
            "SELECT id FROM threads WHERE role = 'Role A'").fetchone()[0]
        self.tB = self.conn.execute(
            "SELECT id FROM threads WHERE role = 'Role B'").fetchone()[0]
        self.tC = self.conn.execute(
            "SELECT id FROM threads WHERE role = 'Role C'").fetchone()[0]
        today = datetime.date.today().isoformat()
        yesterday = (datetime.date.today()
                     - datetime.timedelta(days=1)).isoformat()
        # The mixed instruction set (the brief's pinned ten):
        # i1 search_wide active; i2 hat 'sourcing' active; i3 hat
        # 'interview' active; i4 thread A active, no expiry; i5 thread C
        # (rejected) active; i6 valid_until yesterday; i7 valid_until
        # today; i8 withdrawn; i9 suggested (ai); i10 superseded by i11.
        # Ruling: i11 is created --as ai so it lands 'suggested' — the
        # pinned sets {i1,i2,i4,i5,i7} / {i1,i3} are exact only when the
        # supersede's successor is not active (the op always creates one).
        self.i1 = store.instruction(
            self.db, "directive\tone", "preference", "search_wide")
        self.i2 = store.instruction(
            self.db, "hat sourcing rule", "preference", "hat",
            scope_ref_type="hat", scope_ref_text="sourcing")
        self.i3 = store.instruction(
            self.db, "hat interview rule", "preference", "hat",
            scope_ref_type="hat", scope_ref_text="interview")
        self.i4 = store.instruction(
            self.db, "thread A rule", "constraint", "application",
            scope_ref_type="thread", scope_ref=self.tA)
        self.i5 = store.instruction(
            self.db, "thread C rule", "constraint", "application",
            scope_ref_type="thread", scope_ref=self.tC)
        self.i6 = store.instruction(
            self.db, "closed yesterday", "preference", "search_wide",
            valid_until=_md(yesterday))
        self.i7 = store.instruction(
            self.db, "closes today", "priority", "search_wide",
            valid_until=_md(today))
        self.i8 = store.instruction(
            self.db, "withdrawn one", "preference", "search_wide")
        store.withdraw_instruction(self.db, self.i8)
        self.i9 = store.instruction(
            self.db, "suggested one", "preference", "search_wide",
            as_user=False)
        self.i10 = store.instruction(
            self.db, "old directive", "preference", "search_wide")
        self.i11 = store.instruction(
            self.db, "new directive", "preference", "search_wide",
            supersedes=self.i10, as_user=False)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_working_set_exact_ids(self):
        # row 5 is mechanically present: liveness is the drift check's
        # job (Task 8), not the query's — spec 5.7 is active + scope +
        # unexpired
        rows = store.working_set(self.db, "sourcing")
        self.assertEqual({r[0] for r in rows},
                         {self.i1, self.i2, self.i4, self.i5, self.i7})
        # the pinned row shape: (id, kind, scope, body, valid_until) with
        # scope rendered search_wide / hat:<name> / thread:<id>; ordered
        self.assertEqual(rows[0], (self.i1, "preference", "search_wide",
                                   "directive\tone", None))
        self.assertEqual([r[0] for r in rows],
                         sorted(r[0] for r in rows))
        by_id = {r[0]: r for r in rows}
        self.assertEqual(by_id[self.i2][2], "hat:sourcing")
        self.assertEqual(by_id[self.i4][2], "thread:%d" % self.tA)

    def test_working_set_other_hat(self):
        # Ruling: the pinned set {i1, i3} is inconsistent with the pinned
        # query — unfiltered, thread-scoped rows (i4, i5) are in every
        # hat's set, as the pinned sourcing set {i1,i2,i4,i5,i7} and the
        # row-5 comment both confirm. The query (Shared behaviors) wins.
        rows = store.working_set(self.db, "interview")
        self.assertEqual({r[0] for r in rows},
                         {self.i1, self.i3, self.i4, self.i5, self.i7})
        hat_rows = {r[0] for r in rows if r[2].startswith("hat:")}
        self.assertEqual(hat_rows, {self.i3})

    def test_thread_filter(self):
        rows = store.working_set(self.db, "sourcing", thread_id=self.tA)
        self.assertEqual({r[0] for r in rows},
                         {self.i1, self.i2, self.i4, self.i7})
        rows = store.working_set(self.db, "sourcing", thread_id=self.tB)
        # the Review-Focus scope-bleed pin: thread-4's row is ABSENT
        self.assertEqual({r[0] for r in rows}, {self.i1, self.i2, self.i7})

    def test_boundary_today_included(self):
        today = datetime.date.today().isoformat()
        rows = store.working_set(self.db, "sourcing", today=today)
        ids = {r[0] for r in rows}
        self.assertIn(self.i7, ids)     # window closing today: in force
        self.assertNotIn(self.i6, ids)  # window ended yesterday

    def test_cli_output_shape(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            store.main(["working-set", "--db", str(self.db),
                        "--hat", "sourcing"])
        lines = buf.getvalue().splitlines()
        self.assertEqual(lines[0], "id\tkind\tscope\tbody\tvalid_until")
        # body intact through format_tsv_row (the tab is quoted); row 5
        # (the dead thread C) is mechanically present in the unfiltered
        # set — liveness is the drift check's job
        self.assertEqual(lines[1:], [
            store.format_tsv_row([str(self.i1), "preference", "search_wide",
                                  "directive\tone", ""]),
            store.format_tsv_row([str(self.i2), "preference", "hat:sourcing",
                                  "hat sourcing rule", ""]),
            store.format_tsv_row([str(self.i4), "constraint",
                                  "thread:%d" % self.tA, "thread A rule",
                                  ""]),
            store.format_tsv_row([str(self.i5), "constraint",
                                  "thread:%d" % self.tC, "thread C rule",
                                  ""]),
            store.format_tsv_row([str(self.i7), "priority", "search_wide",
                                  "closes today",
                                  datetime.date.today().isoformat()]),
        ])


class TestWorkingSetDrift(unittest.TestCase):
    """working-set-drift: restated / dead scope / expired (the flip)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        self.conn = store.db_connect(self.db)
        # Threads: live A (submitted), rejected C (submitted, not selected)
        for role in ("Role A", "Role C"):
            store.log_event(self.db, "11/10/2026", "Job Application", "Acme",
                            role, "Company Portal", "Application Submitted",
                            "synthetic")
        store.log_event(self.db, "11/15/2026", "Follow-up", "Acme", "Role C",
                        "Email", "Not Selected", "synthetic")
        self.tA = self.conn.execute(
            "SELECT id FROM threads WHERE role = 'Role A'").fetchone()[0]
        self.tC = self.conn.execute(
            "SELECT id FROM threads WHERE role = 'Role C'").fetchone()[0]
        # hat 'sourcing': the OLDER row carries X's body (not flaggable);
        # the LATEST row carries Y's body verbatim but case-shifted, and a
        # REPHRASED occurrence of Z's body (not a substring)
        store.log_run(self.db, "sourcing", "11/16/2026", "review", "scan",
                      "kept", "old directive text")
        store.log_run(self.db, "sourcing", "11/17/2026", "review", "scan",
                      "kept", "KEEP FOLLOW-UPS SHORT and try to chase that "
                              "referral soon")
        self.iY = store.instruction(self.db, "keep follow-ups short",
                                    "preference", "search_wide")
        self.iZ = store.instruction(self.db, "chase the referral by friday",
                                    "priority", "search_wide")
        self.iX = store.instruction(self.db, "old directive text",
                                    "preference", "search_wide")
        self.iDead = store.instruction(
            self.db, "dead thread rule", "constraint", "application",
            scope_ref_type="thread", scope_ref=self.tC)
        self.iGone = store.instruction(
            self.db, "missing thread rule", "constraint", "application",
            scope_ref_type="thread", scope_ref=999)
        self.iLive = store.instruction(
            self.db, "live thread rule", "constraint", "application",
            scope_ref_type="thread", scope_ref=self.tA)
        self.yesterday = (datetime.date.today()
                          - datetime.timedelta(days=1)).isoformat()
        self.iExp = store.instruction(self.db, "closes soon", "priority",
                                      "search_wide",
                                      valid_until=_md(self.yesterday))

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _row(self, rowid):
        cur = self.conn.execute("SELECT * FROM instruction WHERE id = ?",
                                (rowid,))
        r = cur.fetchone()
        return dict(zip([c[0] for c in cur.description], r)) if r else None

    def test_restated_flagged(self):
        findings = store.working_set_drift(self.db)
        restated = [f for f in findings if f.startswith("restated:")]
        # exactly Y: verbatim (case-insensitive) in the LATEST next; Z is
        # only rephrased, X only in the older row
        self.assertEqual(
            restated,
            ["restated: instruction %d restated in sourcing's last next"
             % self.iY])

    def test_dead_scope_flagged(self):
        findings = store.working_set_drift(self.db)
        dead = [f for f in findings if f.startswith("dead scope:")]
        self.assertEqual(dead, [
            "dead scope: instruction %d (thread Acme / Role C is rejected)"
            % self.iDead,
            "dead scope: instruction %d (thread 999 is gone)" % self.iGone,
        ])  # the live thread's instruction is clean

    def test_expired_flipped_and_reported(self):
        findings = store.working_set_drift(self.db)
        self.assertIn(
            "expired: instruction %d (window ended %s)"
            % (self.iExp, self.yesterday), findings)
        self.assertEqual(self._row(self.iExp)["status"], "expired")
        # a second run does not re-report it
        findings2 = store.working_set_drift(self.db)
        self.assertNotIn(
            "expired: instruction %d (window ended %s)"
            % (self.iExp, self.yesterday), findings2)

    def test_clean_exit(self):
        clean_db = pathlib.Path(self.tmp.name) / "clean.db"
        store.db_connect(clean_db)
        store.log_run(clean_db, "sourcing", "11/17/2026", "review", "scan",
                      "kept", "nothing to flag here")
        self.assertEqual(store.working_set_drift(clean_db), [])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = store.main(["working-set-drift", "--db", str(clean_db)])
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue().strip(), "clean")
        # findings: one line each, a count line, exit 1 (the divergence
        # pattern)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = store.main(["working-set-drift", "--db", str(self.db)])
        self.assertEqual(rc, 1)
        lines = buf.getvalue().splitlines()
        self.assertEqual(lines[-1], "%d drift finding(s)" % (len(lines) - 1))
        self.assertGreater(len(lines), 1)


if __name__ == "__main__":
    unittest.main()
