"""Read-only reproducible DEB/MRC snapshot measurement.

Run from repository root with PYTHONPATH=. and optional --root for live checkout
source validation. Frozen snapshot was extracted from GitHub at exact source SHA.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from physics_harness.code.analysis.definition_inference import (
    SourceSymbol, extract_public_symbols_from_folder, measure_folder,
)




def run(manifest: dict, root: Path | None = None) -> dict:
    if root is not None:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        if head != manifest["revision"]:
            raise ValueError(f"SOURCE_REVISION_MISMATCH:{head}")
    out=[]
    for target in manifest["targets"]:
        if root is None:
            evidence_ref = target["path"] + "/__init__.py@" + target["blob_sha"]
            symbols=tuple(SourceSymbol(s, evidence_ref, "PUBLIC_API") for s in target["public_symbols"])
        else:
            symbols=extract_public_symbols_from_folder(root,target["path"])
            if [x.identifier for x in symbols] != target["public_symbols"]:
                raise ValueError(f"PUBLIC_API_SNAPSHOT_MISMATCH:{target['target_id']}")
        result=measure_folder(target["path"], symbols, tuple(target["module_names"]))
        result["target_id"]=target["target_id"]
        result["source_revision"]=manifest["revision"]
        out.append(result)
    return {"schema_version":"0.2", "revision":manifest["revision"],
            "measurement_type":"exploratory_lexical_source_proxy",
            "readme_used":False, "target_name_used_for_role_inference":False,
            "source_mode":"exact_head_checkout" if root else "frozen_public_api_snapshot",
            "results":out}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, default=Path(__file__).with_name("pilot_inputs.json"))
    p.add_argument("--root", type=Path)
    p.add_argument("--output", type=Path)
    args=p.parse_args()
    result=run(json.loads(args.manifest.read_text()), args.root)
    contents=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if args.output:
        args.output.write_text(contents)
    else:
        print(contents)


if __name__ == "__main__":
    main()
