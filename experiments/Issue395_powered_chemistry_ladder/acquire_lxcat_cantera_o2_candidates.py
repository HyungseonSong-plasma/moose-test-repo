#!/usr/bin/env python3
"""Local-only inspection/extraction of the PUBLIC Cantera Phelps demonstration dataset.

Source: https://github.com/Cantera/cantera-example-data/blob/main/air-plasma-Phelps.yaml
Original reference: LXCat Phelps (retrieved 2025-08-01 per demo header).
This is NOT original-HPEM data, NOT verified original LXCat, and not solver-ready.
The original file says "generator: lxcat2yaml + manual edits".
The original LXCat site's terms do not permit third-party redistribution.
Do not commit exported numeric tables to a public repository.

The parser is intentionally specific to this provenance-pinned demo YAML and
uses only the Python stdlib; no network access or third-party YAML dependency.
"""
from __future__ import annotations

import argparse
import ast
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re

DEMO_URL = "https://github.com/Cantera/cantera-example-data/blob/main/air-plasma-Phelps.yaml"
ORIGIN = "https://master.lxcat.net/contributors/"
REDISTRIBUTION = "https://us.lxcat.net/instructions/redistribution.php"

# This is Cantera's public Git blob id, NOT a SHA-256 checksum of bytes.
DEMO_GIT_BLOB = "df3b84eae6ae503fa46f9bfa14ec4469d615fe03"

# Canonical 33-row registry identifiers. A heading/name/energy similarity
# establishes a candidate source channel, not identity of physical products.
MAPPINGS = (
    ("KIN-M01", "target", "O2", "", "effective", None),
    ("EI-401", "target", "O2", "O^-+O", "attachment", 0.0),
    ("KIN-V01", "target", "O2", "O2(v1)", "excitation", 0.19),
    ("KIN-V02", "target", "O2", "O2(v2)", "excitation", 0.38),
    ("KIN-V03", "target", "O2", "O2(v3)", "excitation", 0.57),
    ("KIN-V04", "target", "O2", "O2(v4)", "excitation", 0.75),
    ("KIN-V01R", "target", "O2", "O2(v1res)", "excitation", 0.19),
    ("KIN-V02R", "target", "O2", "O2(v2res)", "excitation", 0.38),
    ("EI-407", "target", "O2", "O2(a1)", "excitation", 0.977),
    ("EI-411", "target", "O2", "O2(4.5eV)", "excitation", 4.5),
    ("EI-412", "target", "O2", "O2(6.0eV)", "excitation", 6.0),
    ("EI-413", "target", "O2", "O2(8.4eV)", "excitation", 8.4),
    ("EI-414", "target", "O2", "O2(9.97eV)", "excitation", 9.97),
    ("EI-415", "equation", "O2 + Electron => Electron + Electron + O2+",
     "", "reaction", 12.06),
)
assert len(MAPPINGS) == len({row[0] for row in MAPPINGS}) == 14

EXCLUDED_NAMES = {"O2(rot)", "O2(b1)", "O2(130nm)", "O2-"}
FORBIDDEN_CHEMISTRY = {"O2 + Electron => O2-", "O2(rot)", "O2(b1)", "O2(130nm)"}


def blocks(text: str) -> list[dict]:
    if "generator: lxcat2yaml + manual edits" not in text:
        raise ValueError("requires Cantera Phelps demo with manual-edit provenance")
    chunks = re.findall(
        r"(?ms)^-\s+(target|equation):\s*([^\n]+)\n(.*?)(?=^-\s+(?:target|equation):|\Z)",
        text,
    )
    out: list[dict] = []
    for name, subject, body in chunks:
        prop = lambda key: (re.search(rf"(?m)^\s+{re.escape(key)}:\s*([^\n]+)", body) or [None, ""])[1].strip()
        def values(key: str) -> list[float]:
            m = re.search(rf"(?s)^\s+{re.escape(key)}:\s*(\[[^\]]*\])", body, re.M)
            if not m:
                raise ValueError(f"source block {subject}: no numeric {key}")
            result = ast.literal_eval(m.group(1))
            if not isinstance(result, list) or any(not isinstance(x, (int, float)) for x in result):
                raise ValueError(f"source block {subject}: nonnumeric {key}")
            return [float(x) for x in result]
        en = values("energy-levels")
        sig = values("cross-sections")
        if len(en) != len(sig) or len(en) < 2 or any(v < 0 for v in en + sig):
            raise ValueError(f"source block {subject}: invalid energy/sigma arrays")
        if any(en[i] <= en[i - 1] for i in range(1, len(en))):
            raise ValueError(f"source block {subject}: energy must strictly increase")
        threshold = float(prop("threshold")) if prop("threshold") else None
        out.append({"block": name, "subject": subject.strip(), "product": prop("product"),
                    "kind": prop("kind") or "reaction", "threshold_eV": threshold,
                    "energy_eV": en, "sigma_m2": sig})
    return out


