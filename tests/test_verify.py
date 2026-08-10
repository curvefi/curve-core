"""Unit tests for `manage.py verify` - explorer verification payloads.

Offline except the compile test, which is skipped without a local vyper. Getting the payload
wrong wastes a submission and reports a false mismatch, so the shape is pinned here.
"""

from pathlib import Path

import pytest

from settings.config import BASE_DIR


def _row(path, **settings):
    return {
        "contract_path": path,
        "address": "0x" + "11" * 20,
        "deployment_type": "normal",
        "compiler_settings": {"compiler_version": "0.3.10", **settings},
    }


def test_builtin_imports_are_not_shipped():
    """`from vyper.interfaces import ERC20` is the compiler's own. Supplying a file for it
    would shadow the builtin and change what gets built."""
    from scripts.verify import collect_sources

    source = BASE_DIR / "contracts/amm/stableswap/views/views_v_120.vy"
    keys = collect_sources(source)
    assert "vyper" not in " ".join(keys).lower().replace("vyper-", "")
    assert list(keys) == ["contracts/amm/stableswap/views/views_v_120.vy"]


def test_repo_modules_travel_with_the_source():
    """`import contracts.governance.relayer.relayer_v_100 as Relayer` is in this repo, so the
    explorer never sees it unless it is in the payload."""
    from scripts.verify import collect_sources

    source = BASE_DIR / "contracts/governance/relayer/taiko/relayer_v_001.vy"
    if not source.exists():
        pytest.skip("relayer moved")
    keys = collect_sources(source)

    assert "contracts/governance/agent/agent_v_101.vy" in keys, keys
    assert all(Path(BASE_DIR / key).exists() for key in keys)


def test_the_payload_never_states_an_optimise_mode():
    """The regression this locks: sending optimize=gas made vyper reject every contract whose
    source says `# pragma optimize codesize` - 36 recorded rows."""
    from scripts.verify import standard_json

    row = _row("/contracts/amm/stableswap/implementation/implementation_v_700.vy", optimisation_level="CODESIZE")
    assert "optimize" not in standard_json(row)["settings"]


def test_the_payload_asks_for_every_output():
    """Asking only for the bytecode we use locally made Etherscan answer "unable to get
    compiled bytecode" - it reads the abi out of the same compile."""
    from scripts.verify import standard_json

    row = _row("/contracts/amm/stableswap/math/math_v_100.vy")
    assert standard_json(row)["settings"]["outputSelection"] == {"*": ["*"]}


def test_evm_version_is_passed_through_when_recorded():
    from scripts.verify import standard_json

    row = _row("/contracts/amm/stableswap/views/views_v_120.vy", evm_version="shanghai")
    assert standard_json(row)["settings"]["evmVersion"] == "shanghai"
    assert "evmVersion" not in standard_json(_row("/contracts/amm/stableswap/views/views_v_120.vy"))["settings"]


@pytest.mark.parametrize(
    "level, used",
    [("GAS", True), ("gas", True), ("CODESIZE", True), ("codesize", True), ("NONE", False), ("UNKNOWN", True)],
)
def test_optimisation_is_read_in_every_spelling_the_fleet_uses(level, used):
    """Seven spellings across the deployment files, including UNKNOWN and null."""
    from scripts.verify import optimised

    assert optimised(_row("/x.vy", optimisation_level=level), "# nothing") is used


def test_a_source_pragma_beats_the_recorded_level():
    """Vyper rejects a setting that contradicts the pragma, so the pragma is the authority."""
    from scripts.verify import optimised

    assert optimised(_row("/x.vy", optimisation_level="GAS"), "# pragma optimize none\n") is False


def test_blueprints_are_skipped_not_attempted():
    """A blueprint holds initcode on chain; no explorer verifies that against a source."""
    from scripts.verify import plan_row

    row = _row("/contracts/amm/stableswap/views/views_v_120.vy")
    row["deployment_type"] = "blueprint"
    action, detail = plan_row("amm.x", row, 146, {146})
    assert action == "skip" and "blueprint" in detail


@pytest.mark.parametrize(
    "mutate, action",
    [
        (lambda r: r.pop("contract_path"), "skip"),
        (lambda r: r.update(contract_path="/contracts/gone_v_100.vy"), "blocked"),
        (lambda r: r["compiler_settings"].pop("compiler_version"), "blocked"),
    ],
)
def test_rows_that_cannot_be_verified_say_why(mutate, action):
    from scripts.verify import plan_row

    row = _row("/contracts/amm/stableswap/views/views_v_120.vy")
    mutate(row)
    assert plan_row("amm.x", row, 146, {146})[0] == action


