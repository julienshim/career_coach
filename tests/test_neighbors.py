import datetime
import pathlib
import tempfile
import unittest

import scripts.store as store


class TestNeighbors(unittest.TestCase):
    """The connected-record walk: junctions (both sides) + FKS edges."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        # The pinned mini-graph: person -> role (FK held) -> achievement
        # (FK context_for) with 2 skills, 1 evidence, 1 document; the
        # document supersedes an earlier document row.
        self.p = store.upsert_person(self.db, full_name="P")
        self.c = store.upsert_company(self.db, name="C")
        self.r = store.upsert_role(self.db, company="C", title="R")
        self.a = store.upsert_achievement(self.db, title="A", role_id=self.r)
        self.s1 = store.upsert_skill(self.db, name="S1")
        self.s2 = store.upsert_skill(self.db, name="S2")
        self.e = store.upsert_evidence(self.db, evid_id="EV-1", claim="c")
        self.d0 = store.upsert_document(self.db, doc_type="resume",
                                        title="D0", path="d.md", version=1)
        self.d1 = store.upsert_document(self.db, doc_type="resume",
                                        title="D1", path="d.md", version=2,
                                        supersedes_id=self.d0)
        store.link(self.db, "achievement_skill",
                   "achievement:%d" % self.a, "skill:%d" % self.s1)
        store.link(self.db, "achievement_skill",
                   "achievement:%d" % self.a, "skill:%d" % self.s2)
        store.link(self.db, "achievement_evidence",
                   "achievement:%d" % self.a, "evidence:%d" % self.e)
        store.link(self.db, "resume_achievement",
                   "document:%d" % self.d1, "achievement:%d" % self.a)

    def tearDown(self):
        self.tmp.cleanup()

    def test_depth1_exact_rows(self):
        today = datetime.date.today().isoformat()
        rows = store.neighbors(self.db, "achievement", self.a, depth=1)
        self.assertEqual(rows, [
            (1, "achievement_skill", "to", "skill", self.s1,
             "", "user", "user_fact", today),
            (1, "achievement_skill", "to", "skill", self.s2,
             "", "user", "user_fact", today),
            (1, "achievement_evidence", "to", "evidence", self.e,
             "", "user", "user_fact", today),
            (1, "resume_achievement", "from", "document", self.d1,
             "", "user", "user_fact", today),
            (1, "context_for", "out", "role", self.r, "", "", "", ""),
        ])

    def test_depth2_reaches_person(self):
        rows = store.neighbors(self.db, "achievement", self.a, depth=2)
        # depth-1 prefix intact; depth-2: the superseded document (via the
        # document), then person and company (via the role)
        self.assertEqual(rows[5:], [
            (2, "supersedes", "out", "document", self.d0, "", "", "", ""),
            (2, "held", "out", "person", self.p, "", "", "", ""),
            (2, "employs", "out", "company", self.c, "", "", "", ""),
        ])
        self.assertEqual(max(r[0] for r in rows), 2)  # bounded

    def test_directions_both_sides(self):
        # the achievement's walk shows the document as its 'from' endpoint
        a_rows = store.neighbors(self.db, "achievement", self.a, depth=1)
        doc = [r for r in a_rows if r[3] == "document"][0]
        self.assertEqual(doc[2], "from")
        # the document's walk shows the achievement as its 'to' endpoint,
        # and its superseded predecessor as an 'out' FK edge
        d_rows = store.neighbors(self.db, "document", self.d1, depth=1)
        self.assertEqual(d_rows, [
            (1, "resume_achievement", "to", "achievement", self.a,
             "", "user", "user_fact",
             datetime.date.today().isoformat()),
            (1, "supersedes", "out", "document", self.d0, "", "", "", ""),
        ])

    def test_refuses_unknown_type(self):
        with self.assertRaises(ValueError):
            store.neighbors(self.db, "friend", 1)

    def test_refuses_missing_id(self):
        with self.assertRaises(ValueError):
            store.neighbors(self.db, "achievement", 99)

    def test_refuses_bad_depth(self):
        with self.assertRaises(ValueError):
            store.neighbors(self.db, "achievement", self.a, depth=3)


if __name__ == "__main__":
    unittest.main()
