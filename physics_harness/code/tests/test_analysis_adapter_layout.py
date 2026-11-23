"""Specialized Analysis adapter placement preserves existing import contracts."""

from physics_harness.code import analysis
from physics_harness.code.analysis import adapters
from physics_harness.code.analysis import understandability_adapter as old_adapter
from physics_harness.code.analysis import understandability_interpretation as old_interpretation
from physics_harness.code.analysis.adapters import understandability_adapter as new_adapter
from physics_harness.code.analysis.adapters import understandability_interpretation as new_interpretation
from physics_harness.code import diagnostics
from physics_harness.code.diagnostics.providers import cpp, git, moose_input, python_ast, workflow


def test_understandability_exports_identical_across_old_and_new_paths():
    assert old_adapter.assess_code_understandability is new_adapter.assess_code_understandability
    assert old_adapter.summarize_understandability is new_adapter.summarize_understandability
    assert old_interpretation.interpret_understandability_indicators is new_interpretation.interpret_understandability_indicators
    assert analysis.assess_code_understandability is adapters.assess_code_understandability
    assert analysis.summarize_understandability is adapters.summarize_understandability
    assert analysis.interpret_understandability_indicators is adapters.interpret_understandability_indicators


def test_implementation_owned_by_adapters_not_compatibility_shims():
    for obj in (adapters.assess_code_understandability,
                adapters.summarize_understandability,
                adapters.interpret_understandability_indicators):
        assert obj.__module__.startswith("physics_harness.code.analysis.adapters.")


def test_diagnostics_provider_public_entrypoints_unchanged():
    assert diagnostics.CppSourceCollector is cpp.CppSourceCollector
    assert diagnostics.GitSourceProvider is git.GitSourceProvider
    assert diagnostics.MooseInputCollector is moose_input.MooseInputCollector
    assert diagnostics.PythonAstCollector is python_ast.PythonAstCollector
    assert diagnostics.WorkflowCollector is workflow.WorkflowCollector
