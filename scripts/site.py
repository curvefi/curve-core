"""
The registry as a page, for people rather than programs.

    python manage.py site     # write site/

`deployments/` answers "what is on chain X" only if you already know to look there and how
to read a YAML tree. This renders the same data as one searchable page, and publishes
index.json and schema.json beside it so a consumer gets a stable URL with a real content
type instead of raw.githubusercontent.

Built from registry/index.json, never from the deployment files: the page cannot show
something the published registry does not, and regenerating both is one command.
"""

import html
import json
from datetime import datetime, timezone

import click

from scripts.index import INDEX_PATH, SCHEMA_PATH
from scripts.status import plural, rel
from settings.config import BASE_DIR

SITE_DIR = BASE_DIR / "site"

# Order the groups appear in. Anything not listed still renders, after these - a new
# contract family shows up without editing this file.
GROUP_ORDER = ("amm", "gauge", "helpers", "registries", "governance")


def groups_of(chains):
    """Top-level contract families, in GROUP_ORDER first and then whatever else exists."""
    found = {slot.split(".")[0] for chain in chains for slot in chain["contracts"]}
    return [g for g in GROUP_ORDER if g in found] + sorted(found - set(GROUP_ORDER))


def explorer(config, address):
    base = (config.get("explorer_base_url") or "").rstrip("/")
    return f"{base}/address/{address}" if base else ""


def render_rows(chain, groups):
    """One <details> per chain, holding every recorded address grouped by family."""
    config, contracts = chain["config"], chain["contracts"]
    out = []
    for group in groups:
        slots = {s: a for s, a in contracts.items() if s.split(".")[0] == group}
        if not slots:
            continue
        out.append(f'<h4>{html.escape(group)}</h4><table class="addrs">')
        for slot, address in sorted(slots.items()):
            link = explorer(config, address)
            shown = html.escape(address)
            cell = f'<a href="{html.escape(link)}" rel="noopener">{shown}</a>' if link else shown
            out.append(f'<tr><td class="slot">{html.escape(slot)}</td><td class="addr">{cell}</td></tr>')
        out.append("</table>")
    return "".join(out)


def render_chain(chain, groups):
    config = chain["config"]
    name = config.get("network_name") or chain["id"]
    counts = "".join(
        f'<td class="{"n" if not (c := sum(1 for s in chain["contracts"] if s.split(".")[0] == g)) else "y"}">'
        f'{c or "&middot;"}</td>'
        for g in groups
    )
    tags = [f'<span class="tag">chain {config.get("chain_id")}</span>']
    if config.get("rollup_type") and config["rollup_type"] != "not_rollup":
        tags.append(f'<span class="tag">{html.escape(str(config["rollup_type"]))}</span>')
    if config.get("is_testnet"):
        tags.append('<span class="tag warn">testnet</span>')
    if not chain["deployed_by_core"]:
        tags.append('<span class="tag warn">not deployed by core</span>')

    return f"""<tr class="row" data-search="{html.escape((name + ' ' + chain['id']).lower())}">
<td class="name"><details><summary><strong>{html.escape(name)}</strong>
<span class="id">{html.escape(chain["id"])}</span> {''.join(tags)}</summary>
<div class="detail">{render_rows(chain, groups)}</div></details></td>{counts}
<td class="n">{len(chain["contracts"])}</td></tr>"""


def render(index):
    chains = sorted(index["chains"], key=lambda c: (not c["deployed_by_core"], c["id"]))
    groups = groups_of(chains)
    core = sum(1 for c in chains if c["deployed_by_core"])
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    heads = "".join(f"<th>{html.escape(g)}</th>" for g in groups)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Curve Core registry</title>
<style>{CSS}</style></head><body>
<header>
<h1>Curve Core registry</h1>
<p>{plural(len(chains), "chain")}, {core} deployed by this repo,
{plural(sum(len(c["contracts"]) for c in chains), "recorded address")}. Generated {when}.</p>
<p class="links"><a href="index.json">index.json</a> &middot; <a href="schema.json">schema.json</a>
&middot; <a href="https://github.com/curvefi/curve-core">curvefi/curve-core</a></p>
</header>
<main>
<input id="q" type="search" placeholder="Filter chains" autocomplete="off">
<table class="matrix"><thead><tr><th class="name">Chain</th>{heads}<th>all</th></tr></thead>
<tbody>{"".join(render_chain(c, groups) for c in chains)}</tbody></table>
<p class="foot">Counts are addresses recorded per contract family; open a chain for the
addresses themselves. What is recorded here is not a claim about what is live on chain -
<code>manage.py status --onchain</code> is what checks that.</p>
</main>
<script>
const q = document.getElementById('q');
q.addEventListener('input', () => {{
  const term = q.value.trim().toLowerCase();
  for (const row of document.querySelectorAll('.row'))
    row.hidden = term && !row.dataset.search.includes(term);
}});
</script>
</body></html>
"""


# Inlined rather than a separate file: one artifact to publish, and nothing to fetch from a
# CDN that could outlive or outlast the page.
CSS = """
/* Dark is the base, matching blockhash-oracle and storage-proofs: #1a1a1a / #333 / #888 on
   near-black, blue accent, all of it theirs. Light applies only where the reader asks for
   it, and is declared twice so an explicit choice beats the OS in both directions. */
