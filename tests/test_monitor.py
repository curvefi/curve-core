"""Unit tests for `manage.py monitor` - the nightly on-chain health issue.

Offline. The workflow's whole notification model rests on two properties tested here: an
empty body means "close the issue", and an empty delta means "do not comment".
"""

import json

from click.testing import CliRunner


def _finding(kind, summary, unverified=False, subjects=(), **extra):
    return {
        "kind": kind,
        "summary": summary,
        "note": "",
        "items": [],
        "details": [],
        "subjects": list(subjects),
        "unverified": unverified,
        **extra,
    }


def _write(tmp_path, name, findings):
    path = tmp_path / name
    path.write_text(json.dumps(findings), encoding="utf-8")
    return str(path)


def test_offline_findings_are_not_reported():
    """PR CI already gates these. Nightly would leave the issue permanently open."""
    from scripts.monitor import classify

    paging, reported, unverified = classify(
        [
            _finding("PENDING", "impl 1 -> 2"),
            _finding("REQUIRED", "prod/x"),
            _finding("ONCHAIN", "prod/y: no bytecode", subjects=["prod/y"]),
        ]
    )
    assert [f["summary"] for f in paging] == ["prod/y: no bytecode"]
    assert reported == [] and unverified == []


def test_only_prod_opens_the_issue():
    """A wiped testnet is real information and not a 6am alert; devnet churn would keep the
    issue open permanently, which is how an alert stops being read."""
    from scripts.monitor import classify

    paging, reported, _ = classify(
        [
            _finding("ONCHAIN", "devnet/megaeth: 24/24 addresses have NO bytecode", subjects=["devnet/megaeth"]),
            _finding("WIRING", "prod/sonic: 1 factory pointer out of sync", subjects=["prod/sonic"]),
        ]
    )
    assert [f["summary"] for f in paging] == ["prod/sonic: 1 factory pointer out of sync"]
    assert [f["summary"] for f in reported] == ["devnet/megaeth: 24/24 addresses have NO bytecode"]


def test_scope_all_lets_devnet_page():
    """A pull request that edited a devnet file is asking about that chain; only the nightly
    run has a reason to ignore devnet churn."""
    from scripts.monitor import classify

    findings = [_finding("ONCHAIN", "devnet/megaeth: no bytecode", subjects=["devnet/megaeth"])]
    paging, reported, _ = classify(findings, scope="all")

    assert len(paging) == 1 and reported == []
    assert classify(findings)[0] == [], "prod scope must still ignore it"


def test_scope_all_does_not_label_a_devnet_chain_as_prod():
    """The headline and section heading are hardcoded to prod in the nightly shape; a pull
    request touching devnet/arc would have filed it under "Prod"."""
    from scripts.monitor import render_body

    body = render_body([_finding("ONCHAIN", "devnet/arc: no bytecode", subjects=["devnet/arc"])], scope="all")

    assert "on prod" not in body and "### Prod" not in body
    assert "1 deviation" in body and "devnet/arc" in body


def test_a_devnet_only_run_writes_no_body():
    from scripts.monitor import classify, render_body

    paging, reported, unverified = classify(
        [_finding("ONCHAIN", "devnet/monad: no bytecode", subjects=["devnet/monad"])]
    )
    assert render_body(paging, reported, unverified) == ""


def test_a_finding_with_no_chain_still_pages():
    """CONTRACTS-style findings belong to no chain. Losing one is worse than over-reporting."""
    from scripts.monitor import classify

    paging, _, _ = classify([_finding("ONCHAIN", "something repo-wide")])
    assert len(paging) == 1


def test_a_clean_probe_writes_no_body():
    from scripts.monitor import render_body

    assert render_body([]) == ""


def test_a_dead_rpc_alone_never_opens_an_issue():
    """It flaps: rate-limited tonight, fine tomorrow. Waking the team every other night
    is how a monitor gets muted."""
    from scripts.monitor import classify, render_body

    paging, reported, unverified = classify(
        [_finding("ONCHAIN", "prod/x: unverified, RPC failed", unverified=True, subjects=["prod/x"])]
    )
    assert unverified and render_body(paging, reported, unverified) == ""


