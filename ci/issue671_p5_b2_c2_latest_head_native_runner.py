#!/usr/bin/env python3
"""One-shot exact HEAD P5 B2/C2 Native check-input using SHA-locked same-build bundle; no timestep."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, tarfile, tempfile, shlex
from pathlib import Path

W1_HEAD = "74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f"
TARGET_HEAD = "cd61ec396e68f274ddd36073200124b776c58205"
W1_ELF_SHA = "1bdc85c65f5847ae58d51c76f89f8e67c67291dc9b5ee842bcbab98c4a71befa"
W1_TAR_SHA = "12f198cd17101b23b67a61a2fe95247af9c4c860d36b04ebf16b8dc91d4dadeb"
W1_ZIP_SHA = "b1f2dea2ab3d03b3c640260ce4fbdab72b2497a3d1faa24c54106e5f5847d4cd"
C0_SHA = "2c3bab8a8e28b360dcd54775d91ba13c97401364c709944bc21d6bf0b6d79490"
MESH_SHA = "ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc"
CASE_JSON = {
    "417": "ed99493d992c71b30e7a4120646af388894032d262b9af5bf299522629fe24ef",
    "941": "2a7d6b191eddf6a92a6bcf74fc818ade8f30836fdd857dc70516f3aa57fa5dde",
}
def sha_file(path: Path) -> str:
    with path.open("rb") as stream:
        h=hashlib.sha256()
        for chunk in iter(lambda:stream.read(8*1024*1024),b""):
            h.update(chunk)
        return h.hexdigest()

def verify_w1(artifact:Path, out:Path):
    import zipfile
    assert sha_file(artifact)==W1_ZIP_SHA
    with zipfile.ZipFile(artifact) as z:
        assert z.testzip() is None
        assert {"identity.json","physics-opt-and-app-libs.tar.gz"} <= set(z.namelist())
        identity=json.loads(z.read("identity.json"))
        data=z.read("physics-opt-and-app-libs.tar.gz")
    assert identity["source_head"]==W1_HEAD
    assert identity["source_tree"]=="10ab018235f047bf1abc250d3b18005b9156752a"
    assert identity["build_count"]==1
    assert set(identity["app_libraries"])=={"libphysics-opt.so.0","libphysics_test-opt.so.0"}
    assert identity["app_libraries"]["libphysics-opt.so.0"]["sha256"]=="b107698dfc7539237cd194331e306efd28f3fba7bc7e0b958f4f8dd2165f67bd"
    assert identity["app_libraries"]["libphysics_test-opt.so.0"]["sha256"]=="bd1e0626a5e6682ffdda66fa6e1589f3f0d975a66aa9f79b964efeb1d84924a6"
    assert identity["binary_sha256"]==W1_ELF_SHA
    assert identity["archive_sha256"]==W1_TAR_SHA
    assert hashlib.sha256(data).hexdigest()==W1_TAR_SHA
    expected={r["stored_path"]:r for r in identity["file_records"]}
    assert set(expected)=={"physics-opt","lib/libphysics-opt.so.0","lib/libphysics_test-opt.so.0"}
    out.mkdir(parents=True,exist_ok=True)
    import io
    with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as t:
        assert set(t.getnames())==set(expected)
        for name, row in expected.items():
            entry=t.getmember(name)
            assert entry.isfile() and not entry.issym() and not entry.islnk()
            blob=t.extractfile(entry).read()
            assert hashlib.sha256(blob).hexdigest()==row["sha256"] and len(blob)==row["bytes"]
            assert blob[:4]==b"\x7fELF"
            target=out/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(blob)
            target.chmod(0o755 if name=="physics-opt" else 0o644)
    assert sha_file(out/"physics-opt")==W1_ELF_SHA
    print("LATEST_HEAD_ACTUAL_ELF_2_LIBS_ZIP_CRC_SHA_PASS",W1_ELF_SHA)

def native(case: str, stage: Path, repo: Path, bundle: Path, out: Path, oci: str):
    out.mkdir(parents=True,exist_ok=True)
    p4=json.loads((stage.parent/"p4_receipt.json").read_text())[case]
    receipt={"schema":"issue633.newonly.dual_case.source_equivalent_shared_elf_native.v1",
             "source_repo":"HyungseonSong-plasma/moose-test-repo",
             "source_target_head":TARGET_HEAD,"w1_binary_source_head":W1_HEAD,
             "w1_exact_head_match":False,"w1_build_inputs_equivalent":True,
             "w1_binary_sha256":W1_ELF_SHA,"case":"S6-"+case,
             "oci":oci,"native_P3":"NOT_RUN","native_P4":"NOT_RUN",
             "science":"SCIENCE_HOLD","protected_rate_data_uploaded":False,
             "verdict":"HOLD"}
    try:
        assert sha_file(bundle/"physics-opt")==W1_ELF_SHA
        assert p4["post_p4_C0_sha256"]==C0_SHA
        assert p4["JSON_sha256"]==CASE_JSON[case]
        assert p4["parent_mesh_sha256"]==MESH_SHA
        assert len(p4["ordered_inputs"])==len(p4["11_layer_sha256"])==11
        source=stage/"scratch"/case
        chem_source=source/"experiments"/"Issue395_powered_chemistry_ladder"
        assert all(sha_file(chem_source/n)==h for n,h in p4["11_layer_sha256"].items())
        assert sha_file(chem_source/"chemistry"/f"unified_s6_{case}_newonly.json")==CASE_JSON[case]
        assert sha_file(chem_source/"baseline_plasma_plus_unstructured_cover_plus_wafer.msh")==MESH_SHA
        sys.path.insert(0,str(repo/"ci"/"guards"))
        from issue671_secure_ei_rate_scratch import read_hashed_rows, REQUIRED, EXPECTED, validate_rows
        original_meta,rates=read_hashed_rows()
        assert len(EXPECTED)==6 and set(rates)==set(EXPECTED)
        assert all(original_meta[n]["sha256_match"] and original_meta[n]["numeric_shape_pass"] for n in EXPECTED)
        os.environ.pop("PROTECTED_ARCHIVE_B64",None)
        work_dir=None
        with tempfile.TemporaryDirectory(prefix="issue671-W2W3-",dir="/dev/shm") as d:
            private=Path(d);work_dir=private
            assert private.stat().st_mode & 0o777 == 0o700
            work=private/"case"
            shutil.copytree(source,work,symlinks=False)
            chem=work/"experiments"/"Issue395_powered_chemistry_ladder"
            rates_folder=chem/"private_rates"
            assert not rates_folder.exists()
            rates_folder.mkdir(mode=0o700)
            for name in sorted(REQUIRED[case]):
                assert hashlib.sha256(rates[name]).hexdigest()==EXPECTED[name]
                assert validate_rows(rates[name])==100
                destination=rates_folder/name
                fd=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,"O_NOFOLLOW",0),0o600)
                with os.fdopen(fd,"wb") as file:file.write(rates[name])
                assert sha_file(destination)==EXPECTED[name]
                assert (destination.stat().st_mode&0o777)==0o600
            assert len(list(rates_folder.iterdir()))==5
            assert all(sha_file(chem/n)==h for n,h in p4["11_layer_sha256"].items())
            args=["docker","run","--rm","--network","none","--entrypoint","/bin/bash",
                  "--user","0:0","--workdir","/case",
                  "--env","OXYGEN_RESEARCH_400=1","--env","OXYGEN_RESEARCH_FULL24=0",
                  "--env","OXYGEN_RESEARCH_EI2738_FORMULA=0","--env","OXYGEN_RESEARCH_QUICK_5MIN=0",
                  "--mount",f"type=bind,src={bundle},dst=/w1,readonly",
                  "--mount",f"type=bind,src={work},dst=/case",
                  oci,"-lc",
                  'source /environment; export LD_LIBRARY_PATH="/w1/lib:$LD_LIBRARY_PATH"; /w1/physics-opt --check-input -i '+
                  " ".join(shlex.quote(p) for p in p4["ordered_inputs"])]
            try:
                result=subprocess.run(args,text=True,capture_output=True,timeout=720,check=False,
                                     env={k:v for k,v in os.environ.items() if k!="PROTECTED_ARCHIVE_B64"})
                exit_code=result.returncode
                log_text=result.stdout+"\n"+result.stderr
            except subprocess.TimeoutExpired:
                exit_code=124
                log_text="NATIVE_CHECK_INPUT_TIMEOUT_NO_TIMESTEP\n"
            finally:
                subprocess.run(["sudo","chown","-R",f"{os.getuid()}:{os.getgid()}",str(private)],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
            log_path=out/f"S6-{case}-native-check-input.log"
            log_path.write_text(log_text)
            good=exit_code==0 and "Syntax OK" in log_text
            receipt.update({"exit_code":exit_code,"syntax_ok":good,
                           "log_sha256":sha_file(log_path),
                           "case_json_sha256":CASE_JSON[case],
                           "post_p4x_C0_sha256":C0_SHA,
                           "original_parent_mesh_sha256":MESH_SHA,
                           "public_layer_sha256":p4["11_layer_sha256"],
                           "secure_original_case_rate_count":5,
                           "all_original_six_rate_sha_shape_verified":True,
                           "p05_integrity_if_syntax_ok":"REACHED" if good else "NOT_PROVEN",
                           "first_failure":next((ln.strip()[:220] for ln in log_text.splitlines()
                                              if "Error" in ln or "error" in ln),
                                              "NONE" if good else "UNKNOWN"),
                           "verdict":"PASS_NATIVE_CHECK_INPUT" if good else "FAIL_NATIVE_CHECK_INPUT"})
        receipt["private_tmpfs_removed"]=not work_dir.exists()
        assert receipt["private_tmpfs_removed"]
    except Exception as error:
        receipt["failure_class"]=type(error).__name__
        receipt["verdict"]="HOLD_PRE_EXEC_OR_CLEANUP"
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False,sort_keys=True)+"\n")
    print("LATEST_P5_B2C2_RESULT",case,receipt["verdict"],"SHA",receipt.get("log_sha256","none"))
    return 0 if receipt["verdict"]=="PASS_NATIVE_CHECK_INPUT" else 2

def main():
    parser=argparse.ArgumentParser()
    sp=parser.add_subparsers(dest="op",required=True)
    v=sp.add_parser("verify-w1")
    v.add_argument("--artifact",type=Path,required=True)
    v.add_argument("--output",type=Path,required=True)
    n=sp.add_parser("native")
    n.add_argument("--case",choices=CASE_JSON.keys(),required=True)
    n.add_argument("--stage",type=Path,required=True)
    n.add_argument("--repo",type=Path,required=True)
    n.add_argument("--bundle",type=Path,required=True)
    n.add_argument("--out",type=Path,required=True)
    n.add_argument("--oci",required=True)
    a=parser.parse_args()
    if a.op=="verify-w1":
        verify_w1(a.artifact,a.output);return 0
    return native(a.case,a.stage,a.repo,a.bundle,a.out,a.oci)
if __name__=="__main__":
    sys.exit(main())
