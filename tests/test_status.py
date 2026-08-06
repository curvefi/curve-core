"""Unit tests for `manage.py status`.

Each case is a regression test for a bug that shipped; the comment names the failure it
locks down. Offline only - no network, so the suite is deterministic in CI.
"""

import io
import urllib.error
from collections import Counter

import pytest
from rich.console import Console

from scripts.deploy.utils import fetch_latest_contract, normalise_version, version_a_gt_version_b
from scripts.status import (
    Finding,
    RpcError,
    _dominant,
    _error_label,
    _undeclared,
    check_pending,
    check_wiring,
    contract_rows,
    emit,
    plural,
)

# --------------------------------------------------------------------------------------
# version handling
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("3.0.0", "3.0.0"),
        ("v3.0.0", "3.0.0"),  # upstream twocrypto-ng's own convention
        ("V3.0.0", "3.0.0"),
        (" v3.0.0 ", "3.0.0"),
        # `lstrip("vV")` ate every leading v and mangled anything merely starting with one,
        # silently turning a malformed version into a plausible-looking one.
        ("volatile", "volatile"),
        ("vv1.0.0", "vv1.0.0"),
        ("Verified1", "Verified1"),
    ],
)
def test_normalise_version_strips_one_v_only_before_a_digit(raw, expected):
    assert normalise_version(raw) == expected


def test_version_compare_accepts_the_v_prefix():
    # The crash this prevents: a "v3.0.0" contract made version_a_gt_version_b raise
    # mid-deploy on int("v3").
    assert version_a_gt_version_b("v3.0.0", "2.1.0") is True
    assert version_a_gt_version_b("3.0.0", "v2.1.0") is True
    assert version_a_gt_version_b("v2.1.0", "v2.1.0") is False


def test_version_compare_still_raises_on_genuinely_malformed():
    # PENDING relies on this raising so it can report the chain as unprocessable rather than
    # silently skipping it.
    with pytest.raises(ValueError):
        version_a_gt_version_b("1.0.0rc1", "1.0.0")


# --------------------------------------------------------------------------------------
# contract resolution
# --------------------------------------------------------------------------------------


def test_fetch_latest_contract_sorts_on_digits_across_unrelated_contracts(tmp_path):
    """Two contracts in one folder compete on a number that means nothing across them."""
    (tmp_path / "math_v_210.vy").write_text("# a")
    (tmp_path / "stableswap_math_v_011.vy").write_text("# b")
    assert fetch_latest_contract(tmp_path).name == "math_v_210.vy"

    # A newer version of the *other* contract silently takes the slot.
    (tmp_path / "stableswap_math_v_300.vy").write_text("# c")
    assert fetch_latest_contract(tmp_path).name == "stableswap_math_v_300.vy"


def test_fetch_latest_contract_ignores_files_without_v_nnn(tmp_path):
    (tmp_path / "twocrypto_view.vy").write_text("# unreachable")
    with pytest.raises(FileNotFoundError):
        fetch_latest_contract(tmp_path)


# --------------------------------------------------------------------------------------
# walking deployment files
# --------------------------------------------------------------------------------------


def test_contract_rows_descends_past_a_node_that_has_an_address():
    """An early `return` here hid every nested row - 72 across the fleet."""
    raw = {
        "contracts": {
            "registries": {
                "metaregistry": {
                    "address": "0xaaa",
                    "registry_handlers": {
                        "stableswap": {"address": "0xbbb"},
                        "twocrypto": {"address": "0xccc"},
                    },
                }
            }
        }
    }
    slots = dict(contract_rows(raw))
    assert "registries.metaregistry" in slots
    assert "registries.metaregistry.registry_handlers.stableswap" in slots
    assert "registries.metaregistry.registry_handlers.twocrypto" in slots


def test_contract_rows_tolerates_non_dict_nodes():
    raw = {"contracts": {"amm": {"stableswap": None, "twocrypto": ["not", "a", "dict"]}}}
    assert list(contract_rows(raw)) == []


