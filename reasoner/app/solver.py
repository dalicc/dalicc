# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Invocation of the ``hexlite`` answer-set solver.

Responsibilities:

* build the caller-specific logic program in a **per-request** temporary
  directory (the old code wrote every request to the same
  ``./app/programs/temp/test_user.lp``, so two concurrent compatibility checks
  answered each other's question);
* resolve every path relative to this module instead of the process CWD;
* run the solver with a wall-clock timeout, capture *and log* stderr, and map
  failures onto :class:`SolverTimeoutError` / :class:`SolverFailureError` so the routers
  can answer 504 / 502 instead of leaking a traceback;
* always clean the temporary directory up.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from .config import get_settings, package_root, service_root
from .iri import encode_license_token, validate_dependency_graph_iri

__all__ = [
    "SolverError",
    "SolverFailureError",
    "SolverResult",
    "SolverTimeoutError",
    "build_user_program",
    "dependency_graph_override",
    "dependency_graph_program",
    "hexlite_binary",
    "run_compatibility",
    "run_dependency_graph",
]

logger = logging.getLogger(__name__)

#: How much of stderr is echoed back to the client in a 502 body.
STDERR_TAIL_CHARS = 600


class SolverError(RuntimeError):
    """Base class for solver invocation problems."""


class SolverTimeoutError(SolverError):
    """The solver exceeded its wall-clock budget."""

    def __init__(self, timeout_seconds: float) -> None:
        """Record the *timeout_seconds* budget that was exceeded."""
        super().__init__(f"reasoner timed out after {timeout_seconds}s")
        self.timeout_seconds = timeout_seconds


class SolverFailureError(SolverError):
    """The solver exited non-zero or could not be started."""

    def __init__(self, message: str, *, returncode: int | None = None, stderr: str = "") -> None:
        """Record the solver *returncode* and its *stderr* alongside *message*."""
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr

    @property
    def stderr_tail(self) -> str:
        """The last :data:`STDERR_TAIL_CHARS` characters of stderr, trimmed."""
        tail = self.stderr.strip()
        if len(tail) > STDERR_TAIL_CHARS:
            tail = "..." + tail[-STDERR_TAIL_CHARS:]
        return tail


class SolverResult(Sequence[str]):
    """Solver stdout plus the stderr that came with it."""

    def __init__(self, stdout: str, stderr: str) -> None:
        """Store the decoded *stdout* and *stderr* of one solver run."""
        self.stdout = stdout
        self.stderr = stderr

    def __getitem__(self, item: int) -> str:  # pragma: no cover - convenience only
        """Return ``stdout`` for index 0 and ``stderr`` for index 1."""
        return (self.stdout, self.stderr)[item]

    def __len__(self) -> int:  # pragma: no cover - convenience only
        """Return 2 -- ``(stdout, stderr)``."""
        return 2


def hexlite_binary() -> str:
    """Return the ``hexlite`` executable to invoke (``REASONER_HEXLITE_BIN``)."""
    return os.environ.get("REASONER_HEXLITE_BIN") or "hexlite"


def programs_dir() -> Path:
    """Directory holding the ``.lp`` logic programs, resolved module-relative."""
    return package_root() / "programs"


def plugins_dir() -> Path:
    """Directory holding the hexlite Python plugin, resolved module-relative."""
    return package_root() / "plugins"


def build_user_program(licenses: Iterable[str]) -> str:
    """Return the ASP facts for *licenses*.

    Each licence IRI is hex-encoded (:func:`~app.iri.encode_license_token`), so
    the generated program only ever contains ``[0-9a-f]`` inside the string
    literal.  ``plugins.getLicense`` decodes and re-validates the token before
    building its SPARQL query.
    """
    lines = [
        "% generated per request by the DALICC reasoner -- do not edit",
        "% license/1 arguments are hex-encoded IRIs, decoded by plugins.getLicense",
    ]
    for iri in licenses:
        lines.append(f'license("{encode_license_token(iri)}").')
    return "\n".join(lines) + "\n"


def _subprocess_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environment for the solver subprocess.

    ``PYTHONPATH`` gains the service root so the hexlite plugin -- which is
    imported as a *top-level* module from ``--pluginpath`` -- can still import
    ``app.config`` / ``app.iri`` for its configuration and IRI validation.

    ``overrides`` are per-request settings for that one solver run.  The plugin
    runs in its own process and builds its own ``ReasonerSettings`` there, so an
    environment variable set for the subprocess is the whole of the override
    mechanism: nothing in this process is mutated, and two concurrent requests
    cannot see each other's choice.
    """
    env = dict(os.environ)
    root = str(service_root())
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{root}{os.pathsep}{existing}" if existing else root
    if overrides:
        env.update(overrides)
    return env


def _run(
    program_files: Sequence[Path],
    *,
    timeout_seconds: int,
    cwd: Path,
    env_overrides: Mapping[str, str] | None = None,
) -> SolverResult:
    command = [
        hexlite_binary(),
        *(str(path) for path in program_files),
        "--pluginpath",
        str(plugins_dir()),
        "--plugin",
        "plugins",
    ]
    logger.info("running solver: %s", " ".join(command))
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            capture_output=True,
            timeout=timeout_seconds,
            cwd=str(cwd),
            env=_subprocess_env(env_overrides),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = _decode(exc.stderr)
        if stderr:
            logger.warning("solver stderr before timeout: %s", stderr.strip())
        logger.error("solver timed out after %ss", timeout_seconds)
        raise SolverTimeoutError(timeout_seconds) from exc
    except FileNotFoundError as exc:
        logger.error("solver executable %r not found", hexlite_binary())
        raise SolverFailureError(f"solver executable {hexlite_binary()!r} not found") from exc
    except OSError as exc:
        logger.error("could not start solver: %s", exc)
        raise SolverFailureError(f"could not start solver: {exc}") from exc

    stdout = _decode(completed.stdout)
    stderr = _decode(completed.stderr)
    if stderr.strip():
        # hexlite always emits "cannot parse external atom term" warnings for
        # IRIs, so this is information rather than an error unless rc != 0.
        logger.log(
            logging.ERROR if completed.returncode != 0 else logging.DEBUG,
            "solver stderr: %s",
            stderr.strip(),
        )
    if completed.returncode != 0:
        raise SolverFailureError(
            f"solver exited with status {completed.returncode}",
            returncode=completed.returncode,
            stderr=stderr,
        )
    return SolverResult(stdout, stderr)


def _decode(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return raw.decode("utf-8", errors="replace")


def dependency_graph_override(dependency_graph: str | None) -> dict[str, str]:
    """The environment a per-request dependency graph needs, or an empty mapping.

    ``DALICC_DEPENDENCY_GRAPH`` is what the hexlite plugin reads to decide which
    named graph ``&getDependencyGraph`` dumps, so setting it for that one
    subprocess is how a request chooses a graph without touching this process.
    The IRI is validated first and has to sit in one of the two DALICC graph
    spaces, so a caller can never aim the solver at an arbitrary named graph.
    """
    if not dependency_graph:
        return {}
    return {"DALICC_DEPENDENCY_GRAPH": validate_dependency_graph_iri(dependency_graph)}


def run_compatibility(
    licenses: Sequence[str],
    *,
    timeout_seconds: float | None = None,
    dependency_graph: str | None = None,
) -> SolverResult:
    """Run ``query.lp`` for *licenses* in a private temporary directory.

    ``dependency_graph`` overrides the configured graph for this one run.
    """
    settings = get_settings()
    timeout = timeout_seconds if timeout_seconds is not None else settings.timeout_seconds
    overrides = dependency_graph_override(dependency_graph)
    workdir = Path(tempfile.mkdtemp(prefix="dalicc-reasoner-"))
    try:
        user_program = workdir / "user.lp"
        user_program.write_text(build_user_program(licenses), encoding="utf-8")
        return _run(
            [user_program, programs_dir() / "query.lp"],
            timeout_seconds=timeout,
            cwd=workdir,
            env_overrides=overrides,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_dependency_graph(
    *, timeout_seconds: float | None = None, dependency_graph: str | None = None
) -> SolverResult:
    """Run ``getdepgraph.lp``, which needs no caller-supplied input at all.

    ``dependency_graph`` computes the closure of a graph other than the configured
    one, validated exactly as in :func:`run_compatibility`.
    """
    settings = get_settings()
    timeout = timeout_seconds if timeout_seconds is not None else settings.timeout_seconds
    workdir = Path(tempfile.mkdtemp(prefix="dalicc-reasoner-"))
    try:
        return _run(
            [dependency_graph_program()],
            timeout_seconds=timeout,
            cwd=workdir,
            env_overrides=dependency_graph_override(dependency_graph),
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def dependency_graph_program() -> Path:
    """Path of the dependency-graph closure program."""
    return programs_dir() / "getdepgraph.lp"
