"""
What this branch changed about the deployment status.

    python manage.py compare base.json head.json --output report.md

Both inputs come from `status --json`. Comparing two runs, rather than one run against a
committed count, means a fix needs no bookkeeping and a new contract version reads as new
work instead of a regression - and a fault already on the base branch never fails a PR that
did not cause it.
"""

import json
from pathlib import Path

import click

# A finding is the same finding across runs if its kind and summary match. Counts embedded
# in a summary ("15 chains: ...") deliberately change identity - that is a real difference.
IDENTITY = ("kind", "summary")

# Kinds where a new finding is always a defect: `deploy all` cannot start or cannot read the
# file. Everything else - PENDING above all - grows from legitimate work and only reports.
BLOCKING = ("CONFIG", "REQUIRED")


def load(path):
    findings = json.loads(Path(path).read_text(encoding="utf-8"))
    return {tuple(f[k] for k in IDENTITY): f for f in findings}


def compare(base, head):
    """(added, fixed, unchanged_count) between two status runs."""
    added = [head[key] for key in head if key not in base]
    fixed = [base[key] for key in base if key not in head]
    return added, fixed, len(set(base) & set(head))


def render_report(added, fixed, unchanged):
    """Markdown for the PR comment. Empty when there is nothing to say."""
    if not added and not fixed:
        return ""
    lines = ["## Deployment status", ""]
    if added:
        lines.append(f"**{len(added)} new**")
        lines += [f"- `{f['kind']}` {f['summary']}" for f in added]
        lines.append("")
    if fixed:
        lines.append(f"**{len(fixed)} fixed**")
        lines += [f"- ~~`{f['kind']}` {f['summary']}~~" for f in fixed]
        lines.append("")
    lines.append(f"<sub>{unchanged} unchanged. `python manage.py status` for the full report.</sub>")

    blocking = [f for f in added if f["kind"] in BLOCKING]
    if blocking:
        lines += ["", f"⛔ {len(blocking)} of the new findings block `deploy all` on that chain."]
    return "\n".join(lines) + "\n"


@click.command("compare", short_help="diff two status --json runs")
@click.argument("base", type=click.Path(exists=True, dir_okay=False))
@click.argument("head", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", metavar="PATH", default=None, help="write the markdown report here")
def compare_command(base, head, output):
    """Report what changed between two `status --json` runs."""
    added, fixed, unchanged = compare(load(base), load(head))
    report = render_report(added, fixed, unchanged)

    click.echo(report or "no change in deployment status")
    if output:
        Path(output).write_text(report, encoding="utf-8", newline="\n")

    blocking = [f for f in added if f["kind"] in BLOCKING]
    if blocking:
        raise SystemExit(1)
