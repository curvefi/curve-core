"""
Nightly on-chain health, as one self-updating GitHub issue.

    python manage.py status --onchain --wiring --json onchain.json
    python manage.py monitor onchain.json --previous issue.md --body body.md --delta delta.md

Reads a `status --json` run and keeps only what the probes found on chain. The offline
checks belong to PR CI, which already gates them; repeating them nightly would leave the
issue permanently non-empty, and an alert that is always on is an alert nobody reads.

Only prod opens the issue. A devnet chain that was wiped and redeployed is real information
but it is not a 6am alert, and devnet churn would keep the issue open permanently - the same
reason the offline checks stay out.

`--body` is empty when prod is clean, so the workflow closes the issue on that alone.
`--delta` is empty when the prod deviations match the previous body, so an issue that is
already open comments - and therefore notifies - only when the set actually changes.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import click

from scripts.compare import IDENTITY, compare
from scripts.status import chain_configs, in_scope, load_deployments, plural

# status --json carries the offline findings too; the nightly report drops them.
PROBE_KINDS = ("ONCHAIN", "WIRING", "BYTECODE")

PAGING_ENV = "prod/"

# State lives in the issue body: no artifact to expire, and nothing to commit.
STATE_PREFIX = "<!-- curve-core-monitor: "
STATE_SUFFIX = " -->"

# Space-joining 24 rows, as the terminal renderer does, makes one unreadable line.
ITEMS_SHOWN = 6


def subjects(finding):
    return set(finding.get("subjects") or ())


def pages(finding):
    """A finding with no subject is repo-wide; treat it as prod rather than lose it."""
    return not subjects(finding) or any(key.startswith(PAGING_ENV) for key in subjects(finding))


def classify(findings):
    """(paging, reported, unverified) among the on-chain kinds.

    `unverified` drops any chain a deviation already names: a chain with no code cannot
    answer `owner()` either, so keeping both restates one problem as two.
    """
    probes = [f for f in findings if f["kind"] in PROBE_KINDS]
    deviations = [f for f in probes if not f.get("unverified")]
    named = {key for f in deviations for key in subjects(f)}
    return (
        [f for f in deviations if pages(f)],
        [f for f in deviations if not pages(f)],
        [f for f in probes if f.get("unverified") and not subjects(f) & named],
    )


def scope_size():
    """How many chains `status` would probe, from the rule `status` uses to pick them.

    Coverage needs a denominator, and a clean chain leaves no finding to count.
    """
    deployments, _ = load_deployments()
    return len(in_scope(deployments, chain_configs())[0])


def previous_deviations(body):
    """Identities recorded in the last issue body, empty if there is no readable state.

    An unreadable block reads as a first run: over-reporting once beats missing a deviation.
    """
    for line in reversed((body or "").splitlines()):
        if line.startswith(STATE_PREFIX) and line.endswith(STATE_SUFFIX):
            try:
                return {tuple(item) for item in json.loads(line[len(STATE_PREFIX) : -len(STATE_SUFFIX)])}
            except (TypeError, ValueError):
                return set()
    return set()


def identify(finding):
    return tuple(finding[key] for key in IDENTITY)


def render_finding(finding):
    lines = [f"- `{finding['kind']}` {finding['summary']}"]
    if finding.get("note"):
        lines.append(f"  - {finding['note']}")
    lines += [f"  - {detail}" for detail in finding.get("details") or ()]
    items = finding.get("items") or []
    if items:
        shown = [f"`{item}`" for item in items[:ITEMS_SHOWN]]
        if len(items) > ITEMS_SHOWN:
            shown.append(f"+{len(items) - ITEMS_SHOWN} more")
        lines.append(f"  - {', '.join(shown)}")
    return lines


def render_coverage(probed, unverified, when):
    """Counted in chains, not findings: one silent chain produces several unverified rows."""
    incomplete = {key for f in unverified for key in subjects(f)}
    parts = [f"{plural(probed, 'chain')} probed" if probed else "probed"]
    if incomplete:
        parts.append(f"{len(incomplete)} incompletely")
    return f"{', '.join(parts)} — {when}."


def render_body(paging, reported=(), unverified=(), probed=None, when=None, run_url=None):
    """The issue body. Empty when prod is clean - that is how the workflow decides to close."""
    if not paging:
        return ""
    when = when or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    headline = f"**{plural(len(paging), 'deviation')} on prod**"
    if reported:
        headline += f", {len(reported)} on devnet"
    lines = ["## On-chain health", "", f"{headline}. {render_coverage(probed, unverified, when)}", ""]

    for title, rows in (("Prod", paging), ("Devnet", reported)):
        if not rows:
            continue
        lines.append(f"### {title}")
        for row in rows:
            lines += render_finding(row)
        lines.append("")

    if unverified:
        # Shown, never the reason an issue exists: an endpoint that rate-limits tonight and
        # answers tomorrow would page the team every other night. A broken one is a deviation.
        lines += [f"<details><summary>{plural(len(unverified), 'check')} could not complete</summary>", ""]
        lines += [f"- {row['summary']}" for row in unverified]
        lines += ["", "</details>", ""]

    reproduce = "Reproduce with `python manage.py status --onchain --wiring`."
    lines.append(f"<sub>{reproduce}{f' [Run]({run_url})' if run_url else ''}</sub>")
    lines.append(STATE_PREFIX + json.dumps([list(identify(f)) for f in paging]) + STATE_SUFFIX)
    return "\n".join(lines) + "\n"


def render_delta(added, fixed, unchanged):
    """The comment posted when the prod deviations change. Empty when they have not."""
    if not added and not fixed:
        return ""
    lines = []
    if added:
        lines.append(f"**{plural(len(added), 'new deviation')}**")
        lines += [f"- `{f['kind']}` {f['summary']}" for f in added]
        lines.append("")
    if fixed:
        lines.append(f"**{len(fixed)} no longer reported**")
        lines += [f"- ~~`{f['kind']}` {f['summary']}~~" for f in fixed]
        lines.append("")
    lines.append(f"<sub>{unchanged} unchanged. The issue body above is the current state.</sub>")
    return "\n".join(lines) + "\n"


@click.command("monitor", short_help="render the nightly on-chain health issue")
@click.argument("findings", type=click.Path(exists=True, dir_okay=False))
@click.option("--previous", metavar="PATH", default=None, help="the current issue body, to detect what changed")
@click.option("--body", "body_path", metavar="PATH", default=None, help="write the new issue body here")
@click.option("--delta", "delta_path", metavar="PATH", default=None, help="write the change comment here")
@click.option("--run-url", metavar="URL", default=None, help="link back to the workflow run")
def monitor_command(findings, previous, body_path, delta_path, run_url):
    """Turn a `status --json` run into the body and the change comment for one issue."""
    paging, reported, unverified = classify(json.loads(Path(findings).read_text(encoding="utf-8")))
    body = render_body(paging, reported, unverified, probed=scope_size(), run_url=run_url)

    was = previous_deviations(
        Path(previous).read_text(encoding="utf-8") if previous and Path(previous).exists() else ""
    )
    # Rebuilt from identities alone: enough to say a finding is gone, which is all `fixed` needs.
    added, fixed, unchanged = compare({key: dict(zip(IDENTITY, key)) for key in was}, {identify(f): f for f in paging})
    delta = render_delta(added, fixed, unchanged)

    click.echo(f"prod {len(paging)}, devnet {len(reported)}, unverified {len(unverified)}")
    click.echo(f"{len(added)} new since the last run, {len(fixed)} gone")
    for label, rows in (("PROD  ", paging), ("devnet", reported), ("      ", unverified)):
        for row in rows:
            click.echo(f"  {label} {row['kind']:<9} {row['summary']}")

    for path, text in ((body_path, body), (delta_path, delta)):
        if path:
            Path(path).write_text(text, encoding="utf-8", newline="\n")
