"""Source-bound C++/MOOSE Factory and .i reference candidate tests."""

import pytest

from physics_harness.code.diagnostics import (
    CppSourceCollector, GitSourceProvider, MooseInputCollector,
    ScanRequest, run_scan,
)


CPP = """\
#include "MyKernel.h"
registerADMooseObject("PhysicsApp", MyKernel);
class MyKernel : public Kernel {
};
"""
INPUT = """\
[Kernels]
  [./test]
    type = MyKernel
    variable = u
  [../]
[]
"""


def scan(git_factory, files, includes, collectors=("cpp", "moose_input")):
    root, sha = git_factory(files)
    request = ScanRequest(
        repository="example/repo", revision=sha,
        includes=includes, collectors=collectors,
    )
    return run_scan(request, GitSourceProvider(root))


def test_cpp_registration_and_input_reference_share_one_type_identity(git_factory):
    result = scan(git_factory, {
        "physics_app/src/kernels/MyKernel.C": CPP, "inputs/test.i": INPUT,
    }, ("physics_app/src/kernels/*.C", "inputs/*.i"))
    assert result.status == "COMPLETE"
    nodes = [n for n in result.graph.nodes if n.kind == "moose_type"]
    assert len(nodes) == 1
    assert nodes[0].name == "MyKernel"
    assert len(nodes[0].evidence_ids) == 2
    relations = {edge.relation for edge in result.graph.edges}
    assert {
        "DECLARES_MOOSE_REGISTRATION", "DECLARES_TYPE_USE",
        "DECLARES_INPUT_BLOCK", "INCLUDES_CANDIDATE",
        "INHERITS_CANDIDATE", "DEFINES",
    }.issubset(relations)
    assert result.receipt.scanned_count == 2
    assert all(e.observation_status == "SOURCE_DECLARED"
               for e in result.graph.evidence)
    assert not result.graph.claims
    assert "RUNTIME_INSTANTIATES" not in relations


def test_comments_do_not_produce_fake_registrations(git_factory):
    source = """\
// registerMooseObject("PhysicsApp", Fake1);
/* registerADMooseObject("PhysicsApp", Fake2); */
registerADMooseObject("PhysicsApp", RealType);
"""
    result = scan(git_factory, {"src/obj.C": source},
                  ("src/*.C",), collectors=("cpp",))
    assert result.status == "COMPLETE"
    assert [n.name for n in result.graph.nodes if n.kind == "moose_type"] == [
        "RealType",
    ]


def test_cpp_conditions_and_nonliteral_registration_are_unresolved(git_factory):
    conditional = "#if FEATURE\nregisterADMooseObject(\"PhysicsApp\", MyKernel);\n#endif\n"
    first = scan(git_factory, {"src/obj.C": conditional},
                 ("src/*.C",), collectors=("cpp",))
    assert first.status == "PARTIAL"
    assert any("CONDITIONAL_COMPILATION_UNRESOLVED" in u
               for u in first.receipt.unresolved)

    unknown = "registerADMooseObject(PHYSICS_APP, MyKernel);\n"
    second = scan(git_factory, {"src/obj.C": unknown},
                  ("src/*.C",), collectors=("cpp",))
    assert second.status == "PARTIAL"
    assert any("UNPARSED_MOOSE_REGISTRATION" in u
               for u in second.receipt.unresolved)
    assert not any(n.kind == "moose_type" for n in second.graph.nodes)


def test_dynamic_type_and_input_include_require_resolution(git_factory):
    source = """\
!include base_input.i
[Kernels]
  [./test]
    type = $DYNAMIC_KERNEL
    active = 'test'
  [../]
[]
"""
    result = scan(git_factory, {"inputs/test.i": source},
                  ("inputs/*.i",), collectors=("moose_input",))
    assert result.status == "PARTIAL"
    assert result.receipt.files[0].status == "UNRESOLVED"
    assert {e.relation for e in result.graph.edges} >= {
        "DYNAMIC_TYPE_CANDIDATE", "INCLUDES_CANDIDATE",
    }
    assert any(n.kind == "unresolved" for n in result.graph.nodes)
    assert any(e.observation_status == "UNRESOLVED" for e in result.graph.evidence)
    assert not any(n.kind == "moose_type" for n in result.graph.nodes)


@pytest.mark.parametrize("invalid", ["[]\n", "[A]\n[../]\n[../]\n"])
def test_invalid_closing_block_fails_closed(git_factory, invalid):
    result = scan(git_factory, {"inputs/test.i": invalid},
                  ("inputs/*.i",), collectors=("moose_input",))
    assert result.status == "PARTIAL"
    assert result.receipt.files[0].status == "FAILED"
    assert "COLLECTOR_FAILED:moose_input:ValueError" in result.receipt.files[0].details


def test_unclosed_block_is_partial_not_complete(git_factory):
    result = scan(git_factory, {"inputs/test.i": "[Kernels]\n"},
                  ("inputs/*.i",), collectors=("moose_input",))
    assert result.status == "PARTIAL"
    assert any("MOOSE_UNCLOSED_BLOCKS" in u for u in result.receipt.unresolved)


def test_inactive_declaration_is_not_runtime_evidence(git_factory):
    source = INPUT.replace("variable = u", "variable = u\n    inactive = 'other'")
    result = scan(git_factory, {"inputs/test.i": source},
                  ("inputs/*.i",), collectors=("moose_input",))
    assert result.status == "COMPLETE"
    block = next(n for n in result.graph.nodes if n.name == "test")
    assert block.attributes["inactive"] == "'other'"
    assert block.attributes["parameter_names"] == ("inactive", "type", "variable")
    assert not result.graph.claims


def test_canonical_type_id_persists_when_app_registration_changes(git_factory):
    first = scan(git_factory, {"src/k.C": CPP},
                 ("src/*.C",), collectors=("cpp",))
    second = scan(git_factory, {"src/k.C": CPP.replace("PhysicsApp", "OtherApp")},
                  ("src/*.C",), collectors=("cpp",))
    assert {n.id for n in first.graph.nodes if n.kind == "moose_type"} == {
        n.id for n in second.graph.nodes if n.kind == "moose_type"
    }
    assert {e.id for e in first.graph.evidence} != {
        e.id for e in second.graph.evidence
    }


def test_source_extensions_select_correct_provider():
    from physics_harness.code.diagnostics import SourceRecord
    sha = "a" * 40
    cpp, hit = CppSourceCollector(), MooseInputCollector()
    assert cpp.supports(SourceRecord("src/a.C", sha, "100644", 1))
    assert not cpp.supports(SourceRecord("src/a.i", sha, "100644", 1))
    assert hit.supports(SourceRecord("inputs/a.i", sha, "100644", 1))
    assert not hit.supports(SourceRecord("src/a.C", sha, "100644", 1))
