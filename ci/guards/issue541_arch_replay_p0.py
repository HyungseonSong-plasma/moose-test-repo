#!/usr/bin/env python3
"""P0 static contract for two authorized, never-automatic ARCH P3 replay routes."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = "ci/baselines/issue541_arch_two_replay_20261115.json"
DD = ".github/workflows/issue541-arch-dd-p3-replay.yml"
S6 = ".github/workflows/issue541-arch-s6-p3-p4-replay.yml"
ORIGINAL = {
 "dd_json_two_step": (".github/workflows/issue402-dd-json-p3-smoke-once.yml", "068ef7f78b84b45dbf8c678522ada049d4a42b7a"),
 "s6_hybrid_two_case": (".github/workflows/issue402-hybrid-json-s6-p3-p4-once.yml", "485439a723584ca5bbc8632a86c53574b0b1eb9a"),
}
PHRASES = ("ISSUE541_DD_TWO_STEP_P3_APPROVED", "ISSUE541_S6_400W_100US_BOTH_CASES_APPROVED")

def need(condition, message):
 if not condition:
  raise ValueError(message)

def gitblob(content):
 raw = content.encode()
 return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def validate(m, dd, s6, old, surface):
 need(m["schema"] == "issue541.arch.two_p3_workflow_retention.v1", "SCHEMA")
 need(m["package"] == "ARCH" and m["authority_issue"] == 541 and m["retirement_issue"] == 535, "OWNER")
 need(m["overall"] == "TWO_REPLAY_CANDIDATES_STAGED_KEEP_HOLD" and m["immutable_p3_science_status"] == "SCIENCE_HOLD", "SCIENCE_HOLD")
 w = m["workflows"]
 need(set(w) == set(ORIGINAL), "WORKFLOW_SET")
 for name, (path, sha) in ORIGINAL.items():
  x = w[name]
  need(x["old_path"] == path and x["old_blob"] == sha and gitblob(old[name]) == sha, "ORIGINAL_BLOB_"+name)
  need(x["retirement"] == "KEEP_HOLD" and x["replay_proof"] == "NOT_EXECUTED_ON_CANDIDATE_EXACT_HEAD", "FALSE_RETIREMENT_"+name)
  need(x["backup"] == "INDEPENDENT_PRIVATE_COPY_READBACK_SHA256_VERIFIED" and x["archive_worm"] == "NOT_PROVEN", "BACKUP_"+name)
 d = w["dd_json_two_step"]
 need(d["historical_run_id"] == 43536220786 and d["historical_artifact_id"] == 14090046268, "DD_RUN")
 need(d["historical_original_zip_sha256"] == "d7ccb403173ef7a831e3ec9ad31a6c74c49c54dda20dfa839fe11b3331c572a4" and d["historical_original_zip_bytes"] == 1550, "DD_ZIP")
 need(d["backup_drive_file_id"] == "1kcw5K_gvmyeydTDuddIHs3VHZCMhQCaL" and d["native_p3_observed"] == "P3_NATIVE_SHEATH_SOLVE_UNRESOLVED", "DD_FAILURE")
 h = w["s6_hybrid_two_case"]
 need(h["historical_run_id"] == 43587161603 and h["p4"] == "DIAGNOSTIC_ONLY", "S6_SCOPE")
 cases = h["original_artifacts"]
 need(set(cases) == {"417", "941"}, "S6_CASE_SET")
 for case, aid, sha, size in (("417",14117371106,"563800ba985c3966d24aa0196fbe8ce46c9e1f5f1a1936685c6b5ff76c77a195",98686127),("941",14120049502,"87150a4b7db1647aa6a46731335ea1efa28a2998558cedd83df08d707c210d7e",98635164)):
  need(cases[case]["id"] == aid and cases[case]["sha256"] == sha and cases[case]["bytes"] == size, "S6_ZIP_"+case)
 for name, text, phrase, path in (("DD",dd,PHRASES[0],DD),("S6",s6,PHRASES[1],S6)):
  trigger = text.split("\non:\n",1)[1].split("\npermissions:",1)[0]
  need(trigger.startswith("  workflow_dispatch:\n") and "  push:" not in trigger and "  pull_request:" not in trigger and "  schedule:" not in trigger, name+"_EVENT")
  need("      source_sha:" in trigger and "      p3_approval:" in trigger and "        required: true" in trigger, name+"_INPUT")
  need('test "$APPROVAL" = "' + phrase + '"' in text and 'test "$REQUESTED_SHA" = "$GITHUB_SHA"' in text, name+"_AUTH")
  need(text.index("Fail closed") < text.index("uses: actions/checkout@"), name+"_GATE_ORDER")
  need("physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008" in text, name+"_OCI")
  need('"' + Path(path).name + '": {"workflow_dispatch"}' in surface, name+"_SURFACE")
 need("issue402_dd_json_p3_evidence/**" in dd and ".issue402_dd_json_p3_evidence/**" not in dd, "DD_HIDDEN_ARTIFACT")
 need("num_steps = 2" in dd and "run_issue402_dd_json_p3_smoke.py" in dd, "DD_P3")
 need("ci/guards/issue541_arch_dd_p3_result_gate.py" in dd and "--source-sha" in dd and "--binary" in dd, "DD_STRICT_OUTPUT_ORACLE")
 need("case: ['417', '941']" in s6 and "--authorize-p3" in s6 and "--hybrid-json" in s6, "S6_TWO_CASE")
 need('Path(os.environ["RUNNER_TEMP"])' in s6 and 'Path("$RUNNER_TEMP")' not in s6, "S6_TEMP_PATH")

def load():
 m = json.loads((ROOT/MANIFEST).read_text())
 dd, s6 = (ROOT/DD).read_text(), (ROOT/S6).read_text()
 old = {k:(ROOT/v[0]).read_text() for k,v in ORIGINAL.items()}
 surface = (ROOT/"ci/guards/workflow_surface_guard.py").read_text()
 validate(m,dd,s6,old,surface)
 return m,dd,s6,old,surface

def self_test():
 m,dd,s6,old,surface = load()
 cases = [(dd.replace("  workflow_dispatch:", "  push:",1),s6),
          (dd.replace('test "$APPROVAL" = "'+PHRASES[0]+'"',"true",1),s6),
          (dd.replace("issue402_dd_json_p3_evidence/**",".issue402_dd_json_p3_evidence/**",1),s6),
          (dd,s6.replace("case: ['417', '941']","case: ['417']",1)),
          (dd,s6.replace('Path(os.environ["RUNNER_TEMP"])','Path("$RUNNER_TEMP")',1)),
          (dd,s6.replace('test "$APPROVAL" = "'+PHRASES[1]+'"',"true",1)),
          (dd.replace("ci/guards/issue541_arch_dd_p3_result_gate.py", "missing_dd_oracle", 1),s6)]
 for i,(a,b) in enumerate(cases):
  try: validate(m,a,b,old,surface)
  except ValueError: continue
  raise ValueError("UNREJECTED_WORKFLOW_MUTATION_"+str(i))
 for i,(key,field,value) in enumerate((("dd_json_two_step","retirement","RETIRED_VERIFIED"),("dd_json_two_step","replay_proof","PASS"),("dd_json_two_step","historical_original_zip_sha256","0"*64),("s6_hybrid_two_case","p4","SCIENCE_PASS"))):
  mutant=copy.deepcopy(m); mutant["workflows"][key][field]=value
  try: validate(mutant,dd,s6,old,surface)
  except ValueError: continue
  raise ValueError("UNREJECTED_RECEIPT_MUTATION_"+str(i))
 print("ISSUE541_ARCH_P3_NEGATIVE_MUTATIONS_11_REJECTED")

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--self-test",action="store_true")
 ap.add_argument("--check",action="store_true")
 args=ap.parse_args()
 try:
  if args.self_test: self_test()
  if args.check or not args.self_test:
   load(); print("ISSUE541_ARCH_P3_REPLAY_P0_PASS; REPLAY_HOLD; SCIENCE_HOLD")
 except (KeyError,ValueError,OSError) as exc:
  print("ISSUE541_ARCH_P3_REPLAY_P0_FAIL",exc); return 1
 return 0

if __name__ == "__main__":
 raise SystemExit(main())
