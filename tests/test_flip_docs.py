"""The flip prose names the complete neutral set and the assessment
convention — the vocabulary is documented, not code-archaeology. The
convention: an assessment is an interview step — type Interview,
channel the platform name, outcome Completed when the step is done (a
timed assessment that ended early is still Completed; the precision
goes in the note); abandoned-without-submitting is Withdrawn /
Declined; Other is reserved. The convention chose the outcome
vocabulary over a new label, so the doc line is pinned here by grep."""
import pathlib
import tempfile
import unittest

import scripts.store as store
from tests import helpers

STANDARDS = helpers.ROOT / "standards" / "STANDARDS.md"


def flip_section():
    lines = STANDARDS.read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines)
                 if l.startswith("Application status is derived"))
    end = next(i for i in range(start + 1, len(lines))
               if lines[i].startswith("## "))
    return "\n".join(lines[start:end])


class TestFlipProseNamesTheVocabulary(unittest.TestCase):
    def test_neutral_set_is_named_completely(self):
        section = flip_section()
        for outcome in ("Outreach", "Profile Updated",
                        "Internal In Progress", "Internal Complete",
                        "Other"):
            self.assertIn(outcome, section,
                          "neutral outcome %r not named in the flip prose"
                          % outcome)

    def test_assessment_convention_is_named(self):
        section = flip_section()
        for token in ("Assessments", "interview", "Completed",
                      "Withdrawn", "Declined", "platform"):
            self.assertIn(token, section,
                          "assessment-convention token %r missing from "
                          "the flip prose" % token)


class TestAssessmentConventionBehavior(unittest.TestCase):
    """The convention's behavior half: an assessment completion logged
    per the doc line flips the application to advanced and is
    retrievable from the application's record (the application link)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_completed_assessment_flips_and_retrieves(self):
        store.log_event(self.db, "3/10/2026", "Job Application",
                        "Acme", "Data Analytics Engineer",
                        "Company Portal", "Application Submitted",
                        "portal")
        store.log_event(self.db, "3/20/2026", "Interview", "Acme",
                        "Data Analytics Engineer", "Coderbyte",
                        "Completed",
                        "SQL assessment part 1 of 2 done, timed, ended "
                        "early; part 2 scheduled")
        rows = store.status(self.db, company="Acme")
        got = {(c, r): (s, sd) for c, r, s, sd, _q, _l, *_act in rows}
        self.assertEqual(
            got[("Acme", "Data Analytics Engineer")],
            ("advanced", "3/20/2026"))
        conn = store.db_connect(self.db)
        try:
            app_id = conn.execute(
                "SELECT a.id FROM application a "
                "JOIN company c ON a.company_id = c.id "
                "WHERE c.name = 'Acme'").fetchone()[0]
        finally:
            conn.close()
        env = store.query(
            self.db,
            {"entity": "event",
             "filters": [{"field": "application_id", "op": "=",
                          "value": app_id}],
             "order_by": {"field": "date_iso", "direction": "desc"}})
        self.assertEqual(env["results"][0]["outcome"], "Completed")
        self.assertEqual(env["results"][0]["channel"], "Coderbyte")


if __name__ == "__main__":
    unittest.main()
