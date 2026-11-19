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



@pytest.mark.parametrize(
    "header",
    [
        "class PhysicsFVElectronEnergyJouleHeating : public FVElementalKernel\n{\n};\n",
        "class PhysicsFVElectronEnergyJouleHeating\n  : public FVElementalKernel\n{\n};\n",
        "class PhysicsFVElectronEnergyJouleHeating\n  : public\n    FVElementalKernel\n{\n};\n",
    ],
)
def test_cpp_multiline_inheritance_is_detected_with_provenance(git_factory, header):
    path = "physics_app/include/fvkernels/PhysicsFVElectronEnergyJouleHeating.h"
    result = scan(git_factory, {path: header}, ("physics_app/include/fvkernels/*.h",),
                  collectors=("cpp",))
    assert result.status == "COMPLETE"
    assert result.receipt.files[0].status == "SCANNED"
    cls = [node for node in result.graph.nodes if node.kind == "cpp_class"]
    assert len(cls) == 1
    assert cls[0].name == "PhysicsFVElectronEnergyJouleHeating"
    assert cls[0].qualified_name == f"{path}:{cls[0].name}"
    assert cls[0].location.start_line == 1
    inheritance = [edge for edge in result.graph.edges
                   if edge.relation == "INHERITS_CANDIDATE"]
    assert len(inheritance) == 1
    base_node = result.graph.nodes_by_id()[inheritance[0].target_id]
    assert base_node.name == "FVElementalKernel"
    assert any(path + ":1@" in ev.source_ref for ev in result.graph.evidence)
    assert not result.receipt.unresolved


@pytest.mark.parametrize(
    "header",
    [
        "class Complex final : public Kernel {\\n};\\n".replace("\\n", "\n"),
        "class WithTwo : public Base, public Other {\\n};\\n".replace("\\n", "\n"),
        "struct Special alignas(16) {\\n};\\n".replace("\\n", "\n"),
    ],
)
def test_cpp_unsupported_class_shapes_fail_closed_as_partial(git_factory, header):
    result = scan(git_factory, {"src/complex.h": header},
                  ("src/*.h",), collectors=("cpp",))
    assert result.status == "PARTIAL"
    assert result.receipt.files[0].status == "UNRESOLVED"
    assert "CPP_CLASS_UNPARSED:src/complex.h:1" in result.receipt.unresolved
    assert not any(node.kind == "cpp_class" for node in result.graph.nodes)


def test_cpp_ignored_comment_class_is_not_a_missing_declaration(git_factory):
    source = (
        "// class Missing final : public Other {}\n"
        "/*\nclass AlsoMissing final : public Other {}\n*/\n"
        "class RealType : public FVElementalKernel\n{\n};\n"
    )
    result = scan(git_factory, {"src/code.h": source},
                  ("src/*.h",), collectors=("cpp",))
    assert result.status == "COMPLETE"
    assert [node.name for node in result.graph.nodes
            if node.kind == "cpp_class"] == ["RealType"]


def test_cpp_multiline_layout_does_not_change_logical_class_identity(git_factory):
    path = "src/obj.h"
    single = scan(git_factory, {path: "class MyKernel : public Kernel {};\n"},
                  ("src/*.h",), collectors=("cpp",))
    multiline = scan(git_factory, {
        path: "class MyKernel : public Kernel\n{\n};\n",
    }, ("src/*.h",), collectors=("cpp",))
    def class_ids(graph):
        return {node.id for node in graph.nodes if node.kind == "cpp_class"}
    assert class_ids(single.graph) == class_ids(multiline.graph)
    assert single.status == multiline.status == "COMPLETE"
    assert single.graph.scope.revision != multiline.graph.scope.revision
