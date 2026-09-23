# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Shared fixtures for the reasoner test-suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app import health  # noqa: E402
from app.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_caches(monkeypatch: pytest.MonkeyPatch):
    """Isolate the settings singleton and the cached solver probe per test."""
    get_settings.cache_clear()
    health.reset_hexlite_probe()
    for name in (
        "DALICC_SPARQL_ENDPOINT",
        "DALICC_DEPENDENCY_GRAPH",
        "DALICC_LICENSE_LIBRARY_GRAPH",
        "DALICC_CUSTOM_LICENSES_GRAPH",
        "DALICC_REASONER_RESTRICT_GRAPHS",
        "DALICC_REASONER_CONFIG",
        "REASONER_TIMEOUT_SECONDS",
        "DALICC_REASONER_TIMEOUT_SECONDS",
        "REASONER_HEXLITE_BIN",
    ):
        monkeypatch.delenv(name, raising=False)
    yield
    get_settings.cache_clear()
    health.reset_hexlite_probe()


# --- real solver output captured from `hexlite 1.4.1` + `clingo 5.8.2` --------

CONFLICT_STDOUT = (
    '{directConflict("https://dalicc.net/licenselibrary/A",'
    '"http://www.w3.org/ns/odrl/2/permission",'
    '"http://www.w3.org/ns/odrl/2/distribute",'
    '"https://dalicc.net/licenselibrary/B",'
    '"http://www.w3.org/ns/odrl/2/prohibition",'
    '"http://www.w3.org/ns/odrl/2/distribute","direct"),'
    'derivedConflict("https://dalicc.net/licenselibrary/A",'
    '"http://www.w3.org/ns/odrl/2/permission",'
    '"http://www.w3.org/ns/odrl/2/modify",'
    '"https://dalicc.net/licenselibrary/B",'
    '"http://www.w3.org/ns/odrl/2/prohibition",'
    '"http://www.w3.org/ns/odrl/2/derive","includedIn",'
    '"http://www.w3.org/ns/odrl/2/modify",'
    '"http://www.w3.org/ns/odrl/2/derive","dependencygraph")}\n'
)

NO_CONFLICT_STDOUT = "{}\n"

DEPGRAPH_STDOUT = (
    '{t("http://www.w3.org/ns/odrl/2/modify",'
    '"http://www.w3.org/ns/odrl/2/includedIn",'
    '"http://www.w3.org/ns/odrl/2/derive")}\n'
)

#: hexlite writes these to stderr, but a misconfigured deployment may merge the
#: streams -- the parser must survive that.
WARNING_NOISE = (
    "<block>:17:39-49: info: atom does not occur in any rule head:\n"
    "  action(X)\n\n"
    "W:clingobackend.py:239:cannot parse external atom term "
    "'http://www.w3.org/ns/odrl/2/modify' with clingo! (creating a string out of it)\n"
)


@pytest.fixture
def conflict_stdout() -> str:
    return CONFLICT_STDOUT


@pytest.fixture
def no_conflict_stdout() -> str:
    return NO_CONFLICT_STDOUT


@pytest.fixture
def depgraph_stdout() -> str:
    return DEPGRAPH_STDOUT
