import pathlib
import tempfile
import unittest

import scripts.store as store
from tests import helpers


class TestLogEvent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.migrate(self.db, helpers.FIXTURES / "ledger_fixture.tsv",
                      logs_dir=helpers.FIXTURES / "logdir")

    def tearDown(self):
        self.tmp.cleanup()

    def event_count(self):
        return store.db_connect(self.db).execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def thread(self, company, role):
        return store.db_connect(self.db).execute(
            "SELECT status, status_date FROM threads WHERE company=? AND role=?",
            (company, role),
        ).fetchone()

    def test_append_and_flip_atomic(self):
        eid = store.log_event(self.db, "3/12/2026", "Interview Invitation",
                              "Initech", "Data Engineer", "Email", "Interview Invited",
                              "screen set")
        self.assertEqual(self.thread("Initech", "Data Engineer"), ("advanced", "3/12/2026"))
        self.assertEqual(self.event_count(), 11)
        last = store.db_connect(self.db).execute(
            "SELECT last_event_id FROM threads WHERE company='Initech'").fetchone()[0]
        self.assertEqual(last, eid)

    def test_reapply_flips_not_duplicates(self):
        rows = store.db_connect(self.db).execute(
            "SELECT status, COUNT(*) FROM threads WHERE company='Globex' GROUP BY company"
        ).fetchone()
        self.assertEqual(rows, ("submitted", 1))

    def test_none_outcome_does_not_flip(self):
        store.log_event(self.db, "3/12/2026", "Networking/Outreach",
                        "Globex", "Data Engineer", "LinkedIn", "Outreach",
                        "recruiter ping")
        self.assertEqual(self.thread("Globex", "Data Engineer"), ("submitted", "3/10/2026"))
        n_threads = store.db_connect(self.db).execute(
            "SELECT COUNT(*) FROM threads").fetchone()[0]
        self.assertEqual(n_threads, 4)

    def test_refuses_phone_dashed(self):
        with self.assertRaises(ValueError):
            store.log_event(self.db, "3/12/2026", "Job Application", "Acme", "Role",
                            "Company Portal", "Application Submitted", "call 415-555-0100")
        self.assertEqual(self.event_count(), 10)

    def test_refuses_phone_bare(self):
        with self.assertRaises(ValueError):
            store.log_event(self.db, "3/12/2026", "Job Application", "Acme", "Role",
                            "Company Portal", "Application Submitted", "phone 4155550100")
        self.assertEqual(self.event_count(), 10)

    def test_refuses_local_path(self):
        for note in ("/Users/jane/notes.md", "/Volumes/DATA/notes", "~/Documents/x.md"):
            with self.assertRaises(ValueError):
                store.log_event(self.db, "3/12/2026", "Job Application", "Acme", "Role",
                                "Company Portal", "Application Submitted", note)
        self.assertEqual(self.event_count(), 10)

    def test_refuses_evidence_id(self):
        with self.assertRaises(ValueError):
            store.log_event(self.db, "3/12/2026", "Job Application", "Acme", "Role",
                            "Company Portal", "Application Submitted", "per EVID-9999")
        self.assertEqual(self.event_count(), 10)

    def test_refuses_unknown_outcome(self):
        with self.assertRaises(ValueError):
            store.log_event(self.db, "3/12/2026", "Job Application", "Acme", "Role",
                            "Company Portal", "Maybe", "note")
        self.assertEqual(self.event_count(), 10)

    def test_refuses_bad_date(self):
        with self.assertRaises(ValueError):
            store.log_event(self.db, "13/1/2026", "Job Application", "Acme", "Role",
                            "Company Portal", "Application Submitted", "note")
        self.assertEqual(self.event_count(), 10)

    def test_written_row_roundtrips(self):
        store.log_event(self.db, "3/12/2026", "Job Application", "Acme", "New Role",
                        "Email", "Application Submitted",
                        'sent; "fast track" per HR, req 42')
        raw = store.db_connect(self.db).execute(
            "SELECT raw_row FROM events ORDER BY id DESC LIMIT 1").fetchone()[0]
        fields = store.parse_tsv_line(raw)
        self.assertEqual(
            fields,
            ["3/12/2026", "Job Application", "Acme", "New Role", "Email",
             "Application Submitted", 'sent; "fast track" per HR, req 42'],
        )


if __name__ == "__main__":
    unittest.main()