def test_an_unverified_chain_a_deviation_already_names_is_dropped():
    """A chain with no code cannot answer owner() either, so reporting both restated one
    problem as two - and made a few broken endpoints read as half the fleet unchecked."""
    from scripts.monitor import classify

    _, reported, unverified = classify(
        [
            _finding("ONCHAIN", "devnet/megaeth: 24/24 addresses have NO bytecode", subjects=["devnet/megaeth"]),
            _finding("WIRING", "devnet/megaeth: ownership unverifiable", unverified=True, subjects=["devnet/megaeth"]),
            _finding("ONCHAIN", "devnet/plasma: unverified, 5/25 failed", unverified=True, subjects=["devnet/plasma"]),
        ]
    )
    assert len(reported) == 1
    assert [f["summary"] for f in unverified] == ["devnet/plasma: unverified, 5/25 failed"]


def test_coverage_counts_chains_not_findings():
    """One chain that answers nothing produces several unverified rows."""
    from scripts.monitor import render_coverage

    line = render_coverage(
        24,
        [
            _finding("ONCHAIN", "devnet/neon: unverified", unverified=True, subjects=["devnet/neon"]),
            _finding("WIRING", "devnet/neon: unverified", unverified=True, subjects=["devnet/neon"]),
        ],
        "now",
    )
    assert "24 chains probed" in line and "1 incompletely" in line


def test_the_probed_total_comes_from_the_same_scope_status_uses():
    from scripts.monitor import scope_size
    from scripts.status import chain_configs, in_scope, load_deployments

    assert scope_size() == len(in_scope(load_deployments()[0], chain_configs())[0])


def test_a_dead_rpc_is_shown_once_an_issue_exists():
    """It explains why coverage is incomplete, which matters when something else is wrong."""
    from scripts.monitor import render_body

    body = render_body(
        [_finding("ONCHAIN", "prod/y: 2 addresses have NO bytecode", subjects=["prod/y"])],
        unverified=[_finding("ONCHAIN", "prod/x: unverified, RPC failed on 24/24", unverified=True)],
    )
    assert "could not complete" in body
    assert "prod/x: unverified" in body


def test_a_long_row_list_is_truncated():
    """A chain with nothing deployed lists every slot it has, and space-joining 24 of them
    is one line no reader gets through."""
    from scripts.monitor import ITEMS_SHOWN, render_body

    rows = [f"amm.slot{n} 0x{n:040x}" for n in range(24)]
    body = render_body([_finding("ONCHAIN", "prod/y: 24 addresses have NO bytecode", items=rows)])

    assert f"+{24 - ITEMS_SHOWN} more" in body
    assert rows[ITEMS_SHOWN] not in body
    assert max(len(line) for line in body.splitlines() if not line.startswith("<!--")) < 800


def test_the_body_carries_its_own_state():
    """No artifact to expire and no commit: the issue body is the store."""
    from scripts.monitor import previous_deviations, render_body

    paging = [
        _finding("ONCHAIN", "prod/y: 2 addresses have NO bytecode", subjects=["prod/y"]),
        _finding("WIRING", "prod/z: 1 factory pointer out of sync", subjects=["prod/z"]),
    ]
    assert previous_deviations(render_body(paging)) == {
        ("ONCHAIN", "prod/y: 2 addresses have NO bytecode"),
        ("WIRING", "prod/z: 1 factory pointer out of sync"),
    }


def test_only_paging_findings_reach_the_state():
    """Devnet churn and probe counts both move on their own; keeping either in the state
    would make the set look changed on a night when nothing did."""
    from scripts.monitor import previous_deviations, render_body

    body = render_body(
        [_finding("ONCHAIN", "prod/y: no bytecode", subjects=["prod/y"])],
        reported=[_finding("ONCHAIN", "devnet/monad: no bytecode", subjects=["devnet/monad"])],
        unverified=[_finding("ONCHAIN", "prod/x: unverified, RPC failed on 24/24", unverified=True)],
    )
    assert previous_deviations(body) == {("ONCHAIN", "prod/y: no bytecode")}