# --------------------------------------------------------------------------------------
# RPC failure classification
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc, expected",
    [
        # HTTP 429 and 503 are both HTTPError; only the code says whether re-running helps.
        (urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None), "HTTP 429"),
        (urllib.error.HTTPError("u", 503, "Unavailable", {}, None), "HTTP 503"),
        (urllib.error.URLError(TimeoutError("timed out")), "timeout"),
        (TimeoutError("timed out"), "timeout"),
    ],
)
def test_error_label_keeps_the_actionable_part(exc, expected):
    assert _error_label(exc) == expected


def test_error_label_marks_dns_failure_as_unreachable():
    # A URL that does not resolve is never fixed by waiting - it must not read as a rate limit.
    label = _error_label(urllib.error.URLError(OSError("Name or service not known")))
    assert label.startswith("unreachable")


def test_error_label_keeps_the_nodes_own_message_for_in_band_errors():
    assert _error_label(RpcError("rate limit exceeded")).startswith("RPC error:")


def test_dominant_names_the_most_common_and_counts_the_rest():
    assert _dominant(Counter({"HTTP 429": 24})) == "HTTP 429"
    assert _dominant(Counter({"HTTP 429": 24, "timeout": 3, "HTTP 503": 1})) == "HTTP 429 and 2 other kinds"
    assert _dominant(Counter()) == ""


# --------------------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------------------


def render(text, **kwargs):
    console = Console(file=io.StringIO(), width=60, no_color=True, legacy_windows=False)
    emit(console, text, **kwargs)
    return console.file.getvalue().splitlines()


def test_emit_never_leaves_trailing_whitespace():
    """rich.Padding pads wrapped lines to block width - invisible on screen, dirty in a file."""
    lines = render("word " * 40, indent=6, bullet="- ")
    assert lines, "expected wrapped output"
    assert all(line == line.rstrip() for line in lines)


def test_emit_aligns_continuations_under_the_first_line():
    lines = render("word " * 30, indent=2, bullet="- ")
    assert lines[0].startswith("  - ")
    assert all(line.startswith("    ") and not line.startswith("    -") for line in lines[1:])


def test_emit_handles_empty_text():
    assert render("") == [""]


def test_plural_agrees():
    assert plural(1, "chain") == "1 chain"
    assert plural(2, "chain") == "2 chains"
    assert plural(0, "chain") == "0 chains"


# --------------------------------------------------------------------------------------
# schema walking
# --------------------------------------------------------------------------------------


def test_undeclared_reports_keys_no_model_declares():
    """extra='ignore' plus a model_dump() round-trip deletes these on the next write."""
    from scripts.deploy.models import DeploymentConfig

    found = _undeclared({"config": {"totally_made_up_key": 1}}, DeploymentConfig)
    assert "config.totally_made_up_key" in found


def test_undeclared_is_quiet_on_a_clean_payload():
    from scripts.deploy.models import DeploymentConfig

    assert _undeclared({}, DeploymentConfig) == []


# --------------------------------------------------------------------------------------
# PENDING: blocked vs ready
# --------------------------------------------------------------------------------------


def _deployment(version="1.0.0"):
    """A deployment recording an old router, so PENDING has something to upgrade."""
    return {
        "config": {},
        "contracts": {
            "helpers": {
                "router": {
                    "address": "0x" + "11" * 20,
                    "contract_path": "/contracts/helpers/router/router_v_100.vy",
                    "contract_version": version,
                }
            }
        },
    }


