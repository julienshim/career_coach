import pathlib
import sqlite3
import tempfile
import unittest

import scripts.store as store
from tests import helpers


class TestApplicationStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv")

    def tearDown(self):
        self.tmp.cleanup()

    def test_migrate_status_output_matches_v1(self):
        # The derived status (the view over the new tables): the same
        # values the v1 threads carried for the same fixture.
        rows = store.status(self.db)
        got = {(c, r): (s, sd) for c, r, s, sd, req, le, *_act in rows}
        self.assertEqual(got[("Acme", "Data Pipeline Engineer")], ("rejected", "3/5/2026"))
        self.assertEqual(got[("Acme", "Search Infra Engineer")], ("advanced", "3/4/2026"))
        self.assertEqual(got[("Initech", "Data Engineer")], ("submitted", "3/2/2026"))
        # Globex: rejected 3/6, re-applied 3/10 (fixture) — flipped back,
        # one application
        self.assertEqual(got[("Globex", "Data Engineer")], ("submitted", "3/10/2026"))
        self.assertEqual(len(got), 4)

    def test_same_date_last_event_wins(self):
        # 3/5/2026: Interview Invited (event 6) then Not Selected (event 7)
        # — the rejection is last
        row = [r for r in store.status(self.db)
               if r[0] == "Acme" and r[1] == "Data Pipeline Engineer"][0]
        self.assertEqual(row[2], "rejected")
        self.assertEqual(row[3], "3/5/2026")
        self.assertEqual(row[5], 7)

    def test_req_derived_from_status_setting_notes(self):
        by_pair = {(c, r): req for c, r, s, sd, req, le, *_act in
                   store.status(self.db)}
        self.assertEqual(by_pair[("Acme", "Data Pipeline Engineer")], "1001")
        self.assertIsNone(by_pair[("Acme", "Search Infra Engineer")])

    def test_status_company_filter_and_live(self):
        rows = store.status(self.db, company="Acme")
        self.assertEqual([(r[0], r[1]) for r in rows],
                         [("Acme", "Data Pipeline Engineer"), ("Acme", "Search Infra Engineer")])
        live = store.status(self.db, live=True)
        self.assertEqual({(c, r) for c, r, *rest in live},
                         {("Acme", "Search Infra Engineer"), ("Initech", "Data Engineer"),
                          ("Globex", "Data Engineer")})

    def test_directly_created_application_no_status(self):
        # An application with no status-setting event: the view row exists
        # with a NULL status, and --live keeps it (only rejected/closed are
        # excluded).
        conn = store.db_connect(self.db)
        try:
            conn.execute(
                "INSERT INTO application (company_id, role, created_at) "
                "SELECT id, 'New Role', '2026-01-01' FROM company "
                "WHERE name = 'Globex'")
            conn.commit()
        finally:
            conn.close()
        rows = store.status(self.db)
        row = [r for r in rows
               if r[0] == "Globex" and r[1] == "New Role"][0]
        self.assertIsNone(row[2])
        self.assertIsNone(row[5])
        live = store.status(self.db, live=True)
        self.assertIn(("Globex", "New Role"), {(c, r) for c, r, *rest in live})

    def test_fresh_db_has_no_legacy_tables(self):
        # Review Focus 4: a fresh onboarding db never carries the legacy
        # model.
        conn = sqlite3.connect(str(self.db))
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            conn.close()
        self.assertNotIn("events", tables)
        self.assertNotIn("threads", tables)
        self.assertIn("event", tables)
        self.assertIn("application", tables)

    def test_caps(self):
        self.assertEqual(store.caps(self.db), [("Acme", 2), ("Globex", 1), ("Initech", 1)])
        self.assertEqual(store.caps(self.db, company="Acme"), [("Acme", 2)])
        self.assertEqual(store.caps(self.db, company="Globex"), [("Globex", 1)])

    def test_company_key_helper(self):
        self.assertEqual(store.company_key("Acme AI / Michael X, Director"), "Acme AI")
        self.assertEqual(store.company_key("Acme"), "Acme")
        self.assertEqual(store.company_key("n/a"), "n/a")

    def test_unknown_outcome_fails_closed(self):
        lines = (helpers.FIXTURES / "ledger_fixture.tsv").read_text().split("\n")
        fields = lines[1].split("\t")
        fields[5] = "Maybe"
        bad = pathlib.Path(self.tmp.name) / "bad.tsv"
        bad.write_text("\n".join([lines[0]] + ["\t".join(fields)] + lines[2:]) + "\n",
                       encoding="utf-8")
        fresh = pathlib.Path(self.tmp.name) / "fresh.db"
        with self.assertRaises(ValueError):
            store.migrate(fresh, bad)
        n = store.db_connect(fresh).execute("SELECT COUNT(*) FROM event").fetchone()[0]
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