def test_an_unreadable_state_block_reads_as_a_first_run():
    from scripts.monitor import previous_deviations

    assert previous_deviations("## On-chain health\n<!-- curve-core-monitor: not json -->\n") == set()
    assert previous_deviations("hand-written issue body") == set()


def test_no_comment_when_the_deviations_are_unchanged(tmp_path):
    from scripts.monitor import monitor_command, render_body

    same = [_finding("ONCHAIN", "prod/y: no bytecode", subjects=["prod/y"])]
    previous = tmp_path / "previous.md"
    previous.write_text(render_body(same), encoding="utf-8")
    body, delta = tmp_path / "body.md", tmp_path / "delta.md"

    result = CliRunner().invoke(
        monitor_command,
        [_write(tmp_path, "f.json", same), "--previous", str(previous), "--body", str(body), "--delta", str(delta)],
    )
    assert result.exit_code == 0
    assert delta.read_text(encoding="utf-8") == ""
    assert body.read_text(encoding="utf-8") != "", "the issue stays open and up to date"


def test_the_comment_names_what_appeared_and_what_went_away(tmp_path):
    from scripts.monitor import monitor_command, render_body

    was = [_finding("ONCHAIN", "prod/y: no bytecode", subjects=["prod/y"])]
    now = [_finding("WIRING", "prod/z: 1 factory pointer out of sync", subjects=["prod/z"])]
    previous = tmp_path / "previous.md"
    previous.write_text(render_body(was), encoding="utf-8")
    delta = tmp_path / "delta.md"

    CliRunner().invoke(
        monitor_command,
        [_write(tmp_path, "f.json", now), "--previous", str(previous), "--delta", str(delta)],
    )
    text = delta.read_text(encoding="utf-8")
    assert "1 new deviation" in text and "prod/z" in text
    assert "no longer reported" in text and "prod/y" in text


def test_devnet_churn_never_comments(tmp_path):
    """The issue can be open for a prod fault while devnet resets nightly underneath it."""
    from scripts.monitor import monitor_command, render_body

    prod = _finding("ONCHAIN", "prod/y: no bytecode", subjects=["prod/y"])
    previous = tmp_path / "previous.md"
    previous.write_text(render_body([prod]), encoding="utf-8")
    delta = tmp_path / "delta.md"

    CliRunner().invoke(
        monitor_command,
        [
            _write(tmp_path, "f.json", [prod, _finding("ONCHAIN", "devnet/new: gone", subjects=["devnet/new"])]),
            "--previous",
            str(previous),
            "--delta",
            str(delta),
        ],
    )
    assert delta.read_text(encoding="utf-8") == ""


def test_a_missing_previous_body_is_a_first_run(tmp_path):
    """The first scheduled run has no issue to read, and neither does one that was closed."""
    from scripts.monitor import monitor_command

    delta = tmp_path / "delta.md"
    findings = [_finding("ONCHAIN", "prod/y: no bytecode", subjects=["prod/y"])]

    result = CliRunner().invoke(
        monitor_command,
        [_write(tmp_path, "f.json", findings), "--previous", str(tmp_path / "gone.md"), "--delta", str(delta)],
    )
    assert result.exit_code == 0
    assert "1 new deviation" in delta.read_text(encoding="utf-8")


def test_what_counts_as_the_same_finding_is_compare_s_definition():
    """Two consumers, one notion of identity - so a change to one cannot silently give the
    nightly report a different idea of what "already reported" means."""
    import scripts.compare
    import scripts.monitor

    assert scripts.monitor.IDENTITY is scripts.compare.IDENTITY


def test_artifacts_use_unix_line_endings(tmp_path):
    """gh posts these verbatim; CRLF would show through in the rendered issue."""
    from scripts.monitor import monitor_command

    body = tmp_path / "body.md"
    findings = [_finding("ONCHAIN", "prod/y: no bytecode", subjects=["prod/y"])]

    CliRunner().invoke(monitor_command, [_write(tmp_path, "f.json", findings), "--body", str(body)])
    assert b"\r\n" not in body.read_bytes()
