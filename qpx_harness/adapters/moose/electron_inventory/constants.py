"""MOOSE realization constants for electron-inventory closure."""
from __future__ import annotations

from qpx_harness.provenance.cases import QVT_PREPOISSON_CASE
from qpx_harness.domains.plasma.electron_inventory import (
    DEFAULT_MACRO_ELECTRON_AVG,
    C0_TARGET,
    C1_TARGET,
    CLOSURE_TARGET_REL_TOL,
    CLOSURE_DELTA_REL_TOL,
    INVENTORY_CONSISTENCY_REL_TOL,
    EXPECTED_DRIFT_BOUNDARIES,
    EXPECTED_POISSON_GROUNDS,
)

ISSUE = 45
DT_REFERENCE = 1.0e-13
STEPS = 1
DRIFT_TYPE = "QPXFVElectrostaticDrift"
CONSTRAINT_TYPE = "FVIntegralValueConstraint"
LAMBDA_VARIABLE = "r45_inventory_lambda"
MACRO_AVG_POSTPROCESSOR = "r45_ne_macro_avg"
BASE_CASE_RELATIVE = QVT_PREPOISSON_CASE

RUNTIME_PURGE_DIRECTORY_NAMES = (".jitcache",)
RUNTIME_PURGE_PATTERNS = (
    "input_out*",
    "r43_csv*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)

REQUIRED_FVFLUX_SCHEMA_PARAMETERS = (
    "boundaries_to_avoid",
    "boundaries_to_force",
    "force_boundary_execution",
)
REQUIRED_CONSTRAINT_SCHEMA_PARAMETERS = ("variable", "lambda", "phi0")
EXPECTED_TRANSIENT_ELECTRON_KERNEL_TYPES = (
    "FVDiffusion",
    "FVTimeKernel",
    DRIFT_TYPE,
)
EXPECTED_CONSTRAINED_ELECTRON_KERNEL_TYPES = (
    "FVDiffusion",
    CONSTRAINT_TYPE,
    DRIFT_TYPE,
)
RUNTIME_COLUMNS = (
    "n_avg",
    "inventory",
    "domain_volume",
    "n_min",
    "n_max",
    "r43_phi_l2",
    "r43_phi_min",
    "r43_phi_max",
    "r43_charge_integral",
    "r43_charge_min",
    "r43_charge_max",
)
