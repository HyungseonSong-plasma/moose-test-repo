#!/usr/bin/env python3
"""Resolve the SDK of the exact PETSc library loaded by the pinned PhysicsApp.

Never install another PETSc or fall back to an unrelated system library.
All work is secret-free inside the already pinned build-base OCI.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile

ROOT = Path("/workspace")
ELF = ROOT / "physics_app/physics-opt"
PROBE = ROOT / "physics_app/g7_jvp_probe.so"
SOURCE = ROOT / "g8-harness/ci/guards/issue652_g7_jvp_probe.cc"
RECEIPT = ROOT / "g7_petsc_sdk_receipt.json"


def execute(args):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=120).stdout


def linked_petsc(binary):
    out = execute(["ldd", str(binary)])
    paths = set()
    for line in out.splitlines():
        m = re.match(r"\s*libpetsc[^\s]*\s+=>\s+(\S+)", line, re.I)
        if m:
            p = Path(m.group(1))
            if not p.is_absolute() or not p.is_file():
                raise ValueError("PETSC_LIBRARY_UNRESOLVED")
            paths.add(p.resolve(strict=True))
    if len(paths) != 1:
        raise ValueError("PETSC_LINK_IDENTITY_NOT_UNIQUE")
    return paths.pop()


def candidate_includes(lib):
    # Search the linked installation, including an architecture subdirectory.
    # PETSC_DIR/PETSC_ARCH is used only if its library resolves to the same ELF.
    roots = [lib.parent.parent, lib.parent.parent.parent]
    env = os.environ.get("PETSC_DIR")
    if env:
        base = Path(env)
        arch = os.environ.get("PETSC_ARCH")
        for p in ([base / arch, base] if arch else [base]):
            if any(q.resolve() == lib for q in (p/"lib").glob("libpetsc*.so*")):
                roots.extend([p, base])
    dirs = []
    for root in roots:
        for candidate in (root/"include", root/"include/petsc", root/"include/petsc-real",
                          root/"include/petsc64", root/"include/petsc-real64"):
            if candidate.is_dir() and candidate not in dirs:
                dirs.append(candidate)
    # A Debian-style multiarch location can have architecture-specific config
    # headers under the same lib prefix. Inspect only PETSc-specific paths.
    for p in lib.parent.glob("petsc*/**/include"):
        if p.is_dir() and p not in dirs:
            dirs.append(p)
    for p in lib.parent.glob("petsc*/include"):
        if p.is_dir() and p not in dirs:
            dirs.append(p)
    return dirs


VERSION_TEST = r"""
#include <petscsnes.h>
#include <cstdio>
int main(int argc,char **argv) {
  PetscErrorCode rc=PetscInitialize(&argc,&argv,nullptr,nullptr);
  if (rc) return 1;
  PetscInt major=0,minor=0,sub=0,release=0;
  rc=PetscGetVersionNumber(&major,&minor,&sub,&release);
  if (rc || major!=PETSC_VERSION_MAJOR || minor!=PETSC_VERSION_MINOR ||
      sub!=PETSC_VERSION_SUBMINOR || sizeof(PetscScalar)!=sizeof(double)) return 2;
  std::printf("PETSC_ABI %d.%d.%d scalar=%zu index=%zu\\n",
     int(major),int(minor),int(sub),sizeof(PetscScalar),sizeof(PetscInt));
  return PetscFinalize();
}
""".replace(r"\\n", r"\n")


def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    report={"status":"HOLD","phase":"LINK_RESOLUTION","physics_app_rebuilt":False,
            "new_petsc_installed":False}
    try:
        lib=linked_petsc(ELF)
        report["linked_library"]=str(lib)
        report["linked_library_sha256"]=digest(lib)
        print("G7_PETSC_LINK_RESOLUTION_PASS",lib,flush=True)
        report["phase"]="HEADER_RESOLUTION"
        dirs=candidate_includes(lib)
        # Prefer the architecture-specific config belonging to the linked lib.
        config=[p for p in dirs if (p/"petscconf.h").is_file()]
        headers=[p for p in dirs if (p/"petscsnes.h").is_file()]
        if not config or not headers:
            raise ValueError("PETSC_MATCHED_HEADERS_NOT_FOUND")
        print("G7_PETSC_HEADER_CANDIDATE_COUNT",len(headers),len(config),flush=True)
        report["phase"]="ABI_CHECK"
        # Use the existing MPI compiler and direct absolute library, not -lpetsc.
        flags=None
        with tempfile.TemporaryDirectory(prefix="g7-petsc-sdk-") as tmp:
            tmp=Path(tmp)
            test=tmp/"version.cc"
            test.write_text(VERSION_TEST)
            for conf in config:
                for header in headers:
                    trial=["-I"+str(conf),"-I"+str(header)]
                    # Generic and architecture-specific headers may reside separately.
                    trial=list(dict.fromkeys(trial))
                    cmd=["mpicxx","-std=c++17",*trial,str(test),
                         "-o",str(tmp/"version"),str(lib),"-Wl,-rpath,"+str(lib.parent)]
                    try:
                        execute(cmd)
                        if linked_petsc(tmp/"version")!=lib:
                            continue
                        version=execute([str(tmp/"version")]).strip()
                        if not version.startswith("PETSC_ABI "):
                            continue
                    except subprocess.CalledProcessError as exc:
                        print("G7_PETSC_ABI_CANDIDATE_REJECTED",
                              (exc.stderr or "").strip()[-1000:],flush=True)
                        continue
                    flags=trial
                    report["header_directory"]=str(header)
                    report["config_directory"]=str(conf)
                    report["version_check"]=version
                    break
                if flags is not None:
                    break
        if flags is None:
            raise ValueError("PETSC_MATCHED_SDK_ABI_NOT_PROVEN")
        print("G7_PETSC_ABI_PASS",report["version_check"],flush=True)
        report["phase"]="OBSERVER_COMPILE"
        try:
            execute(["mpicxx","-std=c++17","-fPIC","-shared",*flags,str(SOURCE),
                     "-o",str(PROBE),str(lib),"-Wl,-rpath,"+str(lib.parent),"-ldl"])
        except subprocess.CalledProcessError as exc:
            print("G7_OBSERVER_COMPILER_DIAGNOSTIC",(exc.stderr or "")[-5000:],flush=True)
            raise
        report["phase"]="OBSERVER_LINK_CHECK"
        if linked_petsc(PROBE)!=lib:
            raise ValueError("OBSERVER_PETSC_LINK_MISMATCH")
        report.update(status="PASS",phase="COMPLETE",observer_sha256=digest(PROBE))
        print("G7_OBSERVER_PETSC_LINK_IDENTITY_PASS",flush=True)
    except Exception as exc:
        report["blocker_class"]=type(exc).__name__
        report["blocker_code"]=str(exc) if isinstance(exc,ValueError) else "SDK_COMMAND_FAILED"
        print("G7_PETSC_SDK_HOLD",report["phase"],report["blocker_code"],flush=True)
        raise
    finally:
        RECEIPT.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")


if __name__=="__main__":
    main()