:root{color-scheme:light dark;--bg:#0a0a0a;--surface:#1a1a1a;--border:#333;--text:#eee;
--dim:#888;--accent:#4ea1ff;--warn:#f59e0b}
@media(prefers-color-scheme:light){:root:not([data-theme="dark"]){--bg:#f7f7f8;
--surface:#fff;--border:#e0e1e6;--text:#1c1c1c;--dim:#5f5f5f;--accent:#1d4ed8;--warn:#9a3412}}
:root[data-theme="light"]{--bg:#f7f7f8;--surface:#fff;--border:#e0e1e6;--text:#1c1c1c;
--dim:#5f5f5f;--accent:#1d4ed8;--warn:#9a3412}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 ui-sans-serif,system-ui,
"Segoe UI",Roboto,sans-serif}
header,main{max-width:1100px;margin:0 auto;padding:0 1.25rem}
header{padding-top:2.5rem;padding-bottom:1rem;border-bottom:1px solid var(--border)}
h1{margin:0 0 .25rem;font-size:1.6rem}
header p{margin:.25rem 0;color:var(--dim)}
a{color:var(--accent)}
.links{font-size:.9rem}
main{padding-top:1.5rem;padding-bottom:4rem}
#q{width:100%;padding:.6rem .75rem;margin-bottom:1rem;border:1px solid var(--border);
border-radius:8px;background:var(--surface);color:var(--text);font-size:1rem}
table{width:100%;border-collapse:collapse}
.matrix{background:var(--surface);border:1px solid var(--border);border-radius:10px;
overflow:hidden}
.matrix th{font-size:.75rem;text-transform:uppercase;letter-spacing:.04em;color:var(--dim);
text-align:center;padding:.6rem .4rem;border-bottom:1px solid var(--border);font-weight:600}
.matrix th.name{text-align:left;padding-left:1rem}
.matrix td{padding:.5rem .4rem;border-bottom:1px solid var(--border);text-align:center;
font-variant-numeric:tabular-nums}
.matrix td.name{text-align:left;padding-left:1rem;width:42%}
tr:last-child td{border-bottom:none}
td.n{color:var(--dim)}
summary{cursor:pointer;list-style:none}
summary::-webkit-details-marker{display:none}
summary::before{content:"\\25B8";color:var(--dim);display:inline-block;width:1em}
details[open] summary::before{content:"\\25BE"}
.id{color:var(--dim);font-size:.85rem;margin-left:.4rem}
.tag{display:inline-block;margin-left:.35rem;padding:.05rem .4rem;border-radius:999px;
border:1px solid var(--border);color:var(--dim);font-size:.72rem;vertical-align:middle}
.tag.warn{color:var(--warn);border-color:currentColor}
.detail{padding:.75rem 0 .5rem 1.6rem}
.detail h4{margin:.75rem 0 .25rem;font-size:.8rem;text-transform:uppercase;
letter-spacing:.04em;color:var(--dim)}
.addrs td{border:none;text-align:left;padding:.15rem .5rem .15rem 0}
.slot{color:var(--dim);font-size:.85rem;white-space:nowrap}
.addr{font-family:ui-monospace,Consolas,monospace;font-size:.82rem;word-break:break-all}
.foot{color:var(--dim);font-size:.85rem;margin-top:1.5rem}
code{font-family:ui-monospace,Consolas,monospace;font-size:.85em}
"""


def build():
    """The page plus the two artifacts it links to, as {relative name: text}.

    The page is rendered from the committed index.json, not from a fresh build_index(), so
    the table and the JSON beside it can never describe different data.
    """
    index = INDEX_PATH.read_text(encoding="utf-8")
    return {
        "index.html": render(json.loads(index)),
        "index.json": index,
        "schema.json": SCHEMA_PATH.read_text(encoding="utf-8"),
    }


@click.command("site", short_help="render the registry as a static page")
def site_command():
    """Write site/ - the registry as one searchable page, plus index.json and schema.json."""
    missing = [rel(p) for p in (INDEX_PATH, SCHEMA_PATH) if not p.exists()]
    if missing:
        raise click.ClickException(f"missing {', '.join(missing)} - run `python manage.py index` first")

    files = build()
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (SITE_DIR / name).write_text(text, encoding="utf-8", newline="\n")
    click.echo(f"wrote {plural(len(files), 'file')} to {rel(SITE_DIR)}")
