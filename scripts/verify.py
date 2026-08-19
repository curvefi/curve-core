"""
Contract verification on block explorers.

    python manage.py verify prod/sonic           # what would be submitted, and where
    python manage.py verify prod/sonic --submit  # actually submit

The deployment file already records everything an explorer asks for - compiler version,
evm version, optimisation level, constructor args and the source path - so verification is
assembling a payload rather than gathering facts. The README used to say Etherscan had no
Vyper API; it has had `codeformat=vyper-json` since the v2 endpoint.

Blueprints are reported and skipped: what sits on chain for one is the initcode, and no
explorer verifies that against a source file.
"""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

import click

from scripts.status import chain_configs, contract_rows, in_scope, load_deployments, plural, rel, source_provenance
from settings.config import BASE_DIR, settings

ETHERSCAN_API = "https://api.etherscan.io/v2/api"
CHAINLIST = "https://api.etherscan.io/v2/chainlist"
THROTTLE = 0.25  # seconds between submissions; the free tier allows 5 calls a second

# Blockscout, for the 12 chains Etherscan does not list. Same standard json, no key, and it
# matches on runtime rather than creation bytecode.
BLOCKSCOUT_VERSION = "/api/v2/config/backend-version"
BLOCKSCOUT_CONFIG = "/api/v2/smart-contracts/verification/config"
BLOCKSCOUT_VERIFY = "/api/v2/smart-contracts/{address}/verification/via/vyper-standard-input"
BLOCKSCOUT_CONTRACT = "/api/v2/smart-contracts/{address}"

# `import contracts.governance.relayer.relayer_v_100 as Relayer` - a module in this repo, which
# has to travel with the source. vyper.interfaces and ethereum.ercs are builtins and must not.
LOCAL_IMPORT = re.compile(r"^\s*(?:import|from)\s+(contracts(?:\.\w+)+)", re.M)

# Recorded in seven spellings across the fleet - GAS, gas, CODESIZE, codesize, NONE, UNKNOWN
# and null - so match on lower case and treat anything else as "not recorded".
OPTIMISATION = {"gas": "gas", "codesize": "codesize", "none": "none"}

PRAGMA_OPTIMIZE = re.compile(r"^#\s*pragma\s+optimize\s+(\w+)", re.M)


def source_path(row):
    """contract_path is recorded absolute-from-repo-root, with a leading slash."""
    return BASE_DIR / (row.get("contract_path") or "").lstrip("/")


def collect_sources(path, seen=None):
    """The contract and every repo module it imports, keyed as the compiler sees them.

    Builtin imports are left out on purpose - supplying them shadows the compiler's own and
    changes what gets built.
    """
    seen = {} if seen is None else seen
    key = path.relative_to(BASE_DIR).as_posix()
    if key in seen:
        return seen
    text = path.read_text(encoding="utf-8")
    seen[key] = {"content": text}
    for module in LOCAL_IMPORT.findall(text):
        imported = BASE_DIR / (module.replace(".", "/") + ".vy")
        if imported.exists():
            collect_sources(imported, seen)
    return seen


def optimised(row, text):
    """Whether optimisation ran, for Etherscan's form field only.

    The pragma wins where there is one; `optimisation_level` is a record of what the compiler
    chose, in seven spellings, and 202 rows say UNKNOWN or null.
    """
    pragma = PRAGMA_OPTIMIZE.search(text)
    level = pragma.group(1) if pragma else (row.get("compiler_settings") or {}).get("optimisation_level")
    return OPTIMISATION.get(str(level).lower(), "gas") != "none"


