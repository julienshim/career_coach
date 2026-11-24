"""The store under concurrent opens. The crash
mode: two or more ops open at once interleave the derived drop/create, or
race the single WAL writer with zero busy timeout. Every op must survive
N concurrent opens and N concurrent writes (the mechanism's own rule is
that independent tool calls go in one parallel batch)."""
import concurrent.futures
import pathlib
import tempfile
import unittest

import scripts.store as store
from tests import helpers


class TestDerivedRebuildFreshness(unittest.TestCase):
    """The FTS rebuild fires exactly when the fill's input changes —
    in-place edits, not just appends. The stale-index window the rebuild
    is supposed to close is between the edit and the next query."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv")

    def tearDown(self):
        self.tmp.cleanup()

    def test_in_place_edit_visible_to_next_query(self):
        conn = store.db_connect(self.db)
        try:
            cid = conn.execute(
                "SELECT id FROM company WHERE name = 'Acme'").fetchone()[0]
            conn.execute("UPDATE company SET industry = 'widget "
                         "fabrication' WHERE id = ?", (cid,))
            conn.commit()
        finally:
            conn.close()
        env = store.query(self.db, {"search": "fabrication",
                                    "entities": ["company"], "limit": 5})
        got = [r["id"] for r in env["results"]]
        self.assertEqual(len(got), 1)

    def test_hash_stable_on_noop_open_advances_on_edit(self):
        # The guard: the stored hash is stable across no-op opens (so the
        # rebuild is skipped, removing the drop/create interleave) and
        # advances exactly when the fill input changes.
        def stored():
            conn = store.db_connect(self.db)
            try:
                return conn.execute(
                    "SELECT value FROM meta "
                    "WHERE key = 'search_index_hash'").fetchone()[0]
            finally:
                conn.close()

        h1 = stored()
        self.assertIsNotNone(h1)
        self.assertEqual(stored(), h1)  # no-op open: guard holds
        conn = store.db_connect(self.db)
        try:
            conn.execute(
                "UPDATE company SET industry = 'widget fabrication' "
                "WHERE name = 'Acme'")
            conn.commit()
        finally:
            conn.close()
        self.assertNotEqual(stored(), h1)  # edit: hash advanced


class TestConcurrentOpens(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv")

    def tearDown(self):
        self.tmp.cleanup()

    def test_concurrent_read_ops(self):
        # pickup + status + working-set in 3 threads x 50 iterations —
        # all succeed (currently fails intermittently: the drop/create
        # interleave).
        def one(i):
            if i % 3 == 0:
                store.pickup(self.db, "sourcing")
            elif i % 3 == 1:
                store.status(self.db)
            else:
                store.working_set(self.db, "sourcing")
        errors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futs = [ex.submit(one, i) for i in range(150)]
            for f in concurrent.futures.as_completed(futs):
                e = f.exception()
                if e:
                    errors.append(e)
        self.assertEqual(errors, [])

    def test_concurrent_log_event_writes(self):
        # three parallel log-event calls (distinct companies) — all
        # three land, no lost write.
        def one(company):
            store.log_event(self.db, "3/10/2026", "Job Application",
                            company, "Role", "Company Portal",
                            "Application Submitted", "portal")
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futs = [ex.submit(one, c) for c in ("Alpha", "Beta", "Gamma")]
            for f in concurrent.futures.as_completed(futs):
                self.assertIsNone(f.exception())
        conn = store.db_connect(self.db)
        try:
            got = {r[0] for r in conn.execute("SELECT name FROM company")}
            n = conn.execute(
                "SELECT COUNT(*) FROM event WHERE outcome = 'Application "
                "Submitted' AND company_key IN ('Alpha', 'Beta', 'Gamma')"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertLessEqual({"Alpha", "Beta", "Gamma"}, got)
        self.assertEqual(n, 3)


if __name__ == "__main__":
    unittest.main()
