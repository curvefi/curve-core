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
    action, detail = plan_row("amm.x", row, 146, ("etherscan", None))
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
    assert plan_row("amm.x", row, 146, ("etherscan", None))[0] == action


def test_a_chain_with_neither_explorer_is_blocked_not_submitted():
    from scripts.verify import plan_row

    row = _row("/contracts/amm/stableswap/views/views_v_120.vy")
    action, detail = plan_row("amm.x", row, 57073, None)
    assert action == "blocked" and "57073" in detail


def test_a_blockscout_chain_is_planned_not_blocked():
    """ink, etherlink, plume and 9 others are off the Etherscan chainlist but are Blockscout,
    which takes the same standard json and needs no key."""
    from scripts.verify import plan_row

    row = _row("/contracts/amm/stableswap/views/views_v_120.vy")
    action, detail = plan_row("amm.x", row, 57073, ("blockscout", "https://explorer.inkonchain.com"))
    assert action == "verify" and detail.startswith("blockscout")


def test_etherscan_wins_when_a_chain_is_on_both(monkeypatch):
    """Blockscout is the fallback for chains Etherscan does not list, not a competing choice -
    so a chain on the chainlist must never be probed for Blockscout."""
    from scripts import verify as verify_module

    monkeypatch.setattr(verify_module, "etherscan_chains", lambda: {146})
    monkeypatch.setattr(verify_module, "blockscout_base", lambda config: pytest.fail("should not probe Blockscout"))
    assert verify_module.resolve_route(146, {"explorer_base_url": "https://x"}) == ("etherscan", None)


def test_the_blockscout_compiler_string_is_looked_up_not_guessed(monkeypatch):
    """It wants v0.3.10+commit.91361694; the deployment file records 0.3.10, and the commit
    hash differs per release - a wrong one fails the build with no useful message."""
    from scripts import verify as verify_module

    offered = ["v0.4.3+commit.bff19ea2", "v0.3.10+commit.91361694", "v0.3.10-rc5+commit.42817806"]
    monkeypatch.setattr(verify_module, "_json", lambda *a, **k: {"vyper_compiler_versions": offered})

    assert verify_module.blockscout_compiler("https://x", "0.3.10") == "v0.3.10+commit.91361694"
    assert verify_module.blockscout_compiler("https://x", "0.2.99") is None


def test_a_non_blockscout_explorer_is_not_mistaken_for_one(monkeypatch):
    from scripts import verify as verify_module

    def refuse(*args, **kwargs):
        raise OSError("404")

    monkeypatch.setattr(verify_module, "_json", refuse)
    assert verify_module.blockscout_base({"explorer_base_url": "https://not-blockscout.example"}) is None
    assert verify_module.blockscout_base({}) is None


def test_an_empty_backend_version_still_counts_as_blockscout(monkeypatch):
    """An instance reporting a blank version is still Blockscout. Explorers that serve an HTML
    SPA at this path are not, and fail the JSON parse rather than reaching this check."""
    from scripts import verify as verify_module

    monkeypatch.setattr(verify_module, "_json", lambda *a, **k: {"backend_version": ""})
    assert verify_module.blockscout_base({"explorer_base_url": "https://x"}) == "https://x"

    monkeypatch.setattr(verify_module, "_json", lambda *a, **k: {"something_else": 1})
    assert verify_module.blockscout_base({"explorer_base_url": "https://x"}) is None


def test_an_already_verified_contract_is_not_resubmitted(monkeypatch):
    """tac answers a re-submission with a bare 404, which read as a broken route - all 21 of
    its already-verified contracts were reported as failures."""
    from click.testing import CliRunner

    from scripts import verify as verify_module

    monkeypatch.setattr(verify_module, "etherscan_chains", lambda: set())
    monkeypatch.setattr(verify_module, "blockscout_base", lambda config: "https://explorer.example")
    monkeypatch.setattr(verify_module, "blockscout_verified", lambda address, base: True)
    monkeypatch.setattr(verify_module, "THROTTLE", 0)
    monkeypatch.setattr(
        verify_module, "submit_blockscout", lambda *a: pytest.fail("should not submit an already-verified contract")
    )

    result = CliRunner().invoke(verify_module.verify_command, ["prod/tac", "--submit"])
    assert result.exit_code == 0, result.output
    assert "already" in result.output


def test_an_unreachable_explorer_does_not_read_as_verified(monkeypatch):
    """The check must fail closed - a timeout that reported "already verified" would silently
    skip every contract on the chain."""
    from scripts import verify as verify_module

    def refuse(*args, **kwargs):
        raise OSError("timeout")

    monkeypatch.setattr(verify_module, "_json", refuse)
    assert verify_module.blockscout_verified("0xabc", "https://x") is False


def test_the_multipart_body_carries_the_json_as_a_file():
    from scripts.verify import _multipart

    content_type, body = _multipart({"compiler_version": "v0.3.10+commit.91361694"}, "x.vy", '{"language":"Vyper"}')
    text = body.decode()

    assert "multipart/form-data; boundary=" in content_type
    assert 'name="compiler_version"' in text and "v0.3.10+commit.91361694" in text
    assert 'name="files[0]"; filename="x.vy"' in text
    assert '{"language":"Vyper"}' in text
    assert text.rstrip().endswith("--")  # closing boundary, or the server rejects the body


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
