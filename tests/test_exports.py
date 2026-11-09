import pathlib
import tempfile
import unittest

import scripts.store as store
from tests import helpers


class TestExportClaim(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv",
                      logs_dir=helpers.FIXTURES / "logdir")

    def tearDown(self):
        self.tmp.cleanup()

    def test_golden_and_inclusive_bounds(self):
        out = pathlib.Path(self.tmp.name) / "claim.txt"
        store.export_claim(self.db, "3/1/2026", "3/10/2026", out)
        golden = (helpers.FIXTURES / "golden_claim.txt").read_text()
        self.assertEqual(out.read_text(), golden)
        text = out.read_text()
        self.assertIn("3/1/2026", text)      # from-date included
        self.assertIn("3/10/2026", text)     # to-date included
        self.assertNotIn("3/11/2026", text)  # outside the range

    def test_range_filter(self):
        out = pathlib.Path(self.tmp.name) / "claim2.txt"
        store.export_claim(self.db, "3/5/2026", "3/6/2026", out)
        lines = out.read_text().strip().split("\n")
        self.assertEqual(len(lines), 3)  # 3/5 x2, 3/6 x1


if __name__ == "__main__":
    unittest.main()