def test_pending_splits_blocked_from_ready_without_repeating_a_chain():
    """Blocked chains used to appear twice, and the total never visibly added up."""
    deployments = {name: (None, _deployment()) for name in ("prod/a", "prod/b", "prod/c")}
    blocked = {"prod/a": "rejected", "prod/b": "missing"}

    rows = [f for f in check_pending(deployments, {}, blocked) if f.details]
    assert rows, "expected an upgrade finding"
    detail = " ".join(rows[0].details)

    assert "rejected by ChainConfig" in detail and "prod/a" in detail
    assert "no settings/chains file" in detail and "prod/b" in detail
    assert "the other 1 upgrade on the next run: prod/c" in detail
    # Each chain named exactly once across the whole block.
    for chain in ("prod/a", "prod/b", "prod/c"):
        assert detail.count(chain) == 1


def test_pending_labels_the_whole_set_when_nothing_is_blocked():
    deployments = {name: (None, _deployment()) for name in ("prod/a", "prod/b")}
    rows = [f for f in check_pending(deployments, {}, {}) if f.details]
    assert "all 2 upgrade on the next run:" in " ".join(rows[0].details)


def test_pending_emits_no_ready_line_when_everything_is_blocked():
    deployments = {"prod/a": (None, _deployment())}
    rows = [f for f in check_pending(deployments, {}, {"prod/a": "rejected"}) if f.details]
    assert not any("upgrade on the next run" in line for line in rows[0].details)


def test_pending_keeps_every_chain_in_subjects_for_the_summary_rollup():
    # --summary and --json read `subjects`; moving the chain list into `details` must not
    # cost them the machine-readable set.
    deployments = {name: (None, _deployment()) for name in ("prod/a", "prod/b")}
    rows = [f for f in check_pending(deployments, {}, {}) if f.details]
    assert set(rows[0].subjects) == {"prod/a", "prod/b"}


# --------------------------------------------------------------------------------------
# WIRING: the guard path
# --------------------------------------------------------------------------------------


def test_check_wiring_survives_a_chain_with_no_rpc():
    """`inspect` returned a 4-tuple here while the caller unpacked 5."""
    deployments = {"prod/norpc": (None, {"config": {}, "contracts": {}})}
    assert check_wiring(deployments) == []


# --------------------------------------------------------------------------------------
# Finding semantics
# --------------------------------------------------------------------------------------


def test_unverified_defaults_off_so_a_finding_is_a_result_unless_it_says_otherwise():
    assert Finding("SCHEMA", "x").unverified is False
    assert Finding("ONCHAIN", "x", unverified=True).unverified is True


# --------------------------------------------------------------------------------------
# schema round-trip
# --------------------------------------------------------------------------------------


def test_dao_round_trip_keeps_scrvusd():
    """Undeclared keys are dropped when update_deployment_config() rewrites via model_dump()."""
    from scripts.deploy.models import DeploymentConfig

    payload = {
        "config": {
            "file_name": "x",
            "file_path": "prod/x.yaml",
            "network_name": "x",
            "chain_id": 1,
            "layer": 1,
            "rollup_type": "not_rollup",
            "is_testnet": False,
            "wrapped_native_token": "0x" + "11" * 20,
            "explorer_base_url": "https://e",
            "logo_url": "https://l",
            "native_currency_symbol": "X",
            "native_currency_coingecko_id": "x",
            "public_rpc_url": "https://r",
            "reference_token_addresses": {"usdc": "", "usdt": "", "weth": ""},
            "dao": {"scrvusd": "0x" + "22" * 20},
        }
    }
    dumped = DeploymentConfig.model_validate(payload).model_dump()
    assert dumped["config"]["dao"]["scrvusd"] == "0x" + "22" * 20


def test_legacy_amm_registries_survive_the_round_trip():
    """Dropping these would remove real platforms curve-api-core serves."""
    from scripts.deploy.models import AmmDeployment

    row = {
        "address": "0x" + "ab" * 20,
        "compiler_settings": {"compiler_version": "0.3.1", "evm_version": "paris", "optimisation_level": "gas"},
        "constructor_args_encoded": "0x",
        "contract_github_url": "https://x",
        "contract_path": "/contracts/x.vy",
        "contract_version": "1.0.0",
        "deployment_timestamp": 1,
        "deployment_type": "normal",
    }
    keys = ["oldmain", "oldstable", "oldcrypto", "oldcryptofacto", "eywa"]
    dumped = AmmDeployment.model_validate({k: {"factory": row} for k in keys}).model_dump()
    for key in keys:
        assert dumped[key]["factory"]["address"] == row["address"], key


