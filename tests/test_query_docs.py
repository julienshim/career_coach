"""The STANDARDS query row carries a minimal
runnable plan example; it is the same one `query --example` prints
(no drift between the contract and the code), and it actually runs
against the fixture db and returns rows — a cold agent's first query
works from the contract alone. The parse contract: the first
brace-balanced JSON object in the query ops row is the example (its
values carry no braces)."""
import contextlib
import io
import json
import pathlib
import tempfile
import unittest

import scripts.store as store
from tests import helpers

STANDARDS = helpers.ROOT / "standards" / "STANDARDS.md"


def example_from_standards():
    line = next(
        l for l in STANDARDS.read_text(encoding="utf-8").splitlines()
        if l.startswith("| `query"))
    start = line.index("{")
    depth = 0
    for i in range(start, len(line)):
        if line[i] == "{":
            depth += 1
        elif line[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(line[start:i + 1])
    raise AssertionError("unbalanced braces in the query ops row")


class TestQueryExample(unittest.TestCase):
    def test_standards_example_matches_example_flag(self):
        self.assertEqual(example_from_standards(),
                         json.loads(store.EXAMPLE_PLAN))

    def test_example_flag_prints_plan_without_opening_the_db(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            store.main(["query", "--db", "not-a-real-db.db", "--example"])
        self.assertEqual(json.loads(buf.getvalue()),
                         json.loads(store.EXAMPLE_PLAN))

    def test_standards_example_runs_against_fixture(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            db = pathlib.Path(tmp.name) / "t.db"
            store.migrate(db, helpers.FIXTURES / "ledger_fixture.tsv")
            env = store.query(db, example_from_standards())
            self.assertEqual(env["meta"]["mode"], "rows")
            self.assertGreaterEqual(env["meta"]["rows_returned"], 1)
            self.assertTrue(all(
                {"entity", "id"} <= set(r) for r in env["results"]))
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
