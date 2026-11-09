import pathlib
import tempfile
import unittest

import scripts.store as store
from tests import helpers


class TestThreads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv")

    def tearDown(self):
        self.tmp.cleanup()

    def test_flip_table_applied(self):
        rows = store.status(self.db)
        got = {(c, r): (s, sd) for c, r, s, sd, req, le in rows}
        self.assertEqual(got[("Acme", "Data Pipeline Engineer")], ("rejected", "3/5/2026"))
        self.assertEqual(got[("Acme", "Search Infra Engineer")], ("advanced", "3/4/2026"))
        self.assertEqual(got[("Initech", "Data Engineer")], ("submitted", "3/2/2026"))
        # Globex: rejected 3/6, re-applied 3/10 (fixture) — flipped back, one thread
        self.assertEqual(got[("Globex", "Data Engineer")], ("submitted", "3/10/2026"))
        self.assertEqual(len(got), 4)

    def test_same_date_last_event_wins(self):
        # 3/5/2026: Interview Invited (event 6) then Not Selected (event 7) — rejection last
        row = store.db_connect(self.db).execute(
            "SELECT status, status_date, last_event_id FROM threads "
            "WHERE company='Acme' AND role='Data Pipeline Engineer'"
        ).fetchone()
        self.assertEqual(row[0], "rejected")
        self.assertEqual(row[1], "3/5/2026")
        self.assertEqual(row[2], 7)

    def test_req_parsed_from_note(self):
        conn = store.db_connect(self.db)
        req = conn.execute(
            "SELECT req FROM threads WHERE company='Acme' AND role='Data Pipeline Engineer'"
        ).fetchone()[0]
        self.assertEqual(req, "1001")
        req2 = conn.execute(
            "SELECT req FROM threads WHERE company='Acme' AND role='Search Infra Engineer'"
        ).fetchone()[0]
        self.assertIsNone(req2)

    def test_status_company_filter_and_live(self):
        rows = store.status(self.db, company="Acme")
        self.assertEqual([(r[0], r[1]) for r in rows],
                         [("Acme", "Data Pipeline Engineer"), ("Acme", "Search Infra Engineer")])
        live = store.status(self.db, live=True)
        self.assertEqual({(c, r) for c, r, *rest in live},
                         {("Acme", "Search Infra Engineer"), ("Initech", "Data Engineer"),
                          ("Globex", "Data Engineer")})

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
        n = store.db_connect(fresh).execute("SELECT COUNT(*) FROM events").fetchone()[0]
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
