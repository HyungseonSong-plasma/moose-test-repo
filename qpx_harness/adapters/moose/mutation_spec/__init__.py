"""Strict MOOSE input-mutation schema and immutable mutation plan IR."""
from .compiler import compile_mutation_spec
from .errors import MutationSpecDependencyError, MutationSpecError, SpecProblem
from .loader import load_mutation_json_file, load_mutation_json_text, load_mutation_payload
from .models import (
    AddPetscFlagsOperation, EnsureBlockOperation, InsertChildBlockOperation,
    InsertTopLevelBeforeOperation, MutationCaseSpec, MutationSpec, RemoveBlockOperation,
    RemovePathsOperation, RemovePetscFlagsOperation, RemovePetscOptionOperation,
    ReplaceBlockOperation, SetParameterOperation, SetPetscOptionOperation, pydantic_major_api,
)
from .plan import MutationCasePlan, MutationPlan, OperationPlan
__all__ = [
    "AddPetscFlagsOperation", "EnsureBlockOperation", "InsertChildBlockOperation",
    "InsertTopLevelBeforeOperation", "MutationCasePlan", "MutationCaseSpec",
    "MutationPlan", "MutationSpec", "MutationSpecDependencyError", "MutationSpecError",
    "OperationPlan", "RemoveBlockOperation", "RemovePathsOperation",
    "RemovePetscFlagsOperation", "RemovePetscOptionOperation", "ReplaceBlockOperation",
    "SetParameterOperation", "SetPetscOptionOperation", "SpecProblem",
    "compile_mutation_spec", "load_mutation_json_file", "load_mutation_json_text",
    "load_mutation_payload", "pydantic_major_api",
]
