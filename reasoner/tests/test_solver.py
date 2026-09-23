# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Solver invocation: per-request temp files, timeouts and error mapping."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from app import solver
from app.config import get_settings
from app.solver import (
    SolverFailureError,
    SolverTimeoutError,
    build_user_program,
    programs_dir,
    run_compatibility,
    run_dependency_graph,
)


class _Completed:
    def __init__(self, returncode: int = 0, stdout: bytes = b"{}\n", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_user_program_uses_hex_tokens_only() -> None:
    program = build_user_program(
        ["https://dalicc.net/licenselibrary/MIT", "https://dalicc.net/licenselibrary/Apache-2.0"]
    )
    facts = [line for line in program.splitlines() if line.startswith("license(")]
    assert len(facts) == 2
    for fact in facts:
        token = fact[len('license("') : -len('").')]
        assert all(c in "0123456789abcdef" for c in token)
    assert "dalicc.net" not in program.replace("% ", "")


def test_programs_are_resolved_relative_to_the_module_not_the_cwd(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert programs_dir().is_dir()
    assert (programs_dir() / "query.lp").is_file()
    assert (programs_dir() / "getdepgraph.lp").is_file()


def test_each_request_gets_its_own_temp_directory(monkeypatch) -> None:
    seen: list[Path] = []

    def fake_run(command, **kwargs):
        cwd = Path(kwargs["cwd"])
        seen.append(cwd)
        user_program = Path(command[1])
        assert user_program.parent == cwd
        assert user_program.read_text().count("license(") == 1
        return _Completed()

    monkeypatch.setattr(solver.subprocess, "run", fake_run)
    run_compatibility(["https://dalicc.net/licenselibrary/MIT"])
    run_compatibility(["https://dalicc.net/licenselibrary/Apache-2.0"])

    assert len(seen) == 2
    assert seen[0] != seen[1], "concurrent requests must not share a program file"
    for path in seen:
        assert not path.exists(), "temporary directory must be removed"


def test_temp_directory_is_removed_even_on_failure(monkeypatch) -> None:
    seen: list[Path] = []

    def fake_run(command, **kwargs):
        seen.append(Path(kwargs["cwd"]))
        return _Completed(returncode=1, stdout=b"", stderr=b"boom")

    monkeypatch.setattr(solver.subprocess, "run", fake_run)
    with pytest.raises(SolverFailureError):
        run_compatibility(["https://dalicc.net/licenselibrary/MIT"])
    assert not seen[0].exists()


def test_subprocess_env_exposes_the_package_to_the_plugin(monkeypatch) -> None:
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return _Completed()

    monkeypatch.setattr(solver.subprocess, "run", fake_run)
    run_compatibility([])
    pythonpath = captured["env"]["PYTHONPATH"].split(os.pathsep)
    assert str(Path(__file__).resolve().parents[1]) in pythonpath


def test_timeout_is_passed_and_mapped(monkeypatch) -> None:
    monkeypatch.setenv("REASONER_TIMEOUT_SECONDS", "7")
    get_settings.cache_clear()
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        raise subprocess.TimeoutExpired(cmd=command, timeout=7, stderr=b"partial stderr")

    monkeypatch.setattr(solver.subprocess, "run", fake_run)
    with pytest.raises(SolverTimeoutError) as excinfo:
        run_compatibility(["https://dalicc.net/licenselibrary/MIT"])
    assert captured["timeout"] == 7
    assert excinfo.value.timeout_seconds == 7


def test_default_timeout_is_sixty_seconds(monkeypatch) -> None:
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return _Completed()

    monkeypatch.setattr(solver.subprocess, "run", fake_run)
    run_compatibility([])
    assert captured["timeout"] == 60


def test_non_zero_exit_becomes_solver_failure_with_stderr(monkeypatch) -> None:
    stderr = b"Traceback...\nurllib.error.URLError: <urlopen error name resolution>\n"

    monkeypatch.setattr(
        solver.subprocess, "run", lambda command, **kw: _Completed(1, b"", stderr)
    )
    with pytest.raises(SolverFailureError) as excinfo:
        run_compatibility(["https://dalicc.net/licenselibrary/MIT"])
    assert excinfo.value.returncode == 1
    assert "URLError" in excinfo.value.stderr_tail


def test_stderr_tail_is_truncated(monkeypatch) -> None:
    monkeypatch.setattr(
        solver.subprocess, "run", lambda command, **kw: _Completed(1, b"", b"x" * 5000)
    )
    with pytest.raises(SolverFailureError) as excinfo:
        run_compatibility([])
    assert len(excinfo.value.stderr_tail) <= solver.STDERR_TAIL_CHARS + 3


def test_missing_binary_becomes_solver_failure(monkeypatch) -> None:
    def fake_run(command, **kwargs):
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(solver.subprocess, "run", fake_run)
    with pytest.raises(SolverFailureError, match="not found"):
        run_compatibility([])


def test_dependency_graph_runs_only_the_closure_program(monkeypatch) -> None:
    captured: list = []

    def fake_run(command, **kwargs):
        captured.append(command)
        return _Completed(stdout=b"{}\n")

    monkeypatch.setattr(solver.subprocess, "run", fake_run)
    result = run_dependency_graph()
    assert result.stdout == "{}\n"
    assert captured[0][1].endswith("getdepgraph.lp")
    assert "--plugin" in captured[0]


def test_hexlite_binary_is_overridable(monkeypatch) -> None:
    monkeypatch.setenv("REASONER_HEXLITE_BIN", "/opt/hexlite")
    assert solver.hexlite_binary() == "/opt/hexlite"


def test_the_query_program_reasons_over_every_relation_the_graph_uses() -> None:
    """``query.lp`` must read all four dependency-graph relations, and no dead rule.

    ``dalicc:contradicts`` sat in the program as an unused constant while the graph
    carried an axiom that used it, so the one contradiction the library states was
    never reported.  ``sameAs(X,X,...) :- action(X)`` was the opposite: a rule over a
    predicate no rule ever derives, which the solver reported as a warning on every
    single run.
    """
    program = (programs_dir() / "query.lp").read_text(encoding="utf-8")
    for relation in ("sameAs", "implies", "includedIn", "contradicts"):
        assert f'{relation}(X,Y,"dependencygraph") :- dg(' in program, relation
    assert '"contradicts",X,Y,R' in program, "no conflict is derived from contradicts"
    assert "action(X)" not in program
