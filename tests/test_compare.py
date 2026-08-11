"""Unit tests for `manage.py compare` - this branch's findings against its base.

Offline. Replaces the committed-baseline ratchet, which failed on correct work.
"""

import json

from click.testing import CliRunner


def _finding(kind, summary):
    return {
        "kind": kind,
        "summary": summary,
        "note": "",
        "items": [],
        "details": [],
        "subjects": [],
        "unverified": False,
    }


def _write(tmp_path, name, findings):
    path = tmp_path / name
    path.write_text(json.dumps(findings), encoding="utf-8")
    return str(path)


def test_adding_a_contract_version_is_reported_not_failed(tmp_path):
    """The reason the baseline ratchet was wrong: a new _v_NNN.vy legitimately creates a
    PENDING finding, and the old gate read that correct change as a regression."""
    from scripts.compare import compare_command

    base = _write(tmp_path, "base.json", [_finding("CONFIG", "devnet/x  (1 error)")])
    head = _write(
        tmp_path, "head.json", [_finding("CONFIG", "devnet/x  (1 error)"), _finding("PENDING", "impl 1 -> 2")]
    )

    result = CliRunner().invoke(compare_command, [base, head])
    assert result.exit_code == 0
    assert "1 new" in result.output and "PENDING" in result.output


def test_a_new_blocking_finding_fails(tmp_path):
    from scripts.compare import compare_command

    base = _write(tmp_path, "base.json", [])
    head = _write(tmp_path, "head.json", [_finding("REQUIRED", "prod/x  (not valid YAML)")])

    result = CliRunner().invoke(compare_command, [base, head])
    assert result.exit_code == 1
    assert "block `deploy all`" in result.output


def test_a_fault_already_on_base_does_not_fail_the_branch(tmp_path):
    """main once shipped a broken deployment file and reddened every open PR. Unchanged
    findings are the base branch's problem, not this branch's."""
    from scripts.compare import compare_command

    broken = [_finding("REQUIRED", "prod/avalanche  (not valid YAML)")]
    base, head = _write(tmp_path, "base.json", broken), _write(tmp_path, "head.json", broken)

    result = CliRunner().invoke(compare_command, [base, head])
    assert result.exit_code == 0
    assert result.output.strip() == "no change in deployment status"


def test_fixed_findings_are_reported(tmp_path):
    from scripts.compare import compare_command

    base = _write(tmp_path, "base.json", [_finding("CONFIG", "prod/tac  (1 error)")])
    head = _write(tmp_path, "head.json", [])

    result = CliRunner().invoke(compare_command, [base, head])
    assert result.exit_code == 0
    assert "1 fixed" in result.output


def test_no_report_file_is_written_when_nothing_changed(tmp_path):
    """CI deletes the sticky comment on an empty report; a stale one would outlive its cause."""
    from scripts.compare import compare_command

    base = _write(tmp_path, "base.json", [_finding("PENDING", "same")])
    head = _write(tmp_path, "head.json", [_finding("PENDING", "same")])
    out = tmp_path / "report.md"

    assert CliRunner().invoke(compare_command, [base, head, "--output", str(out)]).exit_code == 0
    assert out.read_text(encoding="utf-8") == ""


def test_a_missing_input_is_a_usage_error(tmp_path):
    from scripts.compare import compare_command

    base = _write(tmp_path, "base.json", [])
    result = CliRunner().invoke(compare_command, [base, str(tmp_path / "nope.json")])
    assert result.exit_code == 2
