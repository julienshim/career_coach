import pathlib
import tempfile
import unittest

import scripts.store as store


class TestRelationships(unittest.TestCase):
    """link / verify / reject / unlink over the typed junctions."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        self.conn = store.db_connect(self.db)
        # A synthetic graph: one document, two achievements, two skills,
        # one evidence (ids come back from the ops, not assumed).
        self.d1 = store.upsert_document(self.db, doc_type="resume", title="R",
                                        path="r.md")
        self.a1 = store.upsert_achievement(self.db, title="A1")
        self.a2 = store.upsert_achievement(self.db, title="A2")
        self.s1 = store.upsert_skill(self.db, name="S1")
        self.s2 = store.upsert_skill(self.db, name="S2")
        self.e1 = store.upsert_evidence(self.db, evid_id="EV-1", claim="c")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _junction_row(self, junction, rowid):
        table = store.JUNCTIONS[junction]["table"]
        cur = self.conn.execute("SELECT * FROM %s WHERE id = ?" % table, (rowid,))
        r = cur.fetchone()
        return dict(zip([c[0] for c in cur.description], r)) if r else None

    def _count(self, junction):
        table = store.JUNCTIONS[junction]["table"]
        return self.conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]

    def test_link_user_fact(self):
        rowid = store.link(self.db, "resume_achievement",
                           "document:%d" % self.d1, "achievement:%d" % self.a1,
                           {"placement": "experience"})
        row = self._junction_row("resume_achievement", rowid)
        self.assertEqual(row["document_id"], self.d1)
        self.assertEqual(row["achievement_id"], self.a1)
        self.assertEqual(row["placement"], "experience")
        self.assertEqual(row["provenance"], "user")
        self.assertEqual(row["governance_state"], "user_fact")

    def test_link_ai_suggested(self):
        rowid = store.link(self.db, "achievement_skill",
                           "achievement:%d" % self.a1, "skill:%d" % self.s1,
                           as_user=False)
        row = self._junction_row("achievement_skill", rowid)
        self.assertEqual(row["provenance"], "ai")
        self.assertEqual(row["governance_state"], "ai_suggested")

    def test_verify_promotes_ai_only(self):
        rowid = store.link(self.db, "achievement_evidence",
                           "achievement:%d" % self.a1, "evidence:%d" % self.e1,
                           as_user=False)
        store.verify(self.db, "achievement_evidence", rowid)
        row = self._junction_row("achievement_evidence", rowid)
        self.assertEqual(row["governance_state"], "user_verified")

    def test_verify_refuses_user_fact(self):
        rowid = store.link(self.db, "achievement_evidence",
                           "achievement:%d" % self.a1, "evidence:%d" % self.e1)
        with self.assertRaises(ValueError):
            store.verify(self.db, "achievement_evidence", rowid)

    def test_verify_refuses_double(self):
        rowid = store.link(self.db, "achievement_evidence",
                           "achievement:%d" % self.a1, "evidence:%d" % self.e1,
                           as_user=False)
        store.verify(self.db, "achievement_evidence", rowid)
        with self.assertRaises(ValueError):
            store.verify(self.db, "achievement_evidence", rowid)

    def test_verify_reject_unlink_refuse_missing_row(self):
        # the "the row must exist" clause of the pinned verify / reject /
        # unlink rules (review addition: the refusals were implemented but
        # untested)
        with self.assertRaises(ValueError):
            store.verify(self.db, "achievement_evidence", 999)
        with self.assertRaises(ValueError):
            store.reject(self.db, "achievement_evidence", 999)
        with self.assertRaises(ValueError):
            store.unlink(self.db, "achievement_evidence", 999)
        with self.assertRaises(ValueError):
            store.verify(self.db, "friendship", 1)
        with self.assertRaises(ValueError):
            store.reject(self.db, "friendship", 1)
        self.assertEqual(self._count("achievement_evidence"), 0)

    def test_link_refuses_duplicate(self):
        store.link(self.db, "achievement_evidence",
                   "achievement:%d" % self.a1, "evidence:%d" % self.e1)
        with self.assertRaises(ValueError):
            store.link(self.db, "achievement_evidence",
                       "achievement:%d" % self.a1, "evidence:%d" % self.e1)
        self.assertEqual(self._count("achievement_evidence"), 1)

    def test_link_refuses_missing_entity(self):
        with self.assertRaises(ValueError):
            store.link(self.db, "achievement_skill",
                       "achievement:%d" % self.a1, "skill:99")
        self.assertEqual(self._count("achievement_skill"), 0)

    def test_link_refuses_unknown_junction(self):
        with self.assertRaises(ValueError):
            store.link(self.db, "friendship", "skill:1", "skill:2")

    def test_link_refuses_bad_ref(self):
        # a non-digit id (the type is the junction's expected from-type)
        with self.assertRaises(ValueError):
            store.link(self.db, "achievement_skill", "achievement:abc",
                       "skill:%d" % self.s1)
        with self.assertRaises(ValueError):
            store.link(self.db, "achievement_skill", "nonsense:1",
                       "skill:%d" % self.s1)
        with self.assertRaises(ValueError):
            store.link(self.db, "achievement_skill", "skill 1",
                       "skill:%d" % self.s1)

    def test_link_bad_attr_refused(self):
        # an attr that is not valid for this junction
        with self.assertRaises(ValueError):
            store.link(self.db, "resume_achievement",
                       "document:%d" % self.d1, "achievement:%d" % self.a1,
                       {"level": "daily"})
        # an 'evidence' attr pointing at a missing evidence id
        with self.assertRaises(ValueError):
            store.link(self.db, "achievement_skill",
                       "achievement:%d" % self.a1, "skill:%d" % self.s1,
                       {"evidence": "99"})

    def test_reject_and_unlink_mark(self):
        r1 = store.link(self.db, "achievement_evidence",
                        "achievement:%d" % self.a1, "evidence:%d" % self.e1)
        store.reject(self.db, "achievement_evidence", r1)
        self.assertEqual(
            self._junction_row("achievement_evidence", r1)["governance_state"],
            "rejected_outdated")
        r2 = store.link(self.db, "achievement_evidence",
                        "achievement:%d" % self.a2, "evidence:%d" % self.e1)
        store.unlink(self.db, "achievement_evidence", r2)
        self.assertEqual(
            self._junction_row("achievement_evidence", r2)["governance_state"],
            "rejected_outdated")
        # re-marking is refused; the rows stay (marked, never deleted)
        with self.assertRaises(ValueError):
            store.reject(self.db, "achievement_evidence", r1)
        self.assertEqual(self._count("achievement_evidence"), 2)


if __name__ == "__main__":
    unittest.main()