def standard_json(row):
    """The vyper-json input an explorer verifies against.

    The source comes from the commit the row was deployed at, not from today's file. Vyper
    hashes the source into the deploy bytecode, so a file that has since gained or lost a
    comment still has identical runtime bytecode but different creation code - and an
    explorer matching on creation code would reject it.

    Deliberately sets no `optimize`: the deployer compiles with evm_version alone
    (`boa.load_partial(contract, compiler_args={"evm_version": ...})`), so the source pragma
    is what chose the mode on chain. Stating one here can only disagree - and vyper rejects
    a setting that contradicts a pragma outright.
    """
    settings = row.get("compiler_settings") or {}
    state, historical = source_provenance(row)
    sources = collect_sources(source_path(row))
    if state == "drifted":
        sources[source_path(row).relative_to(BASE_DIR).as_posix()] = {"content": historical}

    payload = {
        "language": "Vyper",
        "sources": sources,
        # Everything, not just the bytecode we need locally: the explorer reads the abi out
        # of this too, and asking for less makes it report "unable to get compiled bytecode".
        "settings": {"outputSelection": {"*": ["*"]}},
    }
    if settings.get("evm_version"):
        payload["settings"]["evmVersion"] = settings["evm_version"]
    return payload


def etherscan_chains():
    """Chain ids the v2 endpoint serves. Unauthenticated, so this needs no key to plan."""
    with urllib.request.urlopen(CHAINLIST, timeout=20) as response:
        listed = json.load(response)
    return {int(entry["chainid"]) for entry in listed.get("result", []) if str(entry.get("chainid", "")).isdigit()}


def plan_row(slot, row, chain_id, route):
    """(action, detail) for one recorded contract. `route` is what resolve_route decided."""
    if row.get("deployment_type") == "blueprint":
        return "skip", "blueprint - the chain holds initcode, which no explorer verifies"
    if not row.get("contract_path"):
        return "skip", "no contract_path recorded"
    if not source_path(row).exists():
        return "blocked", f"source is gone: {rel(source_path(row))}"
    if not (row.get("compiler_settings") or {}).get("compiler_version"):
        return "blocked", "no compiler_version recorded"
    if not route:
        return "blocked", f"chain {chain_id} is on no Etherscan chainlist and its explorer is not Blockscout"
    state, _ = source_provenance(row)
    if state == "unreachable":
        return "blocked", "the deploy commit is not in this clone - fetch full history"
    note = {"drifted": " (source from the deploy commit)", "unpinned": " (no deploy commit recorded)"}
    return "verify", f"{route[0]} vyper:{row['compiler_settings']['compiler_version']}{note.get(state, '')}"


def resolve_route(chain_id, config):
    """("etherscan", None) | ("blockscout", base_url) | None.

    Etherscan first: it covers most chains on one key, and Blockscout is the fallback for the
    12 it does not list rather than a competing choice.
    """
    if chain_id in etherscan_chains():
        return "etherscan", None
    base = blockscout_base(config)
    return ("blockscout", base) if base else None


def submit(row, address, chain_id, api_key):
    """POST one contract to Etherscan v2. Returns its message, or the receipt to poll."""
    path = source_path(row).relative_to(BASE_DIR).as_posix()
    form = {
        "module": "contract",
        "action": "verifysourcecode",
        "codeformat": "vyper-json",
        "sourceCode": json.dumps(standard_json(row)),
        "contractaddress": address,
        "contractname": f"{path}:{source_path(row).stem}",
        "compilerversion": f"vyper:{row['compiler_settings']['compiler_version']}",
        "optimizationUsed": "1" if optimised(row, source_path(row).read_text(encoding="utf-8")) else "0",
        "constructorArguments": row.get("constructor_args_encoded") or "",
    }
    url = f"{ETHERSCAN_API}?{urllib.parse.urlencode({'chainid': chain_id, 'apikey': api_key})}"
    request = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode())
    with urllib.request.urlopen(request, timeout=60) as response:
        answer = json.load(response)
    # status "1" means accepted for checking, not verified - the result is a guid to poll.
    return (answer.get("status") == "1", answer.get("result") or answer.get("message") or "no response")


