"""Cache connectivity probes for the user-authorized public alternatives."""
import hashlib
import json
from phase0_check import ROOT, probe, save

for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
    if not line.startswith("CANDIDATE_RPC_"):
        continue
    name, url = line.split("=", 1)
    path = ROOT / "data" / "private" / "rpc" / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if path.exists():
        result = json.loads(path.read_text(encoding="utf-8"))
    else:
        result = probe(url)
        save(path, result)
    print(json.dumps({"candidate": name, **result}), flush=True)
