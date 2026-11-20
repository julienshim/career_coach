import contextlib
import io
import json
import pathlib
import sqlite3
import tempfile
import unittest

import scripts.store as store


def seed_fixture(db):
    """Synthetic fixture (Acme / Globex, EVID-9001+, 3/1/2026 range): the
    knowledge graph + one operational application + one event.

    Junctions: a1 -> s1, s3; a2 -> s2; a3 -> s1. Evidence: a1 -> e1, e3;
    a2 -> e2. The opening requires s1 + s3."""
    conn = store.db_connect(db)
    try:
        with conn:
            c1 = conn.execute(
                "INSERT INTO company (name, created_at, updated_at) "
                "VALUES ('Acme', '2026-03-01', '2026-03-01')").lastrowid
            conn.execute(
                "INSERT INTO company (name, created_at, updated_at) "
                "VALUES ('Globex', '2026-03-01', '2026-03-01')")
            for name, cat in (("Data Pipelines", "technical"),
                              ("Search Infra", "technical"),
                              ("Distributed Systems", "domain")):
                conn.execute(
                    "INSERT INTO skill (name, category, created_at, "
                    "updated_at) VALUES (?, ?, '2026-03-01', '2026-03-01')",
                    (name, cat))
            for title in ("Built the ingestion pipeline",
                          "Shipped the ranking service",
                          "Migrated the cluster"):
                conn.execute(
                    "INSERT INTO achievement (title, created_at, updated_at) "
                    "VALUES (?, '2026-03-01', '2026-03-01')", (title,))
            for eid, claim in (("EVID-9001", "throughput 1.2M events per second"),
                               ("EVID-9002", "p99 latency under 40ms"),
                               ("EVID-9003", "zero-downtime migration")):
                conn.execute(
                    "INSERT INTO evidence (evid_id, claim, source_kind, "
                    "created_at, updated_at) VALUES (?, ?, 'code', "
                    "'2026-03-01', '2026-03-01')", (eid, claim))
            jid = conn.execute(
                "INSERT INTO job_opening (company_id, title, created_at, "
                "updated_at) VALUES (?, 'Data Engineer', '2026-03-01', "
                "'2026-03-01')", (c1,)).lastrowid
            for aid, sid in ((1, 1), (1, 3), (2, 2), (3, 1)):
                conn.execute(
                    "INSERT INTO achievement_skill (achievement_id, skill_id, "
                    "created_at) VALUES (?, ?, '2026-03-01')", (aid, sid))
            for aid, eid in ((1, 1), (1, 3), (2, 2)):
                conn.execute(
                    "INSERT INTO achievement_evidence (achievement_id, "
                    "evidence_id, created_at) VALUES (?, ?, '2026-03-01')",
                    (aid, eid))
            for sid in (1, 3):
                conn.execute(
                    "INSERT INTO job_skill (job_opening_id, skill_id, "
                    "required_level, created_at) VALUES (?, ?, 'daily', "
                    "'2026-03-01')", (jid, sid))
            conn.execute(
                "INSERT INTO contact (name, title, email, company_id, "
                "created_at, updated_at) VALUES ('Jane', 'TA', "
                "'zqxw@example.com', ?, '2026-03-01', '2026-03-01')", (c1,))
    finally:
        conn.close()
    # the event row goes through the op (it auto-creates the application
    # for the pair; company 'Acme' exists from the raw seed above)
    store.log_event(db, "3/1/2026", "Job Application", "Acme",
                    "Data Engineer", "Company Portal",
                    "Application Submitted",
                    "portal; pipeline backpressure tuning noted")


class TestQueryRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        seed_fixture(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_constants_pinned(self):
        self.assertEqual(store.DEFAULT_LIMIT, 200)
        self.assertEqual(store.MAX_LIMIT, 1000)
        self.assertEqual(store.MAX_TRAVERSAL_STEPS, 3)
        self.assertEqual(
            store.QUERY_ENTITIES,
            ["person", "company", "role", "project", "skill",
             "achievement", "evidence", "document", "contact", "job_opening",
             "application", "interview", "interaction", "event"])

    def test_rows_happy_shape(self):
        out = store.query(self.db, {"entity": "skill"})
        self.assertEqual(len(out["results"]), 3)
        self.assertEqual(
            out["results"][0],
            {"entity": "skill", "id": 1, "name": "Data Pipelines",
             "category": "technical", "notes_ref": None,
             "provenance": "user_fact", "governance_state": "user_fact",
             "created_at": "2026-03-01", "updated_at": "2026-03-01"})
        self.assertEqual(out["meta"], {
            "entity": "skill", "mode": "rows", "rows_returned": 3,
            "rows_total": 3, "truncated": False,
            "stages": [{"entity": "skill", "rows": 3}]})

    def test_filter_ops(self):
        def q(f):
            return store.query(
                self.db, {"entity": "skill", "filters": [f]})["results"]
        self.assertEqual(
            [r["id"] for r in q(
                {"field": "name", "op": "=", "value": "Search Infra"})], [2])
        self.assertEqual(
            [r["id"] for r in q(
                {"field": "category", "op": "!=", "value": "domain"})], [1, 2])
        self.assertEqual(
            [r["id"] for r in q({"field": "id", "op": ">", "value": 1})],
            [2, 3])
        self.assertEqual(
            [r["id"] for r in q({"field": "id", "op": "<", "value": 3})],
            [1, 2])
        self.assertEqual(
            [r["id"] for r in q({"field": "id", "op": ">=", "value": 2})],
            [2, 3])
        self.assertEqual(
            [r["id"] for r in q({"field": "id", "op": "<=", "value": 2})],
            [1, 2])
        self.assertEqual(
            [r["id"] for r in q(
                {"field": "name", "op": "IN",
                 "value": ["Data Pipelines", "Search Infra"]})], [1, 2])
        self.assertEqual(
            [r["id"] for r in q(
                {"field": "name", "op": "LIKE", "value": "%Infra%"})], [2])
        self.assertEqual(
            [r["id"] for r in q(
                {"field": "notes_ref", "op": "IS NULL"})], [1, 2, 3])
        self.assertEqual(
            [r["id"] for r in q(
                {"field": "notes_ref", "op": "IS NOT NULL"})], [])

    def test_order_by_and_default_id_order(self):
        out = store.query(self.db, {
            "entity": "skill",
            "order_by": {"field": "name", "direction": "desc"}})
        self.assertEqual(
            [r["name"] for r in out["results"]],
            ["Search Infra", "Distributed Systems", "Data Pipelines"])
        out = store.query(self.db, {"entity": "skill"})
        self.assertEqual([r["id"] for r in out["results"]], [1, 2, 3])

    def test_limit_and_truncation_meta(self):
        out = store.query(self.db, {"entity": "skill", "limit": 2})
        self.assertEqual(len(out["results"]), 2)
        self.assertEqual(out["meta"]["rows_returned"], 2)
        self.assertEqual(out["meta"]["rows_total"], 3)
        self.assertTrue(out["meta"]["truncated"])
        out = store.query(self.db, {"entity": "skill", "limit": 10})
        self.assertFalse(out["meta"]["truncated"])

    def test_cap_refusals(self):
        with self.assertRaises(ValueError) as ctx:
            store.query(self.db, {"entity": "skill", "limit": 1001})
        self.assertIn("max 1000", str(ctx.exception))
        with self.assertRaises(ValueError):
            store.query(self.db, {"entity": "skill", "limit": 0})
        with self.assertRaises(ValueError) as ctx:
            store.query(self.db, {
                "entity": "achievement",
                "traverse": [{"via": "achievement_skill"}] * 4})
        self.assertIn("max 3", str(ctx.exception))

    def test_refusal_battery(self):
        cases = [
            ({"entity": "meta"}, "unknown entity"),
            ({"entity": "note"}, "unknown entity"),
            ({"entity": "achievement",
              "filters": [{"field": "nope", "op": "=", "value": 1}]},
             "unknown field 'nope' on achievement"),
            ({"entity": "skill",
              "filters": [{"field": "name", "op": "contains",
                           "value": "x"}]},
             "bad filter op"),
            ({"entity": "skill", "mode": "rows2"}, "bad mode"),
            ({"entity": "skill", "mode": "group"}, "group_by is required"),
            ({"entity": "skill", "mode": "rows",
              "group_by": {"field": "name"}},
             "group_by is only for group mode"),
            ({"entity": "skill",
              "order_by": {"field": "name", "direction": "up"}},
             "bad order_by direction"),
            ({"entity": "skill", "search": "x"}, "exactly one"),
            ({"filters": []}, "exactly one"),
        ]
        for plan, frag in cases:
            with self.assertRaises(ValueError) as ctx:
                store.query(self.db, plan)
            self.assertIn(frag, str(ctx.exception),
                          "plan %r did not refuse with %r" % (plan, frag))

    def test_plan_json_string(self):
        out = store.query(
            self.db, json.dumps({"entity": "skill", "limit": 1}))
        self.assertEqual(len(out["results"]), 1)

    def test_cli_plan_and_plan_file(self):
        plan = json.dumps({"entity": "skill", "limit": 1})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            store.main(["query", "--db", str(self.db), "--plan", plan])
        out = json.loads(buf.getvalue())
        self.assertEqual(len(out["results"]), 1)
        self.assertEqual(out["meta"]["entity"], "skill")
        pf = pathlib.Path(self.tmp.name) / "plan.json"
        pf.write_text(plan)
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            store.main(["query", "--db", str(self.db),
                        "--plan-file", str(pf)])
        out2 = json.loads(buf2.getvalue())
        self.assertEqual(len(out2["results"]), 1)


class TestQueryTraversal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        seed_fixture(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_hop_out(self):
        out = store.query(self.db, {
            "entity": "achievement",
            "traverse": [{"via": "achievement_skill"}]})
        self.assertEqual(
            sorted((r["id"], r["name"]) for r in out["results"]),
            [(1, "Data Pipelines"), (2, "Search Infra"),
             (3, "Distributed Systems")])
        self.assertEqual(out["meta"]["stages"],
                         [{"entity": "achievement", "rows": 3},
                          {"entity": "skill", "rows": 3}])

    def test_one_hop_in(self):
        out = store.query(self.db, {
            "entity": "skill",
            "filters": [{"field": "id", "op": "=", "value": 1}],
            "traverse": [{"via": "achievement_skill"}]})
        self.assertEqual([r["id"] for r in out["results"]], [1, 3])

    def test_three_hop_acceptance(self):
        out = store.query(self.db, {
            "entity": "job_opening",
            "traverse": [{"via": "job_skill"},
                         {"via": "achievement_skill"},
                         {"via": "achievement_evidence"}]})
        self.assertEqual(
            sorted(r["evid_id"] for r in out["results"]),
            ["EVID-9001", "EVID-9003"])
        for r in out["results"]:
            self.assertEqual(r["entity"], "evidence")
        self.assertEqual(out["meta"]["stages"],
                         [{"entity": "job_opening", "rows": 1},
                          {"entity": "skill", "rows": 2},
                          {"entity": "achievement", "rows": 2},
                          {"entity": "evidence", "rows": 2}])
        self.assertEqual(out["meta"]["rows_returned"], 2)
        self.assertFalse(out["meta"]["truncated"])

    def test_dedupe_by_entity_id(self):
        out = store.query(self.db, {
            "entity": "achievement",
            "traverse": [{"via": "achievement_skill",
                          "order_by": {"field": "id",
                                       "direction": "asc"}}]})
        ids = [r["id"] for r in out["results"]]
        self.assertEqual(ids, [1, 2, 3])
        self.assertEqual(ids.count(1), 1)

    def test_step_filter_order_limit(self):
        out = store.query(self.db, {
            "entity": "achievement",
            "traverse": [{"via": "achievement_skill",
                          "filters": [{"field": "category", "op": "=",
                                       "value": "technical"}],
                          "order_by": {"field": "id",
                                       "direction": "asc"},
                          "limit": 1}]})
        self.assertEqual([r["id"] for r in out["results"]], [1])

    def test_step_cap_refusal(self):
        with self.assertRaises(ValueError) as ctx:
            store.query(self.db, {
                "entity": "achievement",
                "traverse": [{"via": "achievement_skill",
                              "limit": 1001}]})
        self.assertIn("max 1000", str(ctx.exception))

    def test_disconnected_junction_refused(self):
        with self.assertRaises(ValueError) as ctx:
            store.query(self.db, {
                "entity": "skill",
                "traverse": [{"via": "contact_company"}]})
        msg = str(ctx.exception)
        for frag in ("does not touch", "skill", "contact", "company"):
            self.assertIn(frag, msg)
        with self.assertRaises(ValueError) as ctx:
            store.query(self.db, {
                "entity": "skill",
                "traverse": [{"via": "no_such_junction"}]})
        self.assertIn("unknown junction", str(ctx.exception))

    def test_step_filter_field_gated(self):
        with self.assertRaises(ValueError) as ctx:
            store.query(self.db, {
                "entity": "achievement",
                "traverse": [{"via": "achievement_skill",
                              "filters": [{"field": "nope", "op": "=",
                                           "value": 1}]}]})
        self.assertIn("unknown field 'nope' on skill", str(ctx.exception))


class TestQuerySearch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        seed_fixture(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_rebuilt_at_open(self):
        # seed_fixture's last op call rebuilt the index BEFORE the event
        # row was inserted; a fresh open must re-derive it (derived
        # state, the view pattern).
        conn = store.db_connect(self.db)
        conn.close()
        raw = sqlite3.connect(str(self.db))
        try:
            n = raw.execute(
                "SELECT COUNT(*) FROM search_index").fetchone()[0]
        finally:
            raw.close()
        # 2 companies + 3 skills + 3 achievements + 3 evidence
        # + 1 job opening + 1 contact + 1 application + 1 event
        self.assertEqual(n, 15)

    def test_search_returns_cited_rows(self):
        out = store.query(self.db, {"search": "backpressure"})
        self.assertEqual(len(out["results"]), 1)
        r = out["results"][0]
        self.assertEqual(r["entity"], "event")
        self.assertEqual(r["id"], 1)
        self.assertIn("backpressure", r["note"])
        self.assertEqual(out["meta"]["mode"], "search")
        self.assertEqual(out["meta"]["rows_returned"], 1)
        self.assertEqual(out["meta"]["rows_total"], 1)
        self.assertFalse(out["meta"]["truncated"])

    def test_search_entities_subset(self):
        out = store.query(
            self.db, {"search": "Pipelines", "entities": ["skill"]})
        self.assertEqual([(r["entity"], r["id"]) for r in out["results"]],
                         [("skill", 1)])
        out = store.query(
            self.db, {"search": "Pipelines", "entities": ["company"]})
        self.assertEqual(out["results"], [])
        self.assertEqual(out["meta"]["rows_total"], 0)
        with self.assertRaises(ValueError):
            store.query(self.db, {"search": "x", "entities": []})
        with self.assertRaises(ValueError) as ctx:
            store.query(
                self.db, {"search": "x", "entities": ["not_an_entity"]})
        self.assertIn("not_an_entity", str(ctx.exception))

    def test_search_order_by_rank(self):
        out1 = store.query(self.db, {"search": "the"})
        out2 = store.query(self.db, {"search": "the"})
        self.assertGreaterEqual(len(out1["results"]), 2)
        self.assertEqual(out1["results"], out2["results"])
        for r in out1["results"]:
            self.assertIn("entity", r)
            self.assertIn("id", r)

    def test_pii_excluded_from_index(self):
        # the token lives only in contact.email — never indexed
        self.assertEqual(
            store.query(self.db, {"search": "zqxw"})["results"], [])
        # the contact's name IS indexed
        out = store.query(self.db, {"search": "Jane"})
        self.assertEqual(
            [(r["entity"], r["name"]) for r in out["results"]],
            [("contact", "Jane")])
        # person is excluded entirely: a unique token in objective
        conn = store.db_connect(self.db)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO person (full_name, objective, location, "
                    "created_at, updated_at) VALUES ('Test Person', "
                    "'zqkzr unique token', 'Nowhere', '2026-03-01', "
                    "'2026-03-01')")
        finally:
            conn.close()
        self.assertEqual(
            store.query(self.db, {"search": "zqkzr"})["results"], [])

    def test_non_indexed_columns_not_searchable(self):
        # "company" appears only in the event's channel column and
        # raw_row — neither is indexed (note + type + outcome only)
        self.assertEqual(
            store.query(self.db, {"search": "Company"})["results"], [])

    def test_bad_fts_syntax_refused(self):
        # valid text, invalid FTS5 syntax: an unmatched quote
        with self.assertRaises(ValueError) as ctx:
            store.query(self.db, {"search": 'abc"'})
        self.assertIn("bad search query", str(ctx.exception))

    def test_rebuild_visible_to_read_only(self):
        conn = store.db_connect(self.db)
        conn.close()
        raw = sqlite3.connect(
            "file:" + str(self.db).replace(" ", "%20") + "?mode=ro",
            uri=True)
        try:
            self.assertGreater(
                raw.execute(
                    "SELECT COUNT(*) FROM search_index").fetchone()[0], 0)
        finally:
            raw.close()

    def test_search_truncation(self):
        out = store.query(self.db, {"search": "the", "limit": 1})
        self.assertEqual(len(out["results"]), 1)
        self.assertTrue(out["meta"]["truncated"])
        self.assertGreaterEqual(out["meta"]["rows_total"], 2)


class TestQueryModes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        seed_fixture(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_count_happy(self):
        out = store.query(self.db, {"entity": "achievement",
                                    "mode": "count"})
        self.assertEqual(out["results"], [{"count": 3}])
        self.assertEqual(out["meta"]["mode"], "count")
        self.assertEqual(out["meta"]["rows_total"], 3)
        self.assertFalse(out["meta"]["truncated"])

    def test_count_with_filters_and_path(self):
        out = store.query(self.db, {
            "entity": "achievement",
            "filters": [{"field": "id", "op": "<", "value": 3}],
            "mode": "count"})
        self.assertEqual(out["results"], [{"count": 2}])
        out = store.query(self.db, {
            "entity": "job_opening",
            "traverse": [{"via": "job_skill"},
                         {"via": "achievement_skill"},
                         {"via": "achievement_evidence"}],
            "mode": "count"})
        self.assertEqual(out["results"], [{"count": 2}])

    def test_group_happy_ordering(self):
        out = store.query(self.db, {
            "entity": "skill", "mode": "group",
            "group_by": {"field": "category"}})
        self.assertEqual(out["results"],
                         [{"category": "technical", "count": 2},
                          {"category": "domain", "count": 1}])

    def test_group_null_key_sorts_first(self):
        out = store.query(self.db, {
            "entity": "skill", "mode": "group",
            "group_by": {"field": "notes_ref"}})
        self.assertEqual(out["results"],
                         [{"notes_ref": None, "count": 3}])

    def test_group_cap_and_truncation(self):
        out = store.query(self.db, {
            "entity": "skill", "mode": "group", "limit": 2,
            "group_by": {"field": "id"}})
        self.assertEqual(len(out["results"]), 2)
        self.assertTrue(out["meta"]["truncated"])
        self.assertEqual(out["meta"]["rows_total"], 3)

    def test_structural_read_only(self):
        conn = store._read_only_connect(self.db)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute(
                    "INSERT INTO company (name, created_at, updated_at) "
                    "VALUES ('X', '2026-01-01', '2026-01-01')")
        finally:
            conn.close()

    def test_query_op_is_read_only_end_to_end(self):
        # the 14 data tables are untouched by the op; the derived index
        # is a pure function of them (rebuilt at the op's open, P11)
        def counts():
            conn = sqlite3.connect(str(self.db))
            try:
                return {t: conn.execute(
                    "SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                    for t in store.QUERY_ENTITIES}
            finally:
                conn.close()
        before = counts()
        store.query(self.db, {
            "entity": "job_opening",
            "traverse": [{"via": "job_skill"},
                         {"via": "achievement_skill"},
                         {"via": "achievement_evidence"}]})
        store.query(self.db, {"search": "the"})
        self.assertEqual(counts(), before)
        conn = sqlite3.connect(str(self.db))
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM search_index").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(n, 15)


if __name__ == "__main__":
    unittest.main()
