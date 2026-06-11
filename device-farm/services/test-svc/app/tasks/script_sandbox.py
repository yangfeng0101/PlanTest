"""Script sandbox policy — single source of truth.

Both the runtime executor (`app.tasks.executor`) and the static validator
(`app.api.scripts`) must agree on which top-level modules a user script is
allowed to import. Keeping two independent lists in two different files
has caused drift in the past; this module is the single source.

To allow a new module for user scripts:
  1. Add the module name to `ALLOWED_SCRIPT_IMPORTS` here.
  2. Add the same name to `ALLOWED_IMPORTS` in this module too.
  3. Confirm the module is installed in `requirements.txt`.

Tests in `tests/test_script_sandbox.py` enforce that the static whitelist
and the runtime whitelist stay in lockstep.
"""

from __future__ import annotations

import math
import random
import re
import time
import uuid

# Top-level module names that user scripts may import.
# Used by:
#   - app.api.scripts._validate_script_content (static validation, friendly error)
#   - app.tasks.executor.safe_import (runtime enforcement via custom import hook)
# Tests pin the two consumers to this single set.
ALLOWED_SCRIPT_IMPORTS: frozenset[str] = frozenset(
    {
        "datetime",
        "decimal",
        "json",
        "math",
        "random",
        "re",
        "requests",
        "time",
        "uuid",
    }
)

# Pre-imported module objects used by the runtime sandbox's `safe_import`.
# The keys MUST be a subset of ALLOWED_SCRIPT_IMPORTS.
ALLOWED_IMPORTS: dict[str, object] = {
    "datetime": __import__("datetime"),
    "decimal": __import__("decimal"),
    "json": __import__("json"),
    "math": math,
    "random": random,
    "re": re,
    "requests": __import__("requests"),
    "time": time,
    "uuid": uuid,
}


def assert_consistent() -> None:
    """Raise if the two whitelists drift apart.

    Intentionally NOT called at module import time — that would run on
    every Celery worker boot. Instead, the test suite (and any explicit
    diagnostic) calls this; if the two lists ever drift, the test fails
    before the inconsistency can reach production.
    """
    runtime_names = set(ALLOWED_IMPORTS.keys())
    static_names = set(ALLOWED_SCRIPT_IMPORTS)
    missing_in_runtime = static_names - runtime_names
    missing_in_static = runtime_names - static_names
    if missing_in_runtime or missing_in_static:
        raise RuntimeError(
            "Script sandbox whitelist drift detected: "
            f"missing_in_runtime={sorted(missing_in_runtime)} "
            f"missing_in_static={sorted(missing_in_static)}. "
            "Update both lists in app.tasks.script_sandbox together."
        )