def _json(url, data=None, headers=None, timeout=30):
    # Blockscout instances sit behind Cloudflare, which 403s the default Python-urllib agent.
    request = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def blockscout_base(config):
    """The explorer's API root if it is a Blockscout instance, else None.

    Asked rather than inferred from the hostname: only 3 of the 12 have "blockscout" in the
    name, the rest are white-labelled (explorer.inkonchain.com, explorer.plume.org).
    """
    base = (config.get("explorer_base_url") or "").rstrip("/")
    if not base:
        return None
    try:
        # Key presence, not a truthy value - an instance reporting a blank version is still one.
        return base if "backend_version" in _json(base + BLOCKSCOUT_VERSION, timeout=20) else None
    except Exception:
        return None


def blockscout_compiler(base, version):
    """Blockscout wants "v0.3.10+commit.91361694"; the deployment file records "0.3.10".

    The instance publishes the list it will accept, so the commit hash is looked up rather
    than hardcoded - they differ per release and a wrong one fails the build silently.
    """
    offered = _json(base + BLOCKSCOUT_CONFIG, timeout=25).get("vyper_compiler_versions") or []
    exact = [v for v in offered if v.startswith(f"v{version}+commit.")]
    return exact[0] if exact else None


def _multipart(fields, filename, content):
    """A form-data body, hand-rolled - the repo has no requests, and this is the one caller."""
    boundary = "----curve-core-verify"
    body = "".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        for name, value in fields.items()
    )
    body += (
        f'--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; filename="{filename}"\r\n'
        f"Content-Type: application/json\r\n\r\n{content}\r\n--{boundary}--\r\n"
    )
    return f"multipart/form-data; boundary={boundary}", body.encode()


def blockscout_verified(address, base):
    """Whether the explorer already holds source for this contract.

    Asked before submitting, because instances disagree about what a re-submission means: ink
    answers "verification started", tac answers a bare 404. Reading that 404 as a broken route
    reported 21 already-verified contracts as failures.
    """
    try:
        return bool(_json(base + BLOCKSCOUT_CONTRACT.format(address=address), timeout=25).get("is_verified"))
    except Exception:
        return False


def submit_blockscout(row, address, base, compiler):
    """Start verification. Blockscout queues it, so the reply is an acknowledgement."""
    content_type, body = _multipart(
        {"compiler_version": compiler, "license_type": "none"},
        source_path(row).name,
        json.dumps(standard_json(row)),
    )
    answer = _json(
        base + BLOCKSCOUT_VERIFY.format(address=address),
        data=body,
        headers={"Content-Type": content_type},
        timeout=60,
    )
    return answer.get("message") or "no response"


def poll_blockscout(address, base, attempts=10, pause=5):
    """Ask the contract itself whether it ended up verified."""
    for attempt in range(attempts):
        try:
            contract = _json(base + BLOCKSCOUT_CONTRACT.format(address=address), timeout=25)
        except Exception as exc:
            return f"{type(exc).__name__}: {str(exc)[:60]}"
        if contract.get("is_verified"):
            return "Pass - Verified"
        if attempt < attempts - 1:
            time.sleep(pause)
    return "not verified after waiting"


def outcome(answer):
    """What the explorer's reply actually means.

    It reports a failure as politely as a success, and says "verified" three different ways,
    so the verdict has to come from reading the answer - accepting the request means only that
    the request was well formed. A whole chain of "Unable to locate ContractCode" once exited 0.
    """
    text = (answer or "").lower()
    if "pass - verified" in text:
        return "verified"
    if "already verified" in text:
        return "already"
    return "failed"


def poll(guid, chain_id, api_key, attempts=10, pause=5):
    """Etherscan queues verification, so an accepted submission says nothing about the outcome."""
    query = {
        "chainid": chain_id,
        "module": "contract",
        "action": "checkverifystatus",
        "guid": guid,
        "apikey": api_key,
    }
    for attempt in range(attempts):
        with urllib.request.urlopen(f"{ETHERSCAN_API}?{urllib.parse.urlencode(query)}", timeout=30) as response:
            answer = json.load(response)
        result = answer.get("result") or ""
        if "pending" not in result.lower():
            return result
        if attempt < attempts - 1:
            time.sleep(pause)
    return "still pending"


