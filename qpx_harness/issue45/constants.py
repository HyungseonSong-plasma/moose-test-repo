"""Frozen Issue45 electron-inventory closure constants."""
from __future__ import annotations

from .. import issue43_coupling_diagnostic as coupling_diag

ISSUE = 45
DT_REFERENCE = 1.0e-13
STEPS = 1
DRIFT_TYPE = "QPXFVElectrostaticDrift"
CONSTRAINT_TYPE = "FVIntegralValueConstraint"
LAMBDA_VARIABLE = "r45_inventory_lambda"
MACRO_AVG_POSTPROCESSOR = "r45_ne_macro_avg"
DEFAULT_MACRO_ELECTRON_AVG = 1.0e16
C0_TARGET = 1.0e16
C1_TARGET = 1.01e16
CLOSURE_TARGET_REL_TOL = 1.0e-6
CLOSURE_DELTA_REL_TOL = 5.0e-4
INVENTORY_CONSISTENCY_REL_TOL = 1.0e-8
BASE_CASE_RELATIVE = coupling_diag.BASE_CASE_RELATIVE

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
EXPECTED_DRIFT_BOUNDARIES = frozenset(
    {
        "inlet",
        "outlet",
        "plasma_electrode",
        "plasma_metal",
        "plasma_right",
        "plasma_cover",
        "plasma_wafer",
        "plasma_focus_ring",
    }
)
EXPECTED_POISSON_GROUNDS = frozenset(
    {"plasma_metal", "plasma_electrode", "plasma_right", "inlet", "outlet"}
)
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
