#!/usr/bin/env python3
"""P0 static contract for two authorized, never-automatic ARCH P3 replay routes."""
import argparse
import copy
import hashlib
import json
import subprocess
import sys
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
S6_RETIREMENT_DOC = "experiments/Issue402_plasma_dsl_g1/chemistry/README.md"
S6_STAGED_MARKERS = ("issue541-arch-s6-p3-p4-replay.yml",
                     "485439a723584ca5bbc8632a86c53574b0b1eb9a",
                     "manual-only", "retirement proposal",
                     "current default branch")

def require_s6_staged_receipt(doc):
 for marker in S6_STAGED_MARKERS:
  need(marker in doc, "S6_STAGED_ABSENCE_RECEIPT_MISSING_" + marker)


def need(condition, message):
 if not condition:
  raise ValueError(message)

def gitblob(content):
 raw = content.encode()
 return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

DD_ARCHIVE_SOURCE = "docs/development/archive/issue402-dd-json-p3-smoke-once.yml.txt"
DD_STAGE_MANIFEST = "ci/baselines/issue541_dd_p3_retirement_20261116.json"
DD_STAGE_DOC = "docs/development/2026-11-16_issue541_dd_p3_original_retirement_custody.md"

def require_dd_staged_receipt():
  m = json.loads((ROOT/DD_STAGE_MANIFEST).read_text(encoding="utf-8"))
  archived = (ROOT/DD_ARCHIVE_SOURCE).read_text(encoding="utf-8")
  doc = (ROOT/DD_STAGE_DOC).read_text(encoding="utf-8")
  need(m["schema"] == "issue541.dd_p3.original_staged_retirement.v1"
       and m["state"] == "STAGED_DELETE_KEEP_HOLD_INTEGRATION"
       and m["science"] == "SCIENCE_HOLD" and m["final_retired_verified"] is False,
       "DD_STAGE_STATUS")
  need(m["original"]["git_blob"] == ORIGINAL["dd_json_two_step"][1]
       and m["original"]["source_copy_path"] == DD_ARCHIVE_SOURCE
       and gitblob(archived) == ORIGINAL["dd_json_two_step"][1],
       "DD_ORIGINAL_EXACT_ARCHIVED_BLOB")
  need(m["dd_native_p3"]["run_id"] == 43911477519
       and m["dd_native_p3"]["two_timesteps_completed"] is True
       and m["dd_native_p3"]["sha256"] == "1e2c52623a0ba1936a8c44ae69a1f2c273526a5b96048325288f6854de1d47da",
       "DD_TWO_STEP_P3_RECEIPT")
  need(m["custody"]["readback"] == "REMOTE_DOWNLOAD_SHA256_AND_ZIP_CRC_MATCH_ALL_THREE"
       and m["custody"]["worm_lock"] == "NOT_PROVEN", "DD_CUSTODY_NOT_WORM")
  need(all(x in doc for x in (ORIGINAL["dd_json_two_step"][1], "manual-only",
                              "registered on the current default branch", "SCIENCE_HOLD")),
       "DD_ARCHIVAL_DOCUMENT")
  replay=(ROOT/DD).read_text(encoding="utf-8")
  trigger=replay.split("\non:\n",1)[1].split("\npermissions:",1)[0]
  need(trigger.startswith("  workflow_dispatch:\n")
       and all(x not in trigger for x in ("  push:", "  pull_request:", "  schedule:"))
       and PHRASES[0] in replay and 'test "$REQUESTED_SHA" = "$GITHUB_SHA"' in replay,
       "DD_EXACT_SOURCE_MANUAL_ONLY")


def validate(m, dd, s6, old, surface):
 need(m["schema"] == "issue541.arch.two_p3_workflow_retention.v1", "SCHEMA")
 need(m["package"] == "ARCH" and m["authority_issue"] == 541 and m["retirement_issue"] == 535, "OWNER")
 need(m["overall"] == "TWO_REPLAY_CANDIDATES_STAGED_KEEP_HOLD" and m["immutable_p3_science_status"] == "SCIENCE_HOLD", "SCIENCE_HOLD")
 w = m["workflows"]
 need(set(w) == set(ORIGINAL), "WORKFLOW_SET")
 for name, (path, sha) in ORIGINAL.items():
  x = w[name]
  original_text = old[name]
  need(x["old_path"] == path and x["old_blob"] == sha, "ORIGINAL_ID_"+name)
  if original_text is None:
   if name == "dd_json_two_step":
    require_dd_staged_receipt()
   else:
    need(name == "s6_hybrid_two_case", "UNAPPROVED_ORIGINAL_ABSENCE_"+name)
    require_s6_staged_receipt((ROOT/S6_RETIREMENT_DOC).read_text())
  else:
   need(gitblob(original_text) == sha, "ORIGINAL_BLOB_"+name)
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
 need('trap restore_evidence_ownership EXIT' in dd and
      'sudo chown -R "$(id -u):$(id -g)" issue402_dd_json_p3_evidence' in dd and
      '          restore_evidence_ownership\n          test -w issue402_dd_json_p3_evidence' in dd and
      dd.index("test -w issue402_dd_json_p3_evidence") <
      dd.index("python3 ci/guards/issue541_arch_dd_p3_result_gate.py"),
      "DD_ROOT_OWNED_EVIDENCE_UNWRITABLE")
 need("case: ['417', '941']" in s6 and "--authorize-p3" in s6 and "--hybrid-json" in s6, "S6_TWO_CASE")
 need('Path(os.environ["RUNNER_TEMP"])' in s6 and 'Path("$RUNNER_TEMP")' not in s6, "S6_TEMP_PATH")

