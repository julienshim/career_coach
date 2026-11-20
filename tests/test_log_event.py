import pathlib
import tempfile
import unittest

import scripts.store as store


class TestLogEvent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.db_connect(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def count(self, table):
        conn = store.db_connect(self.db)
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM " + table).fetchone()[0]
        finally:
            conn.close()

    def test_status_setting_event_creates_application_and_company(self):
        eid = store.log_event(self.db, "3/1/2026", "Job Application",
                              "Acme", "Data Pipeline Engineer", "Company Portal",
                              "Application Submitted", "portal, req #1001")
        conn = store.db_connect(self.db)
        try:
            self.assertEqual(
                conn.execute("SELECT name FROM company").fetchall(),
                [("Acme",)])
            app = conn.execute(
                "SELECT a.role, c.name, a.id FROM application a "
                "JOIN company c ON c.id = a.company_id").fetchone()
            self.assertEqual(app, ("Data Pipeline Engineer", "Acme", 1))
            ev = conn.execute(
                "SELECT id, company_key, role, application_id, outcome "
                "FROM event WHERE id = ?", (eid,)).fetchone()
            self.assertEqual(ev, (1, "Acme", "Data Pipeline Engineer", 1,
                                  "Application Submitted"))
        finally:
            conn.close()

    def test_company_with_contact_part_keys_on_company(self):
        # The Company/Contact value carries ' / ' + the contact name — the
        # key strips it, as the v1 company_key did.
        eid = store.log_event(self.db, "3/1/2026", "Job Application",
                              "Initech / Jane Recruiter", "Data Engineer",
                              "Company Portal", "Application Submitted",
                              "portal")
        conn = store.db_connect(self.db)
        try:
            self.assertEqual(
                conn.execute("SELECT name FROM company").fetchall(),
                [("Initech",)])
            self.assertEqual(conn.execute(
                "SELECT company_key FROM event WHERE id = ?", (eid,)
            ).fetchone()[0], "Initech")
        finally:
            conn.close()

    def test_na_event_no_application(self):
        eid = store.log_event(self.db, "3/1/2026", "Profile", "n/a", "n/a",
                              "n/a", "Profile Updated", "updated")
        conn = store.db_connect(self.db)
        try:
            self.assertIsNone(conn.execute(
                "SELECT application_id FROM event WHERE id = ?", (eid,)
            ).fetchone()[0])
        finally:
            conn.close()
        self.assertEqual(self.count("application"), 0)
        self.assertEqual(self.count("company"), 0)

    def test_flip_none_event_no_application(self):
        # A real pair, a non-status outcome: the event lands, but no
        # application is created (the v1 thread-creation rule, re-keyed).
        eid = store.log_event(self.db, "3/1/2026", "Networking/Outreach",
                              "Globex", "QA Engineer", "LinkedIn", "Outreach",
                              "recruiter ping")
        conn = store.db_connect(self.db)
        try:
            self.assertIsNone(conn.execute(
                "SELECT application_id FROM event WHERE id = ?", (eid,)
            ).fetchone()[0])
        finally:
            conn.close()
        self.assertEqual(self.count("application"), 0)
        self.assertEqual(self.count("company"), 0)

    def test_second_event_same_pair_reuses_application(self):
        store.log_event(self.db, "3/1/2026", "Job Application", "Acme", "Role",
                        "Company Portal", "Application Submitted", "in")
        store.log_event(self.db, "3/5/2026", "Interview", "Acme", "Role",
                        "Email", "Interview Invited", "screen")
        self.assertEqual(self.count("application"), 1)
        self.assertEqual(self.count("event"), 2)

    def test_pii_refusal_writes_nothing(self):
        # The refusal precedes the upserts: no event row and no
        # application/company side effects (Review Focus 5).
        with self.assertRaises(ValueError):
            store.log_event(self.db, "3/1/2026", "Job Application", "Acme",
                            "Role", "Company Portal", "Application Submitted",
                            "call 415-555-0100")
        self.assertEqual(self.count("event"), 0)
        self.assertEqual(self.count("application"), 0)
        self.assertEqual(self.count("company"), 0)

    def test_refuses_phone_bare(self):
        with self.assertRaises(ValueError):
            store.log_event(self.db, "3/1/2026", "Job Application", "Acme",
                            "Role", "Company Portal", "Application Submitted",
                            "phone 4155550100")
        self.assertEqual(self.count("event"), 0)

    def test_refuses_local_path(self):
        for note in ("/Users/jane/notes.md", "/Volumes/DATA/notes",
                     "~/Documents/x.md"):
            with self.assertRaises(ValueError):
                store.log_event(self.db, "3/1/2026", "Job Application", "Acme",
                                "Role", "Company Portal",
                                "Application Submitted", note)
        self.assertEqual(self.count("event"), 0)

    def test_refuses_evidence_id(self):
        with self.assertRaises(ValueError):
            store.log_event(self.db, "3/1/2026", "Job Application", "Acme",
                            "Role", "Company Portal", "Application Submitted",
                            "per EVID-9999")
        self.assertEqual(self.count("event"), 0)

    def test_refuses_unknown_outcome(self):
        with self.assertRaises(ValueError):
            store.log_event(self.db, "3/1/2026", "Job Application", "Acme",
                            "Role", "Company Portal", "Maybe", "note")
        self.assertEqual(self.count("event"), 0)
        self.assertEqual(self.count("application"), 0)

    def test_refuses_bad_date(self):
        with self.assertRaises(ValueError):
            store.log_event(self.db, "13/1/2026", "Job Application", "Acme",
                            "Role", "Company Portal", "Application Submitted",
                            "note")
        self.assertEqual(self.count("event"), 0)

    def test_written_row_roundtrips(self):
        store.log_event(self.db, "3/1/2026", "Job Application", "Acme",
                        "New Role", "Email", "Application Submitted",
                        'sent; "fast track" per HR, req 42')
        conn = store.db_connect(self.db)
        try:
            raw = conn.execute(
                "SELECT raw_row FROM event ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        finally:
            conn.close()
        fields = store.parse_tsv_line(raw)
        self.assertEqual(
            fields,
            ["3/1/2026", "Job Application", "Acme", "New Role", "Email",
             "Application Submitted", 'sent; "fast track" per HR, req 42'],
        )


if __name__ == "__main__":
    unittest.main()
