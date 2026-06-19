"""Shared test fixtures as JSON files for contract tests.

These files provide standardized test data that can be loaded by both
pytest tests and the YAML contract runner.
"""

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent


def load_fixture(name: str) -> dict | list:
    """Load a JSON fixture file."""
    path = FIXTURES_DIR / f"{name}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Pre-built test fixtures for contract tests
# These mirror the conftest.py fixtures but as static files
