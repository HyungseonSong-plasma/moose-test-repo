"""Reproduce the *curated* v0.4 exact-blob witness/cue contrast; not an AST scan."""
from __future__ import annotations

import json
from pathlib import Path

from libs.code_understandability.definition_metrics import NameCue
from .measure import assess_from_source_report


def replay(snapshot: dict) -> dict:
    if snapshot.get("schema_version") != "0.5-curated-anchored-frozen-cues":
        raise ValueError("INVALID_FROZEN_CUE_SNAPSHOT")
    rows = snapshot["cases"]
    cue_sets = {}
    for row in rows:
        meta = row["cues"]
        folder = row["folder"]
        sha = meta["init_blob"]
        init_ref = folder + "/__init__.py@" + sha
        cue_sets[row["target"]] = tuple([
            NameCue("name", meta["name"], 0, folder),
            NameCue("parent", meta["parent"], 1, folder.rsplit("/", 1)[0]),
        ] + [NameCue("module:" + m, m, 2, folder + "/" + m + ".py")
             for m in meta["modules"]] + [
                 NameCue(f"api:{j}:{text}", text, 3, init_ref)
                 for j, text in enumerate(meta["api"])
             ])
    v04={"schema_version":"0.4","source_provider":snapshot["source_provider"],
         "exact_source_revision":snapshot["source_revision"],"readme_used":False,
         "target_name_used_for_definition_inference":False,"results":rows}
    result=assess_from_source_report(v04,cue_sets)
    result["input_evidence_kind"] = snapshot["reference_kind"]
    result["full_source_reparsed"] = False
    # JSON wire normalization: tuples in typed assessments become arrays.
    return json.loads(json.dumps(result, ensure_ascii=False))


def main() -> None:
    root=Path(__file__).parent
    snapshot=json.loads((root/"frozen_reference_cues.json").read_text())
    result=replay(snapshot)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
