"""Unit tests for `manage.py deploy all --dry-run`.

Offline: the dry run never opens a connection, which is the property under test.
"""

from click.testing import CliRunner


def test_plan_covers_every_folder_the_deployer_touches():
    """The step list is hand-ordered; this is what stops it drifting from run_deploy_all."""
    from scripts.plan import unknown_folders
    from settings.config import get_chain_settings

    assert unknown_folders(get_chain_settings("prod/sonic.yaml")) == set()


def test_plan_notices_a_folder_missing_from_the_steps(monkeypatch):
    from scripts import plan as plan_module
    from settings.config import get_chain_settings

    monkeypatch.setattr(plan_module, "deployer_folders", lambda: {"helpers/brand_new_thing"})
    assert plan_module.unknown_folders(get_chain_settings("prod/sonic.yaml")) == {"helpers/brand_new_thing"}


def test_plan_reports_the_zero_version_guard_as_blocked():
    """deploy_contract raises rather than redeploying over a live address; the dry run must
    say so instead of promising an upgrade."""
    from scripts.plan import plan_step

    raw = {"contracts": {"helpers": {"router": {"address": "0xabc123def456", "contract_version": "0.0.0"}}}}
    action, detail = plan_step("helpers/router", raw)
    assert action == "BLOCKED"
    assert "0.0.0" in detail


def test_plan_marks_an_undeployed_slot_as_new():
    from scripts.plan import plan_step

    action, detail = plan_step("helpers/router", {})
    assert action == "deploy"
    assert detail.endswith("(new)")


def test_plan_skips_xgov_when_all_three_admins_are_preset():
    """run_deploy_all skips xgov entirely in that case - the plan must agree."""
    from scripts.plan import build_plan
    from settings.config import get_chain_settings

    steps = {s["slot"]: s for s in build_plan(get_chain_settings("prod/sonic.yaml"), {})}
    assert steps["governance/agent"]["action"] == "skip"


def test_dry_run_command_reports_a_plan_and_exits_clean():
    from click.testing import CliRunner

    from scripts.deploy import run_deploy_all

    result = CliRunner().invoke(run_deploy_all, ["prod/sonic.yaml", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "to deploy" in result.output
    assert "plan is out of date" not in result.output


def test_dry_run_command_fails_on_an_invalid_chain_config():
    from click.testing import CliRunner

    from scripts.deploy import run_deploy_all

    result = CliRunner().invoke(run_deploy_all, ["prod/taiko.yaml", "--dry-run"])
    assert result.exit_code == 1
    assert "not a valid chain config" in result.output
