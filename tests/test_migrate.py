import pathlib
import tempfile
import unittest

import scripts.store as store
from tests import helpers


class TestMigrate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_migrate_counts(self):
        counts = store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv")
        self.assertEqual(counts["events"], 10)

    def test_fields_and_dates(self):
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv")
        conn = store.db_connect(self.db)
        row = conn.execute(
            "SELECT date, date_iso, type, company, role, channel, outcome, note "
            "FROM events WHERE id = 1"
        ).fetchone()
        self.assertEqual(
            row,
            ("3/1/2026", "2026-03-01", "Job Application", "Acme",
             "Data Pipeline Engineer", "Company Portal", "Application Submitted",
             "portal, req #1001"),
        )

    def test_quoting_variants_parse(self):
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv")
        conn = store.db_connect(self.db)
        notes = dict(conn.execute("SELECT id, note FROM events").fetchall())
        # r2: gratuitously quoted field, no trigger char
        self.assertEqual(notes[2], "Submitted via Greenhouse | https://acme.example/jobs/1002")
        # r3: empty note
        self.assertEqual(notes[3], "")
        # r4: unquoted field containing double-quotes
        self.assertEqual(notes[4], 'screen set; recruiter said "strong fit"')
        # r5: quoted field with internal doubled quotes
        self.assertEqual(notes[5], 'panel feedback: "would move forward," per notes')

    def test_raw_rows_preserved_verbatim(self):
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv")
        conn = store.db_connect(self.db)
        stored = [r[0] for r in conn.execute("SELECT raw_row FROM events ORDER BY id").fetchall()]
        lines = (helpers.FIXTURES / "ledger_fixture.tsv").read_text().split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        self.assertEqual(stored, lines[1:])

    def test_export_ledger_byte_identical(self):
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv")
        out = pathlib.Path(self.tmp.name) / "out.tsv"
        store.export_ledger(self.db, out)
        self.assertEqual(out.read_bytes(), (helpers.FIXTURES / "ledger_fixture.tsv").read_bytes())

    def test_refuses_nonempty_db(self):
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv")
        with self.assertRaises(ValueError):
            store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv")


if __name__ == "__main__":
    unittest.main()