def select(text: str) -> dict:
    raw = blocks(text)
    selected = {}
    for row_id, name, subject, product, kind, threshold in MAPPINGS:
        matches = [b for b in raw if b["block"] == name and b["subject"] == subject
                   and b["product"] == product and b["kind"] == kind]
        if len(matches) != 1:
            raise ValueError(f"{row_id}: wanted one source candidate, got {len(matches)}")
        b = matches[0]
        if b["threshold_eV"] != threshold:
            raise ValueError(f"{row_id}: demo threshold changed; review required")
        selected[row_id] = b
    if len(selected) != 14:
        raise ValueError("incomplete source selection")
    if any(b["subject"] in FORBIDDEN_CHEMISTRY or b["product"] in EXCLUDED_NAMES
           for b in selected.values()):
        raise ValueError("excluded reaction imported")
    # These are source-identity checks, not verification that the *HPEM*
    # reaction products are accurately represented.
    return selected


def extract(source: Path, dest: Path, retrieved_on: str) -> dict:
    if date.fromisoformat(retrieved_on) > date.today():
        raise ValueError("retrieval date cannot be future")
    source = source.resolve(strict=True)
    dest = dest.resolve()
    if source.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError("need a locally downloaded Cantera demo YAML")
    if dest == source or dest in source.parents:
        raise ValueError("source/output must not overlap")
    data = source.read_bytes()
    records = select(data.decode("utf-8"))
    files = [dest / f"{key}_candidate.csv" for key in records]
    manifest_path = dest / "lxcat_cantera_o2_candidate_manifest.json"
    if any(f.exists() for f in files + [manifest_path]):
        raise FileExistsError("refuse to overwrite existing local candidate files")
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {
        "status": "CANDEMO_NUMERIC_CANDIDATE_NOT_ORIGINAL_LXCAT_OR_HPEM_NOT_SOLVER_READY",
        "original_lxcat_source": ORIGIN,
        "demo_url": DEMO_URL, "demo_blob_sha": DEMO_GIT_BLOB,
        "demo_retrieval_date_reported": "2025-08-01",
        "locally_downloaded_on": retrieved_on,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "redistribution_terms": REDISTRIBUTION,
        "record_count": len(records),
        "excluded": ["three-body attachment", "KIN-R01", "KIN-E01", "KIN-E02"],
        "channels": {},
    }
    for key, f in zip(records, files):
        b = records[key]
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(("energy_eV", "cross_section_m2"))
        writer.writerows(zip(b["energy_eV"], b["sigma_m2"]))
        payload = buf.getvalue().encode("utf-8")
        f.write_bytes(payload)
        manifest["channels"][key] = {
            "candidate_process": b["subject"] + (" -> " + b["product"] if b["product"] else ""),
            "source_kind": b["kind"], "source_threshold_eV": b["threshold_eV"],
            "points": len(b["energy_eV"]), "energy_min_eV": b["energy_eV"][0],
            "energy_max_eV": b["energy_eV"][-1], "sha256": hashlib.sha256(payload).hexdigest(),
            "local_path": f.name, "solver_accepted": False, "hpep_equivalence": False,
        }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--retrieved-on", required=True)
    a = p.parse_args()
    v = extract(a.source, a.output_dir, a.retrieved_on)
    print(f"SOURCE_NUMERIC_CANDIDATES={v['record_count']} (NOT EEDF/SCIENCE READY)")
    print(f"SOURCE_SHA256={v['source_sha256']}")


if __name__ == "__main__":
    main()
