#!/usr/bin/env python3
"""Known-vulnerability check for the locked dependencies of this repository.

Reads `backend/uv.lock` and `admin/pnpm-lock.yaml` (the files that actually decide what runs in
production), asks the OSV database about every locked name@version, and prints one line per
advisory with the fixed version. Exits non-zero when an advisory is not explicitly ignored, so it
can gate CI.

It talks to OSV directly instead of going through `pip-audit` / `pnpm audit` on purpose:
`pnpm audit` needs an audit endpoint on the configured registry, and a mirror registry (for
example `registry.npmmirror.com`) does not expose one, so `pnpm audit` fails while looking like a
clean run. OSV is registry-independent.

Usage:
    scripts/check-vulnerabilities.py            # gate: non-zero on any unignored advisory
    scripts/check-vulnerabilities.py --list     # only print what was scanned, then exit
    scripts/check-vulnerabilities.py --offline  # parse the lockfiles only (no network)

Advisories that are known and accepted go in `.github/osv-ignore.txt`, one `ID  # reason` per
line; a line without a reason is rejected. The id may be the OSV id that the scan prints, a GHSA
or PYSEC id for the same advisory, or its CVE alias.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UV_LOCK = ROOT / "backend" / "uv.lock"
PNPM_LOCK = ROOT / "admin" / "pnpm-lock.yaml"
IGNORE_FILE = ROOT / ".github" / "osv-ignore.txt"
OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/{}"
TIMEOUT_S = 60
# querybatch takes at most 1000 queries per request; stay well under it so a growing pnpm-lock
# cannot turn the gate into an error.
BATCH_SIZE = 500


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def parse_uv_lock(path: Path) -> list[tuple[str, str]]:
    """[[package]] blocks: name = "x" then version = "y"."""
    blocks = path.read_text().split("[[package]]")[1:]
    packages = []
    for block in blocks:
        name = re.search(r'^name = "([^"]+)"', block, re.M)
        version = re.search(r'^version = "([^"]+)"', block, re.M)
        if name and version:
            packages.append((name.group(1), version.group(1)))
    return packages


def parse_pnpm_lock(path: Path) -> list[tuple[str, str]]:
    """lockfileVersion 9 lists resolved entries as `'name@version':` (scoped names quoted)."""
    pattern = re.compile(
        r"^\s{2}'?/?(?P<name>@?[^\s'@]+(?:/[^\s'@]+)?)@(?P<version>[^'():\s]+)'?:\s*$",
        re.M,
    )
    packages = {
        (m["name"], m["version"])
        for m in pattern.finditer(path.read_text())
        if re.fullmatch(r"\d[\w.+-]*", m["version"])
    }
    return sorted(packages)


def load_ignores(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    ignored: dict[str, str] = {}
    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        advisory_id, _, reason = line.partition("#")
        advisory_id, reason = advisory_id.strip(), reason.strip()
        if not advisory_id or not reason:
            fail(f"{path.relative_to(ROOT)}:{number}: expected `ID  # reason`")
        ignored[advisory_id] = reason
    return ignored


def osv_post(url: str, payload: dict) -> dict:
    request = urllib.request.Request(  # noqa: S310 - https
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 - https
            return json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        fail(f"cannot reach {url}: {exc}")


def osv_get(advisory_id: str) -> dict:
    try:
        with urllib.request.urlopen(  # noqa: S310 - https
            OSV_VULN.format(advisory_id), timeout=TIMEOUT_S
        ) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        fail(f"cannot reach OSV for {advisory_id}: {exc}")


def query_osv(packages: list[tuple[str, str]], ecosystem: str) -> list[dict]:
    hits: list[dict] = []
    for start in range(0, len(packages), BATCH_SIZE):
        chunk = packages[start : start + BATCH_SIZE]
        batch = osv_post(
            OSV_BATCH,
            {"queries": [_query(name, version, ecosystem) for name, version in chunk]},
        )
        for (name, version), result in zip(chunk, batch.get("results", []), strict=True):
            for advisory_id in advisory_ids(result, name, version, ecosystem):
                hits.append(
                    {
                        "name": name,
                        "version": version,
                        "ecosystem": ecosystem,
                        "id": advisory_id,
                    }
                )
    return hits


def _query(name: str, version: str, ecosystem: str, page_token: str | None = None) -> dict:
    query = {"package": {"name": name, "ecosystem": ecosystem}, "version": version}
    if page_token:
        query["page_token"] = page_token
    return query


def advisory_ids(result: dict, name: str, version: str, ecosystem: str) -> list[str]:
    """Every advisory id for one package, following next_page_token instead of dropping them."""
    ids = [vuln["id"] for vuln in result.get("vulns", [])]
    token = result.get("next_page_token")
    seen_tokens = {token}
    while token:
        page = osv_post(OSV_BATCH, {"queries": [_query(name, version, ecosystem, token)]})
        result = (page.get("results") or [{}])[0]
        ids += [vuln["id"] for vuln in result.get("vulns", [])]
        token = result.get("next_page_token")
        if token in seen_tokens:
            fail(f"OSV kept returning page_token {token!r} for {name}@{version}")
        seen_tokens.add(token)
    return ids


def normalise(name: str, ecosystem: str) -> str:
    """PyPI names are case-insensitive and treat runs of -_. as one dash (PEP 503)."""
    if ecosystem != "PyPI":
        return name
    return re.sub(r"[-_.]+", "-", name).lower()


def enrich(hits: list[dict]) -> None:
    """Fill severity, fixed versions and summary from each advisory's own record."""
    for hit in hits:
        record = osv_get(hit["id"])
        severities = [s.get("score", "") for s in record.get("severity", []) if s.get("score")]
        database_severity = record.get("database_specific", {}).get("severity", "")
        hit["severity"] = severities[0] if severities else str(database_severity)
        wanted = normalise(hit["name"], hit["ecosystem"])
        fixed: set[str] = set()
        for affected in record.get("affected", []):
            package_name = affected.get("package", {}).get("name", "")
            if normalise(package_name, hit["ecosystem"]) != wanted:
                continue
            for version_range in affected.get("ranges", []):
                for event in version_range.get("events", []):
                    if "fixed" in event:
                        fixed.add(event["fixed"])
        hit["fixed"] = ", ".join(sorted(fixed)) or "no fix published"
        hit["aliases"] = [a for a in record.get("aliases", []) if a.startswith("CVE")]
        hit["summary"] = (record.get("summary") or "").strip()


