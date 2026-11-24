"""Secret-free PETSc linked SDK resolution controls."""
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"ci/guards"))
import issue652_g7_petsc_sdk as sdk


def test_linked_library_realpath_and_arch_headers(tmp_path,monkeypatch):
    prefix=tmp_path/"petsc"
    arch=prefix/"arch-opt"
    lib=arch/"lib/libpetsc.so.3"
    lib.parent.mkdir(parents=True)
    lib.write_bytes(b"fake")
    alias=lib.parent/"libpetsc.so"
    alias.symlink_to(lib)
    (arch/"include").mkdir()
    (prefix/"include").mkdir()
    (arch/"include/petscconf.h").touch()
    (prefix/"include/petscsnes.h").touch()
    monkeypatch.setattr(sdk,"execute",lambda args:f"libpetsc.so => {alias} (0x0)\n")
    assert sdk.linked_petsc(Path("binary"))==lib
    assert sdk.candidate_includes(lib)[:2]==[arch/"include",prefix/"include"]


@pytest.mark.parametrize("output",["libpetsc.so => not found","libmpi.so => /usr/lib/libmpi.so (0x0)",""])
def test_unresolved_link_fails_closed(monkeypatch,output):
    monkeypatch.setattr(sdk,"execute",lambda args:output)
    with pytest.raises(ValueError):
        sdk.linked_petsc(Path("binary"))


def test_two_different_petsc_libraries_rejected(tmp_path,monkeypatch):
    a,b=tmp_path/"libpetsc.so",tmp_path/"libpetsc_real.so"
    a.touch()
    b.touch()
    monkeypatch.setattr(sdk,"execute",lambda args:f"libpetsc.so => {a} (0x0)\nlibpetsc_real.so => {b} (0x0)")
    with pytest.raises(ValueError,match="NOT_UNIQUE"):
        sdk.linked_petsc(Path("binary"))
