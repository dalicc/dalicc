# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Environment-first configuration with the INI file as a fallback."""

from __future__ import annotations

from app.config import get_settings, load_settings


def test_defaults_without_env_or_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DALICC_REASONER_CONFIG", str(tmp_path / "missing.config"))
    monkeypatch.chdir(tmp_path)
    settings = load_settings()
    assert settings.sparql_endpoint == "http://virtuoso-db:8890/sparql"
    assert settings.dependency_graph == "https://dalicc.net/dependencygraph/dg_default"
    assert settings.timeout_seconds == 60
    assert settings.from_graphs == ()


def test_environment_wins_over_the_config_file(monkeypatch, tmp_path) -> None:
    config = tmp_path / "reasoner.config"
    config.write_text("[DEFAULT]\nsparql_endpoint = http://from-file:8890/sparql\n")
    monkeypatch.setenv("DALICC_REASONER_CONFIG", str(config))
    assert load_settings().sparql_endpoint == "http://from-file:8890/sparql"
    monkeypatch.setenv("DALICC_SPARQL_ENDPOINT", "http://from-env:8890/sparql")
    assert load_settings().sparql_endpoint == "http://from-env:8890/sparql"


def test_bare_dependency_graph_name_is_expanded(monkeypatch) -> None:
    monkeypatch.setenv("DALICC_DEPENDENCY_GRAPH", "dg_other")
    assert load_settings().dependency_graph == "https://dalicc.net/dependencygraph/dg_other"


def test_full_dependency_graph_iri_is_kept(monkeypatch) -> None:
    monkeypatch.setenv("DALICC_DEPENDENCY_GRAPH", "https://example.org/dg")
    assert load_settings().dependency_graph == "https://example.org/dg"


def test_graph_restriction_is_opt_in(monkeypatch) -> None:
    """A shared .env sets these; they must not change the query by themselves."""
    monkeypatch.setenv("DALICC_LICENSE_LIBRARY_GRAPH", "https://dalicc.net/licenselibrary/")
    monkeypatch.setenv("DALICC_CUSTOM_LICENSES_GRAPH", "https://dalicc.net/customlicenses/")
    assert load_settings().from_graphs == ()

    monkeypatch.setenv("DALICC_REASONER_RESTRICT_GRAPHS", "true")
    assert load_settings().from_graphs == (
        "https://dalicc.net/licenselibrary/",
        "https://dalicc.net/customlicenses/",
    )


def test_graph_restriction_without_a_library_graph_is_a_no_op(monkeypatch) -> None:
    monkeypatch.setenv("DALICC_REASONER_RESTRICT_GRAPHS", "1")
    assert load_settings().from_graphs == ()


def test_timeout_env_aliases_and_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv("DALICC_REASONER_TIMEOUT_SECONDS", "15")
    assert load_settings().timeout_seconds == 15
    monkeypatch.setenv("REASONER_TIMEOUT_SECONDS", "25")
    assert load_settings().timeout_seconds == 25
    monkeypatch.setenv("REASONER_TIMEOUT_SECONDS", "not-a-number")
    assert load_settings().timeout_seconds == 60
    monkeypatch.setenv("REASONER_TIMEOUT_SECONDS", "0")
    assert load_settings().timeout_seconds == 60


def test_settings_are_cached(monkeypatch) -> None:
    first = get_settings()
    monkeypatch.setenv("DALICC_SPARQL_ENDPOINT", "http://changed:8890/sparql")
    assert get_settings() is first
    get_settings.cache_clear()
    assert get_settings().sparql_endpoint == "http://changed:8890/sparql"
