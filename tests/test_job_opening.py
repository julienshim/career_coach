"""The
job posting's link is the duplicate key. The same title at the same
company can carry several postings, one per link; the legacy no-url form
is kept (a row without a link is a row without a link, and an
unambiguous title still resolves) and refuses a title that now carries
several postings instead of picking one. log-event --url upserts the
posting and attaches it to the application in the same op, so a logged
submission carries its posting durably (the link today lives only in
the free-text note)."""
import pathlib
import tempfile
import unittest

import scripts.store as store


class TestJobOpeningKeying(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.db_connect(self.db)
        store.upsert_company(self.db, "Acme")

    def tearDown(self):
        self.tmp.cleanup()

    def count(self, where="1=1"):
        conn = store.db_connect(self.db)
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM job_opening WHERE " + where).fetchone()[0]
        finally:
            conn.close()

    def test_same_title_different_urls_are_distinct_postings(self):
        a = store.upsert_job_opening(
            self.db, "Acme", "Data Engineer",
            url="https://acme.example/jobs/1001")
        b = store.upsert_job_opening(
            self.db, "Acme", "Data Engineer",
            url="https://acme.example/jobs/2002")
        self.assertNotEqual(a, b)
        self.assertEqual(self.count(), 2)
        # Re-run: the link is the key — a match, not a third row.
        self.assertEqual(store.upsert_job_opening(
            self.db, "Acme", "Data Engineer",
            url="https://acme.example/jobs/1001"), a)
        self.assertEqual(self.count(), 2)

    def test_legacy_no_url_form(self):
        # Fresh: creates the row without a link.
        a = store.upsert_job_opening(self.db, "Acme", "Data Engineer")
        self.assertEqual(self.count(), 1)
        # A posting with a link under the same title is a distinct row.
        store.upsert_job_opening(
            self.db, "Acme", "Data Engineer",
            url="https://acme.example/jobs/3003")
        # Now the title carries two postings: the legacy form refuses
        # and names both links — never a silent pick.
        with self.assertRaises(ValueError) as ctx:
            store.upsert_job_opening(self.db, "Acme", "Data Engineer")
        msg = str(ctx.exception)
        self.assertIn("3003", msg)
        self.assertIn("(no link)", msg)
        # A title with exactly one posting (the linked one): the legacy
        # form resolves to it — the unambiguous case is kept.
        store.upsert_company(self.db, "Globex")
        c = store.upsert_job_opening(
            self.db, "Globex", "Data Engineer",
            url="https://globex.example/jobs/9")
        self.assertEqual(
            store.upsert_job_opening(self.db, "Globex", "Data Engineer"),
            c)
        self.assertEqual(self.count("company_id = (SELECT id FROM company "
                                    "WHERE name = 'Globex')"), 1)


class TestLogEventWithUrl(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.db_connect(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self, table):
        conn = store.db_connect(self.db)
        try:
            return conn.execute("SELECT * FROM " + table).fetchall()
        finally:
            conn.close()

    def test_submission_with_url_upserts_and_attaches(self):
        store.log_event(
            self.db, "3/1/2026", "Job Application", "Acme",
            "Data Engineer", "Company Portal", "Application Submitted",
            "portal", url="https://acme.example/jobs/1001")
        conn = store.db_connect(self.db)
        try:
            jo = conn.execute(
                "SELECT id, url FROM job_opening").fetchall()
            linked = conn.execute(
                "SELECT a.id, a.job_opening_id, e.id "
                "FROM application a "
                "JOIN event e ON e.application_id = a.id "
                "WHERE e.outcome = 'Application Submitted'").fetchall()
        finally:
            conn.close()
        self.assertEqual(len(jo), 1)
        self.assertEqual(jo[0][1], "https://acme.example/jobs/1001")
        self.assertEqual(linked[0][1], jo[0][0])  # attached

    def test_same_url_later_event_no_duplicate_posting(self):
        store.log_event(
            self.db, "3/1/2026", "Job Application", "Acme",
            "Data Engineer", "Company Portal", "Application Submitted",
            "portal", url="https://acme.example/jobs/1001")
        store.log_event(
            self.db, "3/5/2026", "Interview", "Acme", "Data Engineer",
            "Email", "Interview Invited", "round 1",
            url="https://acme.example/jobs/1001")
        conn = store.db_connect(self.db)
        try:
            n = conn.execute("SELECT COUNT(*) FROM job_opening").fetchone()[0]
            linked = conn.execute(
                "SELECT COUNT(DISTINCT job_opening_id) FROM application "
                "WHERE job_opening_id IS NOT NULL").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(n, 1)
        self.assertEqual(linked, 1)

    def test_event_without_url_creates_no_posting(self):
        store.log_event(
            self.db, "3/1/2026", "Job Application", "Acme",
            "Data Engineer", "Company Portal", "Application Submitted",
            "portal")
        self.assertEqual(self.rows("job_opening"), [])


if __name__ == "__main__":
    unittest.main()
