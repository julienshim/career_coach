"""Neutral events link to their application, and the orphaned rows are
repaired. The class: an event whose outcome sets no status was written
without an application link and was unreachable through the
application-scoped reads."""
import pathlib
import tempfile
import unittest

import scripts.store as store
from tests import helpers

COMPANY = "Orphaneer"
ROLE = "Senior Data Engineer"


class TestNeutralEventLinking(unittest.TestCase):
    """A neutral outcome (Other / Outreach) for an existing
    (company, role) -> the row carries the application id; the view's
    status/date is unchanged; the walk from the application reaches the
    event."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.log_event(
            self.db, "3/1/2026", "Job Application", "Acme",
            "Data Pipeline Engineer", "Company Portal",
            "Application Submitted", "portal")

    def tearDown(self):
        self.tmp.cleanup()

    def app_id(self):
        conn = store.db_connect(self.db)
        try:
            return conn.execute(
                "SELECT a.id FROM application a "
                "JOIN company c ON a.company_id = c.id "
                "WHERE c.name = 'Acme'").fetchone()[0]
        finally:
            conn.close()

    def test_neutral_outcomes_link_and_view_unchanged(self):
        eid1 = store.log_event(
            self.db, "3/3/2026", "Interview", "Acme",
            "Data Pipeline Engineer", "Coderbyte", "Other",
            "assessment, part 1 of 2 done")
        eid2 = store.log_event(
            self.db, "3/4/2026", "Outreach", "Acme",
            "Data Pipeline Engineer", "Email", "Outreach",
            "follow-up to the recruiter")
        conn = store.db_connect(self.db)
        try:
            got = conn.execute(
                "SELECT application_id FROM event WHERE id IN (?, ?)",
                (eid1, eid2)).fetchall()
        finally:
            conn.close()
        self.assertEqual(got, [(self.app_id(),), (self.app_id(),)])
        # The neutral events do not flip the status: still submitted 3/1.
        rows = store.status(self.db, company="Acme")
        got = {(c, r): (s, sd) for c, r, s, sd, _q, _l, *_act in rows}
        self.assertEqual(got[("Acme", "Data Pipeline Engineer")],
                         ("submitted", "3/1/2026"))
        # The walk from the application reaches both events (the
        # logged_on edge is in the graph model).
        edges = store.neighbors(self.db, "application", self.app_id())
        rels = [(rel, otype, oid)
                for (_d, rel, _dir, otype, oid, *rest) in edges]
        self.assertIn(("logged_on", "event", eid1), rels)
        self.assertIn(("logged_on", "event", eid2), rels)
        # A depth-2 walk lands on the event rows (outside ENTITIES) — it
        # must stop there cleanly, not crash on the missing table map.
        deep = store.neighbors(self.db, "application", self.app_id(),
                               depth=2)
        self.assertIsInstance(deep, list)


class TestRepairOp(unittest.TestCase):
    """The one-shot repair backfills the orphaned links; the ledger
    export is byte-identical before and after (the link column is not in
    the ledger's raw rows)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv")

    def tearDown(self):
        self.tmp.cleanup()

    def ledger_bytes(self):
        out = pathlib.Path(self.tmp.name) / "ledger.tsv"
        store.export_ledger(self.db, out)
        return out.read_bytes()

    def test_repair_links_orphan_and_keeps_ledger_byte_stable(self):
        # The orphan-creation flow: a neutral row for a new pair (no
        # application yet — nothing to link to), then a status row that
        # creates the application. The neutral row stays orphaned until
        # repair.
        eid = store.log_event(
            self.db, "3/10/2026", "Outreach", "Orphaneer",
            "Data Engineer", "Email", "Outreach", "intro")
        store.log_event(
            self.db, "3/11/2026", "Job Application", "Orphaneer",
            "Data Engineer", "Company Portal",
            "Application Submitted", "portal")
        conn = store.db_connect(self.db)
        try:
            app_id = conn.execute(
                "SELECT a.id FROM application a "
                "JOIN company c ON a.company_id = c.id "
                "WHERE c.name = 'Orphaneer' AND a.role = 'Data Engineer'"
            ).fetchone()[0]
            pre = conn.execute(
                "SELECT application_id FROM event WHERE id = ?",
                (eid,)).fetchone()[0]
        finally:
            conn.close()
        self.assertIsNone(pre)
        before = self.ledger_bytes()
        self.assertEqual(store.repair(self.db), {"linked": 1})
        conn = store.db_connect(self.db)
        try:
            post = conn.execute(
                "SELECT application_id FROM event WHERE id = ?",
                (eid,)).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(post, app_id)
        self.assertEqual(self.ledger_bytes(), before)
        # Idempotent: a second run links nothing.
        self.assertEqual(store.repair(self.db), {"linked": 0})


class TestColdSessionAcceptance(unittest.TestCase):
    """Mechanism-level: a fresh store, a scripted cold session told only
    "check Orphaneer" — sanctioned ops alone
    (status/query/working_set/pickup), in <= 3 ops, surfaces the
    assessment completion. The fixture is the failure class's shape: the
    application, a neutral assessment event (outcome 'Other'), and the
    satisfied-withdrawn directive (whose stale-active form steered a
    session toward a duplicate write)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        ledger = pathlib.Path(self.tmp.name) / "ledger.tsv"
        ledger.write_text(
            "Date\tActivity Type\tCompany/Contact\tRole\tMethod\t"
            "Stage/Outcome\tNote/Links\n"
            "3/1/2026\tInterview\t" + COMPANY + "\t" + ROLE +
            "\tEmail\tInterview Invited\tonsite round offered\n"
            "3/5/2026\tInterview\t" + COMPANY + "\t" + ROLE +
            "\tCoderPad\tOther\tassessment part 1 of 2 done, "
            "part 2 scheduled\n",
            encoding="utf-8")
        store.migrate(self.db, ledger)
        conn = store.db_connect(self.db)
        try:
            self.app_id = conn.execute(
                "SELECT a.id FROM application a "
                "JOIN company c ON a.company_id = c.id "
                "WHERE c.name = ?", (COMPANY,)).fetchone()[0]
        finally:
            conn.close()
        # The satisfied-withdrawn directive: "log the completion when
        # reported" — the completion was logged, the directive was
        # withdrawn; the working set must not carry it.
        iid = store.instruction(
            self.db, "log the completion when reported", "constraint",
            "application", "application", self.app_id)
        store.withdraw_instruction(self.db, iid)

    def tearDown(self):
        self.tmp.cleanup()

    def test_cold_session_surfaces_assessment_in_three_ops(self):
        ops = 0
        # Op 1: the status read — the natural first question. It shows
        # advanced 3/1: the view tracks status-setting events only, so
        # it cannot answer "what happened most recently".
        rows = store.status(self.db, company=COMPANY)
        ops += 1
        got = {(c, r): (s, sd) for c, r, s, sd, _q, _l, *_act in rows}
        self.assertEqual(got[(COMPANY, ROLE)], ("advanced", "3/1/2026"))
        # Op 2: the application row — the record the events hang on.
        env = store.query(
            self.db,
            {"entity": "application",
             "filters": [{"field": "role", "op": "=", "value": ROLE}],
             "limit": 5})
        ops += 1
        self.assertEqual([r["id"] for r in env["results"]], [self.app_id])
        # Op 3: the application's full event record, newest first — the
        # application-scoped read the linking made possible (pre-fix the
        # row was NULL-linked and invisible to this plan).
        env = store.query(
            self.db,
            {"entity": "event",
             "filters": [{"field": "application_id", "op": "=",
                          "value": self.app_id}],
             "order_by": {"field": "date_iso", "direction": "desc"},
             "limit": 5})
        ops += 1
        self.assertLessEqual(ops, 3)
        top = env["results"][0]
        self.assertEqual(top["date"], "3/5/2026")
        self.assertIn("assessment", top["note"])
        # The working set carries no stale directive — the
        # satisfied-withdrawn instruction must not misdirect the
        # session into re-logging the completion.
        self.assertEqual(
            store.working_set(self.db, "sourcing", self.app_id), [])


if __name__ == "__main__":
    unittest.main()
