"""Inspect tracked/stageable files without printing any credential values."""
import json
import re
import subprocess
from urllib.parse import parse_qsl, unquote, urlsplit
from phase0_check import ROOT
from rpc_transport import config


def main():
    raw = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT)
    files = sorted(set(raw.decode().split("\0")) - {""})
    needles = []
    for name, value in config().items():
        if not value:
            continue
        needles.append((name, value.encode()))
        if value.startswith(("https://", "http://")):
            parts = urlsplit(value)
            components = [parts.username, parts.password] + [v for _, v in parse_qsl(parts.query)]
            components += [x for x in parts.path.split("/") if len(x) >= 24]
            needles.extend((name + " credential component", unquote(v).encode()) for v in components if v)
    findings = []
    for name in files:
        data = (ROOT / name).read_bytes()
        for label, needle in needles:
            if needle in data:
                findings.append({"file": name, "matched_variable": label})
    cache_findings = []
    caches = list((ROOT / "data/rpc").glob("*.json"))
    for path in caches:
        data = path.read_text(encoding="utf-8")
        json.loads(data)
        if re.search(r"https?://|\"(?:api[_-]?key|private[_-]?key|authorization|password|secret|access_token)\"\s*:", data, re.I):
            cache_findings.append(str(path.relative_to(ROOT)))
    forbidden = [name for name in files if name == ".env" or (name.startswith(".env.") and name != ".env.example") or name.startswith((".tools/", "data/private/", "out/", "cache/", ".venv/")) or "__pycache__/" in name]
    result = {"checked_files": len(files), "checked_rpc_cache_files": len(caches),
              "credential_matches": findings, "rpc_cache_url_or_credential_fields": cache_findings,
              "forbidden_files": forbidden, "passed": not (findings or cache_findings or forbidden)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
