import pathlib
import tempfile
import unittest

import scripts.store as store
from tests import helpers


class TestRunLogs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv",
                      logs_dir=helpers.FIXTURES / "logdir")

    def tearDown(self):
        self.tmp.cleanup()

    def test_migrate_logs_counts_and_pickup(self):
        n = store.db_connect(self.db).execute("SELECT COUNT(*) FROM run_logs").fetchone()[0]
        self.assertEqual(n, 4)
        self.assertEqual(store.pickup(self.db, "architect"),
                         ("3/2/2026", "Second task", "Did more.", "Chose approach B.",
                          "Next: wrap up."))
        # 4-field fixture row: next padded with ''
        self.assertEqual(store.pickup(self.db, "sourcing"),
                         ("3/2/2026", "Follow-up run", "Chased one reply.",
                          "Hold on the other one.", ""))
        self.assertIsNone(store.pickup(self.db, "interview"))

    def test_log_run_then_pickup(self):
        store.log_run(self.db, "architect", "3/3/2026", "Third task", "Did the rest.",
                      "Chose approach C.", "Next: done.")
        self.assertEqual(store.pickup(self.db, "architect"),
                         ("3/3/2026", "Third task", "Did the rest.", "Chose approach C.",
                          "Next: done."))
        # the other hat is untouched
        self.assertEqual(store.pickup(self.db, "sourcing")[0], "3/2/2026")

    def test_log_run_refuses_pii(self):
        with self.assertRaises(ValueError):
            store.log_run(self.db, "architect", "3/3/2026", "Task",
                          "Called 415-555-0100", "Decision", "Next")
        n = store.db_connect(self.db).execute(
            "SELECT COUNT(*) FROM run_logs WHERE hat='architect' AND date='3/3/2026'"
        ).fetchone()[0]
        self.assertEqual(n, 0)

    def test_export_logs_byte_identical(self):
        out_dir = pathlib.Path(self.tmp.name) / "logs"
        store.export_logs(self.db, out_dir)
        for hat in ("architect", "sourcing"):
            self.assertEqual(
                (out_dir / (hat + ".tsv")).read_bytes(),
                (helpers.FIXTURES / "logdir" / (hat + ".tsv")).read_bytes(),
                hat,
            )


if __name__ == "__main__":
    unittest.main()
