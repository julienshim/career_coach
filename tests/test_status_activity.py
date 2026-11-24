"""Last activity in the status op: the status shows where the
application stands as far as status goes; the last activity shows what
happened most recently — neutral events included. One op answers both:
an advanced status with a newer neutral event reads in a single line
instead of a second retrieval, and the status semantics stay exactly as
they were (the last status-setting event, never a neutral one)."""
import pathlib
import tempfile
import unittest

import scripts.store as store

COMPANY = "Acme"
ROLE = "Data Analytics Engineer"


class TestStatusLastActivity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        store.db_connect(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def row(self):
        rows = store.status(self.db, company=COMPANY)
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_last_activity_is_most_recent_event_any_kind(self):
        # The shape: outreach, a status-setting invite, then a neutral
        # assessment completion.
        store.log_event(self.db, "3/10/2026", "Outreach", COMPANY, ROLE,
                        "Email", "Outreach", "intro")
        store.log_event(self.db, "3/16/2026", "Interview", COMPANY, ROLE,
                        "Email", "Interview Invited", "onsite offered")
        store.log_event(self.db, "3/20/2026", "Interview", COMPANY, ROLE,
                        "Coderbyte", "Other",
                        "assessment part 1 of 2 done, timed, ended early")
        comp, role, st, sd, req, le, ad, at, ao = self.row()
        # Status semantics unchanged: the last status-setting event.
        self.assertEqual((st, sd), ("advanced", "3/16/2026"))
        # Last activity: the newest event of any kind — the neutral one.
        self.assertEqual((ad, at, ao), ("3/20/2026", "Interview", "Other"))

    def test_last_activity_falls_back_to_status_event(self):
        # No neutral events: the activity is the status event itself.
        store.log_event(self.db, "3/10/2026", "Outreach", COMPANY, ROLE,
                        "Email", "Outreach", "intro")
        store.log_event(self.db, "3/16/2026", "Interview", COMPANY, ROLE,
                        "Email", "Interview Invited", "onsite offered")
        comp, role, st, sd, req, le, ad, at, ao = self.row()
        self.assertEqual((st, sd), ("advanced", "3/16/2026"))
        self.assertEqual((ad, at, ao), ("3/16/2026", "Interview",
                                        "Interview Invited"))

    def test_neutral_between_statuses_is_not_the_activity(self):
        # A neutral event between two status events: the activity is the
        # later status event, not the neutral one in between.
        store.log_event(self.db, "3/10/2026", "Interview", COMPANY, ROLE,
                        "Email", "Interview Invited", "round 1 offered")
        store.log_event(self.db, "3/12/2026", "Interview", COMPANY, ROLE,
                        "Coderbyte", "Other", "written test assigned")
        store.log_event(self.db, "3/16/2026", "Interview", COMPANY, ROLE,
                        "Email", "Interview Invited", "round 2 offered")
        _c, _r, st, sd, _q, le, ad, at, ao = self.row()
        self.assertEqual((st, sd), ("advanced", "3/16/2026"))
        self.assertEqual((ad, at, ao), ("3/16/2026", "Interview",
                                        "Interview Invited"))


if __name__ == "__main__":
    unittest.main()
