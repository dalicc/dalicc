# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Liveness / readiness probes for the reasoner service.

``GET /healthz`` reports two things:

``hexlite``
    Whether the solver binary is present and executable.  The probe runs
    ``hexlite --help`` **once at startup** and caches the result, so the
    endpoint stays cheap enough for a container ``HEALTHCHECK``.
``sparql``
    Whether the configured SPARQL endpoint answers.  This is a *soft*
    dependency: Virtuoso may still be starting up while the reasoner is
    already able to serve, so an unreachable store makes the service
    ``degraded`` (HTTP 200) rather than unhealthy.  Only a broken solver makes
    ``/healthz`` return 503.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from .config import get_settings
from .solver import hexlite_binary

__all__ = ["HEALTH_DEGRADED", "HEALTH_OK", "check_health", "probe_hexlite", "reset_hexlite_probe"]

logger = logging.getLogger(__name__)

HEALTH_OK = "ok"
HEALTH_DEGRADED = "degraded"

_HEXLITE_PROBE: dict[str, Any] | None = None


def reset_hexlite_probe() -> None:
    """Forget the cached solver probe (used by tests and by the startup hook)."""
    global _HEXLITE_PROBE
    _HEXLITE_PROBE = None


def probe_hexlite(*, refresh: bool = False, timeout_seconds: int = 15) -> dict[str, Any]:
    """Return ``{"ok": bool, "binary": str, "detail": str}`` for the solver."""
    global _HEXLITE_PROBE
    if _HEXLITE_PROBE is not None and not refresh:
        return _HEXLITE_PROBE

    binary = hexlite_binary()
    result: dict[str, Any]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [binary, "--help"],
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        result = {"ok": False, "binary": binary, "detail": "executable not found"}
    except subprocess.TimeoutExpired:
        result = {
            "ok": False,
            "binary": binary,
            "detail": f"--help timed out after {timeout_seconds}s",
        }
    except OSError as exc:
        result = {"ok": False, "binary": binary, "detail": f"could not execute: {exc}"}
    else:
        # hexlite's argparse wrapper exits with status 1 after printing its
        # usage banner, so the banner -- not the exit status -- is the signal
        # that the solver is installed and importable.
        banner = completed.stdout.decode("utf-8", "replace")
        ok = completed.returncode == 0 or "usage: hexlite" in banner
        detail = "ok" if ok else f"--help exited with status {completed.returncode}"
        result = {"ok": ok, "binary": binary, "detail": detail}

    if not result["ok"]:
        logger.error("solver probe failed: %s", result["detail"])
    _HEXLITE_PROBE = result
    return result


def probe_sparql(timeout_seconds: int | None = None) -> dict[str, Any]:
    """Return ``{"ok": bool, "endpoint": str, "detail": str}`` for the store."""
    import requests

    settings = get_settings()
    timeout = timeout_seconds if timeout_seconds is not None else settings.health_timeout_seconds
    endpoint = settings.sparql_endpoint
    try:
        response = requests.get(
            endpoint,
            params={"query": "ASK {}", "format": "application/sparql-results+json"},
            timeout=timeout,
            headers={"Accept": "application/sparql-results+json"},
        )
    except requests.RequestException as exc:
        logger.warning("SPARQL endpoint %s unreachable: %s", endpoint, exc)
        return {
            "ok": False,
            "endpoint": endpoint,
            "detail": f"unreachable: {exc.__class__.__name__}",
        }
    ok = response.status_code < 500
    return {
        "ok": ok,
        "endpoint": endpoint,
        "detail": f"HTTP {response.status_code}",
    }


def check_health() -> tuple[dict[str, Any], int]:
    """Return the ``/healthz`` payload and the HTTP status code to use."""
    hexlite = probe_hexlite()
    sparql = probe_sparql()
    healthy = bool(hexlite["ok"])
    status = HEALTH_OK if healthy and sparql["ok"] else HEALTH_DEGRADED
    payload = {
        "status": status,
        "service": "dalicc-reasoner",
        "hexlite": hexlite,
        "sparql": sparql,
    }
    return payload, (200 if healthy else 503)
