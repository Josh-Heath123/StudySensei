"""Print [{name, version, license}] for every package in the current Python environment.

Used by scripts/check-licenses.mjs (run with apps/api's environment). The licence is the
PEP 639 expression, else the License field's first line, else the trove classifiers.
"""

import json
from importlib.metadata import distributions

out = []
for dist in distributions():
    meta = dist.metadata
    lic = meta.get("License-Expression") or ""
    if not lic and meta.get("License") and len(meta["License"]) < 200:
        lic = meta["License"].strip().splitlines()[0]
    if not lic or lic.upper() == "UNKNOWN":
        names = [
            c.split("::")[-1].strip()
            for c in meta.get_all("Classifier") or []
            if c.startswith("License ::") and c.split("::")[-1].strip() != "OSI Approved"
        ]
        lic = " OR ".join(names)
    out.append({"name": meta["Name"], "version": dist.version, "license": lic})
print(json.dumps(out))