# --------------------------------------------------------------------------------------
# source provenance
# --------------------------------------------------------------------------------------


def _row(url, path="scripts/status.py"):
    return {"contract_path": "/" + path, "contract_github_url": url}


def test_source_provenance_flags_a_file_edited_since_its_deploy_commit():
    """contract_path + contract_version do not identify what was deployed: vendored sources
    are edited in place while the version constant stays put."""
    from scripts.status import _git, source_provenance

    old = _git("rev-list", "--max-parents=0", "HEAD").split("\n")[0]
    assert old != _git("rev-parse", "HEAD"), "needs full history - clone with fetch-depth: 0"
    state, source = source_provenance(_row(f"https://github.com/curvefi/curve-core/blob/{old}/README.md", "README.md"))
    assert state == "drifted"
    assert source, "the historical source must come back so --from-commit can compile it"


def test_source_provenance_is_current_when_the_file_has_not_moved():
    from scripts.status import _git, source_provenance

    head = _git("rev-parse", "HEAD")
    state, source = source_provenance(_row(f"https://github.com/x/y/blob/{head}/README.md", "README.md"))
    assert (state, source) == ("current", None)


def test_source_provenance_reports_an_unknown_commit_rather_than_guessing():
    from scripts.status import source_provenance

    state, _ = source_provenance(_row("https://github.com/x/y/blob/" + "0" * 40 + "/README.md", "README.md"))
    assert state == "unreachable"


def test_source_provenance_reports_a_url_with_no_commit():
    from scripts.status import source_provenance

    assert source_provenance(_row("https://github.com/x/y/blob/main/README.md", "README.md"))[0] == "unpinned"
    assert source_provenance({"contract_path": "/x.vy"})[0] == "unpinned"


def test_file_name_collisions_ignore_a_chain_s_own_devnet_prod_pair():
    """Lite chains are deployed to their testnet first and keep the file_name; curve-api-core
    separates them by folder. Only a name shared by different chains hides one downstream."""
    from pathlib import Path

    def clashes(by_name):
        return {
            n: ps
            for n, ps in by_name.items()
            if len({Path(p).stem for p in ps}) > 1 or len({Path(p).parent.name for p in ps}) < len(ps)
        }

    assert not clashes({"monad": ["deployments/devnet/monad.yaml", "deployments/prod/monad.yaml"]})
    assert clashes({"monad": ["deployments/prod/monad.yaml", "deployments/prod/monad_v2.yaml"]})
    assert clashes({"monad": ["deployments/devnet/monad.yaml", "deployments/prod/other.yaml"]})


def test_a_deployment_file_that_is_not_valid_yaml_is_reported_not_raised(tmp_path, monkeypatch):
    """main once shipped `compiler_settings: null` with children under it; status crashed on
    the whole repo instead of reporting the one bad file."""
    from scripts import status

    broken = tmp_path / "deployments" / "prod"
    broken.mkdir(parents=True)
    (broken / "avalanche.yaml").write_text(
        "contracts:\n  amm:\n    implementation:\n      compiler_settings: null\n        compiler_version: 0.3.10\n"
    )
    monkeypatch.setattr(status, "BASE_DIR", tmp_path)

    good, unreadable = status.load_deployments()
    assert good == {}
    assert list(unreadable) == ["prod/avalanche"]

    finding = status.check_required({}, {}, (), unreadable)[0]
    assert finding.kind == "REQUIRED"
    assert "line 5" in finding.details[0], finding.details
