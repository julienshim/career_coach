"""Case drift on the company key must not hide or duplicate records.

Company keys are case-insensitive identifiers. The lookup matched on an
exact, case-sensitive name comparison, so a key typed in another case
matched nothing, the empty result read as "no application", and the write
path would create a duplicate company in the drifted case. The filter and
the lookups now match on lowercased names, the stored canonical spelling is
what comes back, and a no-match surfaces the near companies instead of a
silent empty result."""
import pathlib
import tempfile
import unittest

import scripts.store as store

COMPANY = "Globex"
ROLE = "Engineer"


class TestCompanyCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        self.conn = store.db_connect(self.db)
        self.conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def submit(self, company=COMPANY):
        store.log_event(self.db, "3/1/2026", "Job Application", company,
                        ROLE, "Company Portal", "Application Submitted",
                        "submitted via portal")

    def test_status_company_filter_matches_case_insensitively(self):
        self.submit()
        rows = store.status(self.db, company="globex")
        self.assertEqual(len(rows), 1)
        # The stored canonical spelling is what comes back.
        self.assertEqual(rows[0][0], COMPANY)

    def test_caps_company_filter_matches_case_insensitively(self):
        self.submit()
        self.assertEqual(store.caps(self.db, company="globex"),
                         [(COMPANY, 1)])

    def test_log_event_with_case_drift_links_existing_application(self):
        # A status-setting event with a case-drifted key: it must link the
        # existing application — not create a duplicate company + application.
        self.submit()
        store.log_event(self.db, "3/2/2026", "Interview", "globex",
                        ROLE, "Email", "Interview Invited", "intro call set")
        conn = store.db_connect(self.db)
        try:
            companies = conn.execute(
                "SELECT name FROM company "
                "WHERE LOWER(name) = 'globex'").fetchall()
            self.assertEqual(companies, [(COMPANY,)])
            app_ids = conn.execute(
                "SELECT id FROM application WHERE TRIM(role) = ? "
                "AND company_id = (SELECT id FROM company WHERE name = ?)",
                (ROLE, COMPANY)).fetchall()
            self.assertEqual(len(app_ids), 1)
            app_id = app_ids[0][0]
            [(linked,)] = conn.execute(
                "SELECT application_id FROM event "
                "WHERE type = 'Interview'").fetchall()
            self.assertEqual(linked, app_id)
        finally:
            conn.close()

    def test_near_companies_empty_on_case_variant(self):
        # A pure case variant is not "near" — the case-insensitive filter
        # resolves it, so a suggestion would never be reachable.
        self.submit()
        store.log_event(self.db, "3/3/2026", "Outreach", "Initech",
                        "Engineer", "Email", "Outreach", "intro")
        self.assertEqual(store.near_companies(self.db, "globex"), [])

    def test_near_companies_empty_when_name_is_far(self):
        self.submit()
        self.assertEqual(store.near_companies(self.db, "Zzzyzx"), [])

    def test_near_companies_suggests_fuzzy_typo(self):
        self.submit()
        self.assertIn(COMPANY, store.near_companies(self.db, "globax"))


if __name__ == "__main__":
    unittest.main()
