import pathlib
import re
import shutil
import tempfile
import unittest

import scripts.store as store
from tests import helpers

STATE = helpers.STATE


class TestDivergence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv",
                      logs_dir=helpers.FIXTURES / "logdir")
        self.qa = STATE / "qa_fixture.md"
        self.cast = STATE / "cast_fixture.md"
        self.hubs = STATE / "hubs"

    def tearDown(self):
        self.tmp.cleanup()

    def copy(self, src, name=None):
        dst = pathlib.Path(self.tmp.name) / (name or src.name)
        dst.write_text(src.read_text(), encoding="utf-8")
        return dst

    def test_clean(self):
        d = store.divergence(self.db, self.qa, self.cast, hubs_dir=self.hubs)
        self.assertEqual(d, [])

    def test_missing_qa_section_is_drift(self):
        qa = self.copy(self.qa)
        text = re.sub(r"## Initech.*?\n(?=## |\Z)", "", qa.read_text(), flags=re.S)
        qa.write_text(text)
        d = store.divergence(self.db, qa, self.cast, hubs_dir=self.hubs)
        self.assertEqual(len(d), 1)
        self.assertIn("Initech", d[0])

    def test_missing_qa_file_is_drift_not_crash(self):
        missing = pathlib.Path(self.tmp.name) / "nope.md"
        d = store.divergence(self.db, missing, self.cast, hubs_dir=self.hubs)
        self.assertEqual(len(d), 3)  # Acme, Globex, Initech
        self.assertTrue(all(x.startswith("qa:") for x in d))

    def test_stale_hub_is_drift(self):
        hubs = pathlib.Path(self.tmp.name) / "hubs"
        shutil.copytree(self.hubs, hubs)
        readme = hubs / "Acme" / "README.md"
        readme.write_text(readme.read_text().replace("(3/5/2026)", "(3/1/2026)"))
        d = store.divergence(self.db, self.qa, self.cast, hubs_dir=hubs)
        self.assertEqual(len(d), 1)
        self.assertIn("Acme", d[0])

    def test_hub_without_live_state_line_is_drift(self):
        hubs = pathlib.Path(self.tmp.name) / "hubs"
        shutil.copytree(self.hubs, hubs)
        readme = hubs / "Acme" / "README.md"
        readme.write_text(readme.read_text().split("**Live state")[0])
        d = store.divergence(self.db, self.qa, self.cast, hubs_dir=hubs)
        self.assertEqual(len(d), 1)
        self.assertTrue(d[0].startswith("hub:"))

    def test_unnamed_in_cast_is_drift(self):
        cast = self.copy(self.cast)
        lines = [ln for ln in cast.read_text().split("\n") if "Acme" not in ln]
        cast.write_text("\n".join(lines))
        d = store.divergence(self.db, self.qa, cast, hubs_dir=self.hubs)
        self.assertEqual(len(d), 1)
        self.assertIn("Acme", d[0])

    def test_drifted_names_match_bidirectionally(self):
        # the store keys carry suffixes the narrative names lack
        # ("Acme Inc." vs "Acme", "Initech Labs" vs "Initech"): naming drift
        # is not drift. Only the key sharing no name at all is reported.
        db = pathlib.Path(self.tmp.name) / "drift.db"
        store.migrate(db, helpers.FIXTURES / "ledger_drift_fixture.tsv")
        d = store.divergence(db, STATE / "qa_drift_fixture.md",
                             STATE / "cast_drift_fixture.md")
        self.assertEqual(d, ["qa: no '## ' section naming 'Globex Corp'"])

    def test_missing_cast_file_is_drift(self):
        missing = pathlib.Path(self.tmp.name) / "nope.md"
        d = store.divergence(self.db, self.qa, missing, hubs_dir=self.hubs)
        self.assertEqual(len(d), 1)  # Acme is the only advanced/rejected/closed company
        self.assertIn("Acme", d[0])


if __name__ == "__main__":
    unittest.main()