@click.command("verify", short_help="verify recorded contracts on block explorers")
@click.argument("chain")
@click.option("--submit", "do_submit", is_flag=True, help="actually submit (needs ETHERSCAN_API_KEY)")
@click.option("--slot", metavar="NAME", default=None, help="one contract slot, e.g. helpers.router")
def verify_command(chain, do_submit, slot):
    """Report - and with --submit, perform - explorer verification for a chain."""
    deployments, _ = load_deployments(chain)
    deployments, out_of_scope = in_scope(deployments, chain_configs())
    if not deployments:
        raise click.UsageError(f"no deployment found for {chain!r}")

    key = next(iter(deployments))
    _, raw = deployments[key]
    config = raw.get("config") or {}
    chain_id = config.get("chain_id")
    route = resolve_route(chain_id, config)

    rows = [(name, row) for name, row in contract_rows(raw) if row.get("address")]
    if slot:
        rows = [(name, row) for name, row in rows if name == slot]
        if not rows:
            raise click.UsageError(f"no slot {slot!r} on {key}")

    api_key = os.environ.get("ETHERSCAN_API_KEY") or settings.ETHERSCAN_API_KEY
    if do_submit and route and route[0] == "etherscan" and not api_key:
        raise click.ClickException(
            "ETHERSCAN_API_KEY is not set - export it or put it in settings/env, or drop --submit"
        )

    # Looked up once, not per contract: every row on a chain shares a compiler list.
    compilers = {}

    click.echo(f"{key}  chain {chain_id}  {plural(len(rows), 'recorded contract')}\n")
    tally = defaultdict(int)
    for name, row in rows:
        action, detail = plan_row(name, row, chain_id, route)
        if action == "verify" and do_submit:
            time.sleep(THROTTLE)  # the free tier allows 5 calls a second
            try:
                if route[0] == "etherscan":
                    accepted, answer = submit(row, row["address"], chain_id, api_key)
                    detail = poll(answer, chain_id, api_key) if accepted else answer
                elif blockscout_verified(row["address"], route[1]):
                    detail = "already verified"
                else:
                    version = row["compiler_settings"]["compiler_version"]
                    if version not in compilers:
                        compilers[version] = blockscout_compiler(route[1], version)
                    if not compilers[version]:
                        raise RuntimeError(f"this Blockscout does not offer vyper {version}")
                    started = submit_blockscout(row, row["address"], route[1], compilers[version])
                    detail = poll_blockscout(row["address"], route[1]) if "started" in started.lower() else started
                action = outcome(detail)
            except urllib.error.HTTPError as exc:
                # The explorer answering is not our bug. 404 here is the route, not the address:
                # some instances advertise vyper-standard-input and never deployed the verifier.
                hint = " - this instance has no verification API" if exc.code == 404 else ""
                action, detail = "failed", f"explorer HTTP {exc.code}{hint}"
            except Exception as exc:
                # One contract must not abandon the rest - a whole-chain run is 20-odd of them.
                action, detail = "error", f"{type(exc).__name__}: {str(exc)[:80]}"
        # Counted after the submission, not before: the plan says what was attempted, the
        # reply says what happened, and the summary has to report the second one.
        tally[action] += 1
        click.echo(f"  {action:<8} {name:<52} {detail}")

    counts = ", ".join(f"{n} {name}" for name, n in sorted(tally.items()) if n)
    click.echo(f"\n{counts}")
    if not do_submit and tally["verify"]:
        click.echo("re-run with --submit to send them")
    if tally["failed"] or tally["error"]:
        raise SystemExit(1)
