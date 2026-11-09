"""Shared paths for the store tests. Synthetic fixtures only — no user data."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
STATE = FIXTURES / "state"
