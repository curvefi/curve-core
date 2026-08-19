"""Unit tests for `manage.py site` - the registry rendered as a page.

Offline. The page is published at a stable URL, so a wrong or broken one is worse than none.
"""

import json
from html.parser import HTMLParser

from click.testing import CliRunner

VOID_TAGS = {"meta", "input", "br", "hr", "link", "img"}


class Balanced(HTMLParser):
    """Tags must nest. A stray </td> silently swallows the rest of a table in a browser."""

    def __init__(self):
        super().__init__()
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack:
            self.errors.append(f"stray </{tag}>")
        elif self.stack[-1] != tag:
            self.errors.append(f"</{tag}> closes <{self.stack[-1]}>")
        else:
            self.stack.pop()


def _index(chains):
    return {"count": len(chains), "chains": chains}


def _chain(chain_id="prod/x", contracts=None, deployed_by_core=True, **config):
    return {
        "id": chain_id,
        "file_path": f"{chain_id}.yaml",
        "deployed_by_core": deployed_by_core,
        "config": {
            "network_name": chain_id.split("/")[-1],
            "chain_id": 1,
            "explorer_base_url": "https://scan.example/",
            **config,
        },
        "contracts": contracts if contracts is not None else {"amm.stableswap.factory": "0xaaa"},
    }


def test_the_page_is_well_formed():
    from scripts.site import render

    parser = Balanced()
    parser.feed(render(_index([_chain(), _chain("devnet/y")])))
    assert not parser.errors and not parser.stack, (parser.errors, parser.stack)


def test_the_real_registry_renders_well_formed():
    """The fixtures cannot cover 632 addresses across five contract families."""
    from scripts.index import INDEX_PATH
    from scripts.site import render

    parser = Balanced()
    parser.feed(render(json.loads(INDEX_PATH.read_text(encoding="utf-8"))))
    assert not parser.errors and not parser.stack, (parser.errors, parser.stack)


def test_every_chain_and_every_address_appears():
    """An index that publishes a chain and a page that drops it is the worst of both."""
    from scripts.index import INDEX_PATH
    from scripts.site import render

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    page = render(index)

    assert page.count('<tr class="row"') == len(index["chains"])
    for chain in index["chains"]:
        for address in chain["contracts"].values():
            assert address in page, f"{chain['id']} {address}"


def test_group_counts_match_the_index():
    """Columns are the families the fleet has, so a chain missing one shows a dot, not a gap."""
    from scripts.site import render

    rich = _chain(
        contracts={
            "amm.stableswap.factory": "0xa",
            "amm.stableswap.views": "0xb",
            "gauge.child_gauge.factory": "0xc",
        }
    )
    page = render(_index([rich, _chain("prod/bare", contracts={"amm.stableswap.factory": "0xd"})]))

    def cells(name):  # rows are sorted, so find the row rather than counting positions
        return page.split(f'data-search="{name} ')[1].split("</details></td>")[1][:120]

    assert ">2<" in cells("x") and ">1<" in cells("x")  # amm 2, gauge 1
    assert ">1<" in cells("bare") and "&middot;" in cells("bare")  # amm 1, no gauge at all


def test_a_chain_with_no_explorer_still_lists_its_addresses():
    """explorer_base_url is missing on some chains; the address is the point, the link is not."""
    from scripts.site import render

    page = render(_index([_chain(explorer_base_url="")]))
    assert "0xaaa" in page
    assert 'href=""' not in page


def test_legacy_and_testnet_chains_are_marked():
    from scripts.site import render

    page = render(_index([_chain(deployed_by_core=False), _chain("devnet/t", is_testnet=True)]))
    assert "not deployed by core" in page
    assert "testnet</span>" in page


def test_chain_names_are_escaped():
    """Names come from a YAML file anyone can edit in a PR."""
    from scripts.site import render

    page = render(_index([_chain(network_name="<script>alert(1)</script>")]))
    assert "<script>alert(1)" not in page
    assert "&lt;script&gt;" in page


def test_unknown_contract_families_still_render():
    """GROUP_ORDER is presentation. A new family must not vanish because it is not listed."""
    from scripts.site import groups_of, render

    chain = _chain(contracts={"amm.stableswap.factory": "0xa", "newthing.gadget": "0xb"})
    assert groups_of([chain])[-1] == "newthing"
    assert "newthing" in render(_index([chain]))


def test_the_page_and_the_json_beside_it_are_the_same_data():
    """The page used to render from a fresh build while shipping the committed JSON, so a
    stale artifact would publish a table and a file that disagreed."""
    from scripts.site import build

    files = build()
    index = json.loads(files["index.json"])
    assert files["index.html"].count('<tr class="row"') == len(index["chains"])


def test_site_writes_the_three_files(tmp_path, monkeypatch):
    from scripts import site as site_module

    monkeypatch.setattr(site_module, "SITE_DIR", tmp_path / "site")
    result = CliRunner().invoke(site_module.site_command, [])

    assert result.exit_code == 0, result.output
    written = {p.name for p in (tmp_path / "site").iterdir()}
    assert written == {"index.html", "index.json", "schema.json"}


def test_site_refuses_to_render_without_the_registry(tmp_path, monkeypatch):
    from scripts import site as site_module

    monkeypatch.setattr(site_module, "INDEX_PATH", tmp_path / "gone.json")
    result = CliRunner().invoke(site_module.site_command, [])

    assert result.exit_code == 1
    assert "manage.py index" in result.output


def test_the_page_uses_unix_line_endings(tmp_path, monkeypatch):
    from scripts import site as site_module

    monkeypatch.setattr(site_module, "SITE_DIR", tmp_path / "site")
    CliRunner().invoke(site_module.site_command, [])
    assert b"\r\n" not in (tmp_path / "site" / "index.html").read_bytes()


def test_the_page_fetches_nothing_external():
    """It is published on Pages and read by people behind assorted networks; an external
    stylesheet or font is a dependency that can outlive whoever added it."""
    import re

    from scripts.index import INDEX_PATH
    from scripts.site import render

    page = render(json.loads(INDEX_PATH.read_text(encoding="utf-8")))
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', page)
    assert all("/address/" in url or "github.com/curvefi" in url for url in external), external