def load():
 m = json.loads((ROOT/MANIFEST).read_text())
 dd, s6 = (ROOT/DD).read_text(), (ROOT/S6).read_text()
 old = {}
 for name, (path, sha) in ORIGINAL.items():
  file = ROOT/path
  if file.is_file():
   old[name] = file.read_text()
  elif name == "s6_hybrid_two_case":
   # Integration-only staged absence needs a separately pinned historical
   # blob and a documented maintained manual replacement, not a guard bypass.
   require_s6_staged_receipt((ROOT/S6_RETIREMENT_DOC).read_text())
   old[name] = None
  elif name == "dd_json_two_step":
   require_dd_staged_receipt()
   old[name] = None
  else:
   need(False, "UNEXPECTED_ORIGINAL_ABSENCE_"+name)
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
          (dd.replace("ci/guards/issue541_arch_dd_p3_result_gate.py", "missing_dd_oracle", 1),s6),
          (dd.replace("trap restore_evidence_ownership EXIT","trap : EXIT",1),s6),
          (dd.replace('sudo chown -R "$(id -u):$(id -g)" issue402_dd_json_p3_evidence',"true",1),s6),
          (dd.replace('          restore_evidence_ownership\n          test -w issue402_dd_json_p3_evidence',
                      '          true\n          test -w issue402_dd_json_p3_evidence',1),s6)]
 for i,(a,b) in enumerate(cases):
  try: validate(m,a,b,old,surface)
  except ValueError: continue
  raise ValueError("UNREJECTED_WORKFLOW_MUTATION_"+str(i))
 for i,(key,field,value) in enumerate((("dd_json_two_step","retirement","RETIRED_VERIFIED"),("dd_json_two_step","replay_proof","PASS"),("dd_json_two_step","historical_original_zip_sha256","0"*64),("s6_hybrid_two_case","p4","SCIENCE_PASS"))):
  mutant=copy.deepcopy(m); mutant["workflows"][key][field]=value
  try: validate(mutant,dd,s6,old,surface)
  except ValueError: continue
  raise ValueError("UNREJECTED_RECEIPT_MUTATION_"+str(i))
 runner = ROOT/"physics_app/ci/run_issue402_dd_json_p3_smoke.py"
 result = subprocess.run(
  [sys.executable, str(runner), "--self-test"],
  cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
  text=True, timeout=30, check=False)
 need(result.returncode == 0 and
      "ISSUE541_DD_P3_FAILURE_DIAGNOSTIC_NEGATIVE_2_PASS_NO_NATIVE"
      in result.stdout,
      "DD_P3_RUNNER_FAILURE_CLASSIFICATION_SELF_TEST")
 print(result.stdout.strip())
 if old["dd_json_two_step"] is None:
  forged=dict(old);forged["dd_json_two_step"]="forged original"
  try: validate(m,dd,s6,forged,surface)
  except ValueError: pass
  else: raise ValueError("UNREJECTED_FORGED_DD_ORIGINAL")
  print("ISSUE541_ARCH_DD_STAGED_ABSENCE_NEGATIVE_REJECTED")
 if old["s6_hybrid_two_case"] is None:
  # Fail closed on forged original bytes or missing rollback/replacement proof.
  forged = dict(old)
  forged["s6_hybrid_two_case"] = "forged S6 source"
  try: validate(m,dd,s6,forged,surface)
  except ValueError: pass
  else: raise ValueError("UNREJECTED_FORGED_ORIGINAL_S6")
  source_doc = (ROOT/S6_RETIREMENT_DOC).read_text()
  for marker in S6_STAGED_MARKERS:
   try: require_s6_staged_receipt(source_doc.replace(marker, "tampered", 1))
   except ValueError: continue
   raise ValueError("UNREJECTED_S6_RETIREMENT_RECEIPT_MUTATION_" + marker)
  print("ISSUE541_ARCH_S6_STAGED_ABSENCE_NEGATIVE_6_REJECTED")
 print("ISSUE541_ARCH_P3_NEGATIVE_MUTATIONS_14_REJECTED")

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