def test_an_unsupported_chain_is_blocked_not_submitted():
    """ink, etherlink, x_layer and plume are not on the Etherscan v2 chainlist."""
    from scripts.verify import plan_row

    row = _row("/contracts/amm/stableswap/views/views_v_120.vy")
    action, detail = plan_row("amm.x", row, 57073, {1, 146})
    assert action == "blocked" and "57073" in detail


@pytest.mark.parametrize(
    "answer, verdict",
    [
        # The three replies a real run across 24 chains actually produced.
        ("Pass - Verified", "verified"),
        ("Contract source code already verified", "already"),
        ("Already Verified", "already"),
        ("Unable to locate ContractCode at 0xabc", "failed"),
        ("Fail - Unable to verify. Unable to locate a matching contract", "failed"),
        ("", "failed"),
    ],
)
def test_the_explorers_reply_is_read_not_assumed(answer, verdict):
    from scripts.verify import outcome

    assert outcome(answer) == verdict


def test_a_chain_that_verified_nothing_exits_non_zero(monkeypatch):
    """devnet/monad failed all 21 submissions and the run still exited 0, because accepting
    the request was being counted as success."""
    from click.testing import CliRunner

    from scripts import verify as verify_module

    monkeypatch.setattr(verify_module, "etherscan_chains", lambda: {146})
    monkeypatch.setattr(verify_module, "THROTTLE", 0)
    monkeypatch.setattr(verify_module.settings, "ETHERSCAN_API_KEY", "key")
    monkeypatch.setattr(verify_module, "submit", lambda *a: (False, "Unable to locate ContractCode at 0xabc"))

    result = CliRunner().invoke(verify_module.verify_command, ["prod/sonic", "--submit"])
    assert result.exit_code == 1, result.output
    assert "failed" in result.output


def test_a_chain_that_was_already_verified_exits_zero(monkeypatch):
    from click.testing import CliRunner

    from scripts import verify as verify_module

    monkeypatch.setattr(verify_module, "etherscan_chains", lambda: {146})
    monkeypatch.setattr(verify_module, "THROTTLE", 0)
    monkeypatch.setattr(verify_module.settings, "ETHERSCAN_API_KEY", "key")
    monkeypatch.setattr(verify_module, "submit", lambda *a: (False, "Contract source code already verified"))

    result = CliRunner().invoke(verify_module.verify_command, ["prod/sonic", "--submit"])
    assert result.exit_code == 0, result.output
    assert "already" in result.output


def test_submitting_without_a_key_fails_before_any_request(monkeypatch):
    """Both sources have to be empty - settings/env is the other one, and a developer who has
    it set would otherwise never see this path."""
    from click.testing import CliRunner

    from scripts import verify as verify_module

    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    monkeypatch.setattr(verify_module.settings, "ETHERSCAN_API_KEY", "")
    result = CliRunner().invoke(verify_module.verify_command, ["prod/sonic", "--submit"])

    assert result.exit_code == 1
    assert "ETHERSCAN_API_KEY" in result.output


@pytest.mark.parametrize(
    "path",
    [
        "contracts/amm/stableswap/implementation/implementation_v_700.vy",  # pragma codesize
        "contracts/governance/relayer/op_stack/relayer_v_101.vy",  # repo-relative import
        "contracts/helpers/router/router_v_110.vy",
    ],
)
def test_the_payload_builds_what_the_deployer_builds(path):
    """The point of the whole command: an explorer compiling this payload must land on the
    same runtime bytecode the deployer produced, or verification fails on a real contract."""
    vvm = pytest.importorskip("vvm")
    if not (Path.home() / ".vvm").exists():
        pytest.skip("no local vyper compilers")

    from scripts.verify import source_path, standard_json

    row = _row("/" + path, evm_version="shanghai")
    if not source_path(row).exists():
        pytest.skip(f"{path} moved")

    built = vvm.compile_standard(standard_json(row), vyper_version="0.3.10")
    runtime = next(iter(next(iter(built["contracts"].values())).values()))["evm"]["deployedBytecode"]["object"]
    direct = vvm.compile_source(
        source_path(row).read_text(encoding="utf-8"), vyper_version="0.3.10", evm_version="shanghai"
    )
    assert runtime.lstrip("0x") == next(iter(direct.values()))["bytecode_runtime"].lstrip("0x")
