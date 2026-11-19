import datetime
import pathlib
import tempfile
import unittest

import scripts.store as store


class TestGovernanceReads(unittest.TestCase):
    """governance / find-disconnected / export-relationships."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        self.conn = store.db_connect(self.db)
        # A synthetic graph with mixed governance states, one deliberately
        # isolated skill, and one attr value containing a tab + a quote.
        self.p = store.upsert_person(self.db, full_name="P")
        self.c = store.upsert_company(self.db, name="C")
        self.r = store.upsert_role(self.db, company="C", title="R")
        self.pr = store.upsert_project(self.db, name="Pr")
        self.s1 = store.upsert_skill(self.db, name="S1")
        self.s2 = store.upsert_skill(self.db, name="S2")  # isolated
        self.a1 = store.upsert_achievement(self.db, title="A1", role_id=self.r)
        self.e1 = store.upsert_evidence(self.db, evid_id="EV-1", claim="c")
        self.d1 = store.upsert_document(self.db, doc_type="resume", title="R1",
                                        path="r1.md")
        self.d2 = store.upsert_document(self.db, doc_type="resume", title="R2",
                                        path="r1.md", version=2,
                                        supersedes_id=self.d1)
        self.l_skill = store.link(self.db, "achievement_skill",
                                  "achievement:%d" % self.a1,
                                  "skill:%d" % self.s1, as_user=False)
        self.l_ev = store.link(self.db, "achievement_evidence",
                               "achievement:%d" % self.a1, "evidence:%d" % self.e1)
        self.l_doc = store.link(self.db, "resume_achievement",
                                "document:%d" % self.d1,
                                "achievement:%d" % self.a1,
                                {"placement": 'sec\t"x"'})

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_governance_lists_exact_state(self):
        today = datetime.date.today().isoformat()
        rows = store.governance(self.db, "ai_suggested")
        self.assertEqual(rows, [("achievement_skill", self.l_skill, "A1 -> S1",
                                 "ai_suggested", "ai", today)])
        rows = store.governance(self.db, "user_fact")
        got = {(t, i) for t, i, _n, _s, _p, _c in rows}
        self.assertEqual(got, {
            ("role", self.r), ("project", self.pr), ("skill", self.s1),
            ("skill", self.s2), ("achievement", self.a1), ("document", self.d1),
            ("document", self.d2), ("achievement_evidence", self.l_ev),
            ("resume_achievement", self.l_doc)})

    def test_governance_refuses_bad_state(self):
        with self.assertRaises(ValueError):
            store.governance(self.db, "pending")

    def test_find_disconnected_exact_set(self):
        rows = store.find_disconnected(self.db)
        self.assertEqual(rows, [("project", self.pr, "Pr"),
                                ("skill", self.s2, "S2")])

    def test_find_disconnected_entity_filter(self):
        rows = store.find_disconnected(self.db, "skill")
        self.assertEqual(rows, [("skill", self.s2, "S2")])
        with self.assertRaises(ValueError):
            store.find_disconnected(self.db, "friend")

    def test_export_relationships_exact_tsv(self):
        today = datetime.date.today().isoformat()
        out = pathlib.Path(self.tmp.name) / "rel.tsv"
        store.export_relationships(self.db, out)
        exp = "\n".join([
            "junction\tfrom_type\tfrom_id\tfrom_name\tto_type\tto_id\tto_name"
            "\tattrs\tprovenance\tgovernance_state\tcreated_at",
            store.format_tsv_row(["achievement_skill", "achievement",
                                  str(self.a1), "A1", "skill", str(self.s1), "S1",
                                  "", "ai", "ai_suggested", today]),
            store.format_tsv_row(["achievement_evidence", "achievement",
                                  str(self.a1), "A1", "evidence", str(self.e1),
                                  "EV-1", "", "user", "user_fact", today]),
            store.format_tsv_row(["resume_achievement", "document",
                                  str(self.d1), "R1", "achievement",
                                  str(self.a1), "A1", 'placement=sec\t"x"',
                                  "user", "user_fact", today]),
        ]) + "\n"
        self.assertEqual(out.read_text(encoding="utf-8"), exp)

    def test_export_relationships_stable(self):
        out1 = pathlib.Path(self.tmp.name) / "rel1.tsv"
        out2 = pathlib.Path(self.tmp.name) / "rel2.tsv"
        store.export_relationships(self.db, out1)
        store.export_relationships(self.db, out2)
        self.assertEqual(out1.read_bytes(), out2.read_bytes())


if __name__ == "__main__":
    unittest.main()