def dedupe(hits: list[dict]) -> list[dict]:
    """One advisory can arrive twice (GHSA and PYSEC for the same CVE); keep the GHSA entry.

    Every id from the collapsed duplicates stays on the kept hit, so an ignore entry written with
    the PYSEC id, the CVE, or the GHSA id all match the same advisory.
    """
    groups: dict[tuple[str, str, str, str], list[dict]] = {}
    for hit in hits:
        key = (
            hit["ecosystem"],
            hit["name"],
            hit["version"],
            hit["aliases"][0] if hit["aliases"] else hit["id"],
        )
        groups.setdefault(key, []).append(hit)

    kept = []
    for group in groups.values():
        chosen = next((h for h in group if h["id"].startswith("GHSA")), group[0])
        chosen["ids"] = {h["id"] for h in group}
        kept.append(chosen)
    return kept


def ignore_keys(hit: dict) -> set[str]:
    """Ids and CVE aliases that `.github/osv-ignore.txt` may use to name this advisory."""
    return {*hit["ids"], *hit["aliases"]}


def main(argv: list[str]) -> int:
    offline = "--offline" in argv
    list_only = "--list" in argv

    python_packages = parse_uv_lock(UV_LOCK)
    js_packages = parse_pnpm_lock(PNPM_LOCK)
    # Guard against a lockfile format change silently turning this gate into a no-op.
    if len(python_packages) < 20:
        fail(f"parsed only {len(python_packages)} packages from {UV_LOCK.name}; format changed?")
    if len(js_packages) < 50:
        fail(f"parsed only {len(js_packages)} packages from {PNPM_LOCK.name}; format changed?")

    print(f"scanned {len(python_packages)} Python and {len(js_packages)} npm locked packages")
    if list_only or offline:
        return 0

    # Loaded before the early return: a malformed line has to fail even when the scan is clean,
    # and a clean scan is exactly when every ignore entry is stale.
    ignored = load_ignores(IGNORE_FILE)

    hits = query_osv(python_packages, "PyPI") + query_osv(js_packages, "npm")
    if not hits:
        print("no known vulnerabilities")
    enrich(hits)
    hits = dedupe(hits)

    unignored = []
    for hit in sorted(hits, key=lambda h: (h["name"], h["id"])):
        cve = f" ({', '.join(hit['aliases'])})" if hit["aliases"] else ""
        matched = sorted(ignore_keys(hit) & ignored.keys())
        if matched:
            print(f"ignored  {hit['name']}@{hit['version']}  {hit['id']}{cve}")
            print(f"         matched ignore entry {matched[0]}")
            print(f"         reason: {ignored[matched[0]]}")
            continue
        unignored.append(hit)
        print(f"found    {hit['name']}@{hit['version']}  {hit['id']}{cve}")
        print(f"         fixed in: {hit['fixed']}")
        if hit["severity"]:
            print(f"         severity: {hit['severity']}")
        if hit["summary"]:
            print(f"         {hit['summary']}")

    known = {key for hit in hits for key in ignore_keys(hit)}
    for advisory_id in sorted(set(ignored) - known):
        print(
            f"note: {advisory_id} is ignored but no longer matches a locked package; drop the entry"
        )

    if unignored:
        print(
            f"\n{len(unignored)} advisory(ies) not ignored: bump the dependency or add the "
            f"advisory to .github/osv-ignore.txt with a reason"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
