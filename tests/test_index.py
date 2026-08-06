"""Unit tests for `manage.py index` - the generated registry artifacts.

Offline only. See test_status.py for the shared conventions.
"""

import pytest
from click.testing import CliRunner


def test_index_is_deterministic():
    """--check compares bytes, so any run-to-run variation would fail CI at random."""
    from scripts.index import build_index, render

    assert render(build_index()) == render(build_index())


def test_index_includes_chains_that_fail_validation():
    """avalanche/fantom/x_layer are hand-written catalog rows that pydantic rejects, but they
    are real chains with real addresses. A validation-gated index would drop them silently."""
    from scripts.index import build_index

    ids = {c["id"] for c in build_index()["chains"]}
    assert {"prod/avalanche", "prod/fantom", "prod/x_layer"} <= ids


def test_index_excludes_debug_and_example_files():
    from scripts.index import build_index

    ids = {c["id"] for c in build_index()["chains"]}
    assert not any(i.startswith(("debug/", "examples/")) for i in ids), ids


def test_index_refuses_to_ship_a_missing_chain(tmp_path, monkeypatch):
    """An index that quietly omits a chain is worse than no index."""
    import click

    from scripts import index as index_module

    broken = tmp_path / "deployments" / "prod"
    broken.mkdir(parents=True)
    (broken / "x.yaml").write_text("config:\n  a: null\n    b: 1\n")
    monkeypatch.setattr(index_module, "BASE_DIR", tmp_path)

    with pytest.raises(click.ClickException):
        index_module.build_index()


def test_contract_addresses_skips_empty_and_descends_past_a_node_with_an_address():
    from scripts.index import contract_addresses

    raw = {
        "contracts": {
            "amm": {"stableswap": {"factory": {"address": "0xaaa"}, "implementation": {"address": ""}}},
            "registries": {"metaregistry": {"address": "0xbbb", "handlers": {"one": {"address": "0xccc"}}}},
        }
    }
    found = dict(contract_addresses(raw))
    assert found == {
        "amm.stableswap.factory": "0xaaa",
        "registries.metaregistry": "0xbbb",
        "registries.metaregistry.handlers.one": "0xccc",
    }


def test_index_command_writes_then_reports_itself_current(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from scripts import index as index_module

    monkeypatch.setattr(index_module, "INDEX_PATH", tmp_path / "index.json")
    monkeypatch.setattr(index_module, "SCHEMA_PATH", tmp_path / "schema.json")
    runner = CliRunner()

    assert runner.invoke(index_module.index_command, []).exit_code == 0
    assert (tmp_path / "index.json").exists()
    assert runner.invoke(index_module.index_command, ["--check"]).exit_code == 0

    (tmp_path / "index.json").write_text("{}", encoding="utf-8")
    stale = runner.invoke(index_module.index_command, ["--check"])
    assert stale.exit_code == 1
    assert "out of date" in stale.output
