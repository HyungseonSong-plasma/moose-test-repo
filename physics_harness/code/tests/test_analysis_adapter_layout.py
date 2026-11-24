"""Specialized Analysis adapter placement preserves canonical exports."""

from physics_harness.code import analysis, diagnostics
from physics_harness.code.analysis import adapters
from physics_harness.code.analysis.adapters import lucidity_adapter as implementation_adapter
from physics_harness.code.analysis.adapters import lucidity_interpretation as implementation_interpretation
from physics_harness.code.diagnostics.providers import cpp, git, moose_input, python_ast, workflow


def test_canonical_analysis_import_paths_preserve_public_object_identity():
    for module in (analysis, adapters):
        assert module.assess_code_understandability is implementation_adapter.assess_code_understandability
        assert module.summarize_understandability is implementation_adapter.summarize_understandability
    for module in (analysis, adapters):
        assert module.interpret_understandability_indicators is implementation_interpretation.interpret_understandability_indicators


def test_adapters_own_implementations_not_wrapper_modules():
    for obj in (adapters.assess_code_understandability,
                adapters.summarize_understandability,
                adapters.interpret_understandability_indicators):
        assert obj.__module__.startswith("physics_harness.code.analysis.adapters.")


def test_diagnostics_provider_exports_unchanged():
    assert diagnostics.CppSourceCollector is cpp.CppSourceCollector
    assert diagnostics.GitSourceProvider is git.GitSourceProvider
    assert diagnostics.MooseInputCollector is moose_input.MooseInputCollector
    assert diagnostics.PythonAstCollector is python_ast.PythonAstCollector
    assert diagnostics.WorkflowCollector is workflow.WorkflowCollector
