"""Unit tests for `manage.py init` - the chain config scaffold.

The RPC probe is injected, so this stays offline like the rest of the suite.
"""

import pytest
from click.testing import CliRunner


def _answers(**overrides):
    base = {
        "network_name": "mychain",
        "chain_id": 12345,
        "is_testnet": False,
        "layer": 2,
        "rollup_type": "op_stack",
        "explorer_base_url": "https://explorer.mychain.org",
        "native_currency_symbol": "MYC",
        "native_currency_coingecko_id": "mychain",
        "public_rpc_url": "https://rpc.mychain.org",
        "wrapped_native_token": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "logo_url": "https://example.com/logo.png",
        "reference_token_addresses": {"weth": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "usdc": "", "usdt": ""},
    }
    base.update(overrides)
    return base


def test_scaffold_writes_a_config_that_validates():
    """The whole point: all four onboarding templates were invalid, so a scaffold that can
    emit an invalid file would just reproduce the problem it exists to fix."""
    from scripts.init import render_config, validate_config

    config = validate_config("prod", "mychain", render_config(_answers()))
    assert (config.file_name, config.chain_id, config.rollup_type) == ("mychain", 12345, "op_stack")
    # wrapper is not asked for; the model fills it from wrapped_native_token.
    assert config.wrapper == config.wrapped_native_token


def test_scaffold_refuses_answers_that_do_not_validate():
    from pydantic import ValidationError

    from scripts.init import render_config, validate_config

    text = render_config(_answers(chain_id="not-a-number"))
    with pytest.raises(ValidationError):
        validate_config("prod", "mychain", text)


def test_scaffold_leaves_unknown_tokens_as_visible_placeholders():
    """Empty usdc/usdt must stay obviously unfilled rather than becoming empty strings that
    look deliberate - and the file must still validate, since they are optional."""
    from scripts.init import render_config, validate_config

    text = render_config(_answers())
    assert "usdc:  # fill in for your chain" in text
    assert "usdt:  # fill in for your chain" in text
    config = validate_config("prod", "mychain", text)
    assert config.reference_token_addresses.usdc is None


def test_probe_reads_the_hex_chain_id_and_notices_a_missing_multicall3(monkeypatch):
    from scripts import init as init_module

    def fake_rpc(rpc, method, params, timeout=15):
        return {"eth_chainId": "0x92", "eth_getCode": "0x"}[method]

    monkeypatch.setattr(init_module, "_rpc_call", fake_rpc)
    assert init_module.probe_chain("https://x") == {"chain_id": 146, "multicall3": False}


def test_probe_reports_multicall3_unknown_rather_than_failing_the_scaffold(monkeypatch):
    """chain_id is the valuable answer; losing it because a second call failed is worse."""
    from scripts import init as init_module

    def fake_rpc(rpc, method, params, timeout=15):
        if method == "eth_chainId":
            return "0x1"
        raise OSError("node does not support eth_getCode")

    monkeypatch.setattr(init_module, "_rpc_call", fake_rpc)
    assert init_module.probe_chain("https://x") == {"chain_id": 1, "multicall3": None}


def test_init_command_prompts_through_to_a_valid_file(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from scripts import init as init_module
    from settings.config import get_chain_settings

    monkeypatch.setattr(init_module, "CHAINS_DIR", tmp_path)
    monkeypatch.setattr(init_module, "probe_chain", lambda url, timeout=15: {"chain_id": 146, "multicall3": True})
    answers = "\n".join(
        [
            "Demo",  # network name
            "",  # chain id - accept the probed default
            "n",  # testnet
            "1",  # layer
            "not_rollup",
            "https://explorer.demo/",
            "S",
            "demo-coin",
            "0x039e2fB66102314Ce7b64Ce5Ce3E5183bc94aD38",
            "https://example.com/logo.png",
            "0x50c42dEAcD8Fc9773493ED674b675bE577f2634b",
            "",  # usdc
            "",  # usdt
        ]
    )
    result = CliRunner().invoke(init_module.init_command, ["devnet/demo", "--rpc", "https://x"], input=answers + "\n")
    assert result.exit_code == 0, result.output

    written = tmp_path / "devnet" / "demo.yaml"
    assert "chain_id: 146" in written.read_text(encoding="utf-8")  # the probed default was used
    init_module.validate_config("devnet", "demo", written.read_text(encoding="utf-8"))


def test_init_command_refuses_to_overwrite_without_force(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from scripts import init as init_module

    monkeypatch.setattr(init_module, "CHAINS_DIR", tmp_path)
    (tmp_path / "devnet").mkdir()
    (tmp_path / "devnet" / "demo.yaml").write_text("network_name: existing\n", encoding="utf-8")

    result = CliRunner().invoke(init_module.init_command, ["devnet/demo"])
    assert result.exit_code == 2
    assert "already exists" in result.output
    assert "existing" in (tmp_path / "devnet" / "demo.yaml").read_text(encoding="utf-8")


def test_init_command_rejects_a_chain_without_a_directory():
    from click.testing import CliRunner

    from scripts.init import init_command

    result = CliRunner().invoke(init_command, ["mychain"])
    assert result.exit_code == 2
    assert "must include the directory" in result.output


def test_free_text_answers_survive_the_yaml_round_trip():
    """Plain scalars silently truncated a name at " #", so the file validated and was wrong."""
    from scripts.init import render_config, validate_config

    for field, value in [
        ("network_name", "My Chain #1"),
        ("network_name", "Chain: mainnet"),
        ("network_name", 'Bob\'s "Chain"'),
        ("native_currency_symbol", "NO"),  # YAML 1.1 reads this as False
    ]:
        answers = _answers(**{field: value})
        assert getattr(validate_config("prod", "x", render_config(answers)), field) == value, (field, value)
