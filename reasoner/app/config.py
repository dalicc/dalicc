# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Environment-driven configuration for the DALICC reasoner service.

``reasoner.config`` (an INI file with a ``[DEFAULT]`` section) is still read as
a fallback so that existing deployments keep working, but it is no longer
required: every value can be supplied through the environment.  Environment
variables win over the file, the file wins over the built-in defaults.

The module is imported both by the FastAPI application *and* by the hexlite
plugin, which runs in a separate ``hexlite`` subprocess, so it must stay free
of FastAPI/pydantic imports and cheap to import.
"""

from __future__ import annotations

import configparser
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

__all__ = ["ReasonerSettings", "get_settings", "package_root", "service_root"]

logger = logging.getLogger(__name__)

#: ``<repo>/reasoner/app`` -- the Python package directory.
PACKAGE_ROOT = Path(__file__).resolve().parent
#: ``<repo>/reasoner`` -- the service directory (also the image ``WORKDIR``).
SERVICE_ROOT = PACKAGE_ROOT.parent

DEFAULT_SPARQL_ENDPOINT = "http://virtuoso-db:8890/sparql"
DEFAULT_DEPENDENCY_GRAPH = "https://dalicc.net/dependencygraph/dg_default"
DEFAULT_DEPENDENCY_GRAPH_PREFIX = "https://dalicc.net/dependencygraph/"


def package_root() -> Path:
    """Return the directory of the ``app`` package (module-relative, not CWD)."""
    return PACKAGE_ROOT


def service_root() -> Path:
    """Return the service directory that contains ``app/`` and ``reasoner.config``."""
    return SERVICE_ROOT


def _config_file_values() -> dict[str, str]:
    """Read ``reasoner.config`` if present; never raise."""
    candidates = [
        (
            Path(os.environ["DALICC_REASONER_CONFIG"])
            if os.environ.get("DALICC_REASONER_CONFIG")
            else None
        ),
        SERVICE_ROOT / "reasoner.config",
        Path.cwd() / "reasoner.config",
    ]
    for candidate in candidates:
        if candidate is None or not candidate.is_file():
            continue
        parser = configparser.ConfigParser()
        try:
            parser.read(candidate)
        except (OSError, configparser.Error) as exc:
            logger.warning("ignoring unreadable config file %s: %s", candidate, exc)
            continue
        return dict(parser["DEFAULT"])
    return {}


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _bool_env(default: bool, *names: str) -> bool:
    raw = _first_env(*names)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _int_env(default: int, *names: str) -> int:
    raw = _first_env(*names)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("invalid integer %r for %s; falling back to %s", raw, names[0], default)
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class ReasonerSettings:
    """Resolved runtime configuration."""

    sparql_endpoint: str = DEFAULT_SPARQL_ENDPOINT
    #: Full IRI of the dependency-graph named graph.
    dependency_graph: str = DEFAULT_DEPENDENCY_GRAPH
    #: Named graph of the licence library.  Only used as a ``FROM`` restriction
    #: when :attr:`restrict_graphs` is enabled -- by default the plugin queries
    #: the store's default-graph union, which is what makes composed ("custom")
    #: licences visible and is what production has always done.
    license_library_graph: str = ""
    #: Named graph of the composed ("custom") licences, added alongside
    #: :attr:`license_library_graph` when :attr:`restrict_graphs` is enabled.
    custom_licenses_graph: str = ""
    #: Opt in to restricting the licence lookup to the two graphs above
    #: (``DALICC_REASONER_RESTRICT_GRAPHS``).  Off by default so that sharing a
    #: single ``.env`` with the API service cannot silently change the answers.
    restrict_graphs: bool = False
    #: Wall-clock budget for one ``hexlite`` run.
    timeout_seconds: int = 60
    #: Socket timeout for the plugin's SPARQL calls.
    sparql_timeout_seconds: int = 30
    #: Timeout for the ``/healthz`` SPARQL probe.
    health_timeout_seconds: int = 3
    log_level: str = "INFO"

    @property
    def from_graphs(self) -> tuple[str, ...]:
        """Named graphs to add as ``FROM`` clauses to the licence query."""
        if not self.restrict_graphs or not self.license_library_graph:
            return ()
        graphs = [self.license_library_graph]
        if self.custom_licenses_graph:
            graphs.append(self.custom_licenses_graph)
        return tuple(graphs)


def _resolve_dependency_graph(raw: str | None) -> str:
    """Accept either a full IRI or a bare graph name such as ``dg_default``."""
    if not raw:
        return DEFAULT_DEPENDENCY_GRAPH
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return DEFAULT_DEPENDENCY_GRAPH_PREFIX + raw.lstrip("/")


def load_settings() -> ReasonerSettings:
    """Build :class:`ReasonerSettings` from the environment and config file."""
    file_values = _config_file_values()
    return ReasonerSettings(
        sparql_endpoint=(
            _first_env("DALICC_SPARQL_ENDPOINT")
            or file_values.get("sparql_endpoint")
            or DEFAULT_SPARQL_ENDPOINT
        ),
        dependency_graph=_resolve_dependency_graph(
            _first_env("DALICC_DEPENDENCY_GRAPH") or file_values.get("dependency_graph")
        ),
        license_library_graph=(
            _first_env("DALICC_LICENSE_LIBRARY_GRAPH")
            or file_values.get("license_library_graph")
            or ""
        ),
        custom_licenses_graph=(
            _first_env("DALICC_CUSTOM_LICENSES_GRAPH")
            or file_values.get("custom_licenses_graph")
            or ""
        ),
        restrict_graphs=_bool_env(False, "DALICC_REASONER_RESTRICT_GRAPHS"),
        timeout_seconds=_int_env(
            60, "REASONER_TIMEOUT_SECONDS", "DALICC_REASONER_TIMEOUT_SECONDS"
        ),
        sparql_timeout_seconds=_int_env(
            30, "DALICC_SPARQL_TIMEOUT_SECONDS", "REASONER_SPARQL_TIMEOUT_SECONDS"
        ),
        health_timeout_seconds=_int_env(3, "DALICC_HEALTH_TIMEOUT_SECONDS"),
        log_level=(_first_env("DALICC_LOG_LEVEL") or "INFO").upper(),
    )


@lru_cache(maxsize=1)
def get_settings() -> ReasonerSettings:
    """Return the process-wide settings singleton."""
    return load_settings()
