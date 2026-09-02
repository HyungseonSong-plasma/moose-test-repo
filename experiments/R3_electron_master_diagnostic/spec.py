"""Declarative case/remedy specification for the R3 electron master diagnostic."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FROZEN_DIFFUSION = 41257.29899041419
FROZEN_MOBILITY = 9755.114369721427
FROZEN_NEUTRAL_DENSITY = 1.6094219840118698e20
PLASMA_BOUNDARIES = (
    "inlet", "outlet", "plasma_electrode", "plasma_metal",
    "plasma_right", "plasma_cover", "plasma_wafer", "plasma_focus_ring",
)
CaseKind = Literal["required", "optional"]


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    family: str
    base: str
    transforms: tuple[tuple[str, str], ...] = ()
    kind: CaseKind = "required"
    meaning: str = ""


def t(name: str, value: str) -> tuple[str, str]:
    return name, value


CHEAP_CASES: tuple[CaseSpec, ...] = (
    # Required anchors reuse the already-established #94 L0-L3 construction paths.
    CaseSpec("A0_TIME_ONLY", "control", "L0", meaning="time-only accepted control"),
    CaseSpec("A1_QPX_BASELINE", "control", "L3", meaning="current QPX diffusion failure anchor"),
    CaseSpec("A2_LITERAL_BASE", "coefficient", "L1", meaning="literal-D #94 anchor"),
    CaseSpec("A3_GENERIC_AD_BASE", "coefficient", "L2", meaning="generic-AD #94 anchor"),

    # Exploratory discriminators are optional so pinned-version incompatibility does not
    # consume the one-shot opportunity or block the required scientific anchors.
    CaseSpec("C0_LITERAL_HARMONIC", "coefficient", "L1", (t("coeff_interp_method", "harmonic"),), kind="optional"),
    CaseSpec("C1_LITERAL_AVERAGE", "coefficient", "L1", (t("coeff_interp_method", "average"),), kind="optional"),
    CaseSpec("C2_GENERIC_NONAD", "coefficient", "L2", (t("material_ad", "false"), t("coeff_interp_method", "harmonic")), kind="optional"),
    CaseSpec("C3_GENERIC_AD_HARMONIC", "coefficient", "L2", (t("coeff_interp_method", "harmonic"),), kind="optional"),
    CaseSpec("C4_GENERIC_AD_AVERAGE", "coefficient", "L2", (t("coeff_interp_method", "average"),), kind="optional"),
    CaseSpec("B0_TWO_TERM_FALSE", "variable", "L1", (t("two_term_boundary_expansion", "false"),), kind="optional"),
    CaseSpec("B1_TWO_TERM_TRUE", "variable", "L1", (t("two_term_boundary_expansion", "true"),), kind="optional"),
    CaseSpec("B2_VAR_FACE_SKEW", "variable", "L1", (t("two_term_boundary_expansion", "true"), t("face_interp_method", "skewness-corrected")), kind="optional"),
    CaseSpec("B3_DIFF_VAR_SKEW", "variable", "L1", (t("two_term_boundary_expansion", "true"), t("variable_interp_method", "skewness-corrected")), kind="optional"),
    CaseSpec("B4_BOTH_SKEW", "variable", "L1", (t("two_term_boundary_expansion", "true"), t("face_interp_method", "skewness-corrected"), t("variable_interp_method", "skewness-corrected")), kind="optional"),
    CaseSpec("B5_CACHE_FALSE", "variable", "L1", (t("two_term_boundary_expansion", "true"), t("cache_cell_gradients", "false")), kind="optional"),
    CaseSpec("B6_INSFV", "variable", "L1", (t("two_term_boundary_expansion", "true"), t("variable_type", "INSFVScalarFieldVariable")), kind="optional"),
    CaseSpec("E0_LITERAL_NO_BOUNDARY", "face_context", "L1", (t("boundaries_to_avoid", "all"),), kind="optional"),
    CaseSpec("E1_GENERIC_AD_NO_BOUNDARY", "face_context", "L2", (t("boundaries_to_avoid", "all"),), kind="optional"),
    CaseSpec("E2_QPX_NO_BOUNDARY", "face_context", "L3", (t("boundaries_to_avoid", "all"),), kind="optional"),
    CaseSpec("Q0_QPX_LITERAL_MEAN_EN", "lookup", "L3", (t("qpx_mean_energy", "5.73276"),), kind="optional"),
    CaseSpec("Q1_QPX_LITERAL_P", "lookup", "L3", (t("qpx_pressure", "1.33322"),), kind="optional"),
    CaseSpec("Q2_QPX_LITERAL_T", "lookup", "L3", (t("qpx_gas_temperature", "600.0"),), kind="optional"),
    CaseSpec("Q3_QPX_ALL_LITERAL", "lookup", "L3", (t("qpx_mean_energy", "5.73276"), t("qpx_pressure", "1.33322"), t("qpx_gas_temperature", "600.0")), kind="optional"),
    CaseSpec("S0_QPX_SCALING_OFF", "solver", "L3", (t("automatic_scaling", "false"), t("off_diagonals_in_auto_scaling", "false")), kind="optional"),

    # Constant-state magnitude discriminators. These preserve the zero-gradient
    # mathematical solution while changing only the absolute unknown scale.
    CaseSpec("M0_LITERAL_N1_RAW", "conditioning", "L1", (t("initial_n_e", "1.0"), t("automatic_scaling", "false"), t("off_diagonals_in_auto_scaling", "false")), kind="optional"),
    CaseSpec("M1_LITERAL_N1E4_RAW", "conditioning", "L1", (t("initial_n_e", "1e4"), t("automatic_scaling", "false"), t("off_diagonals_in_auto_scaling", "false")), kind="optional"),
    CaseSpec("M2_LITERAL_N1E8_RAW", "conditioning", "L1", (t("initial_n_e", "1e8"), t("automatic_scaling", "false"), t("off_diagonals_in_auto_scaling", "false")), kind="optional"),
    CaseSpec("M3_LITERAL_N1E12_RAW", "conditioning", "L1", (t("initial_n_e", "1e12"), t("automatic_scaling", "false"), t("off_diagonals_in_auto_scaling", "false")), kind="optional"),
    CaseSpec("M4_LITERAL_N1E14_RAW", "conditioning", "L1", (t("initial_n_e", "1e14"), t("automatic_scaling", "false"), t("off_diagonals_in_auto_scaling", "false")), kind="optional"),

    # Diffusion-strength discriminators use the physical n_e=1e16 but disable
    # automatic residual scaling so the raw residual trend can be compared.
    CaseSpec("K0_LITERAL_D0_RAW", "conditioning", "L1", (t("literal_diffusion", "0.0"), t("automatic_scaling", "false"), t("off_diagonals_in_auto_scaling", "false")), kind="optional"),
    CaseSpec("K1_LITERAL_D1_RAW", "conditioning", "L1", (t("literal_diffusion", "1.0"), t("automatic_scaling", "false"), t("off_diagonals_in_auto_scaling", "false")), kind="optional"),
    CaseSpec("K2_LITERAL_D1E2_RAW", "conditioning", "L1", (t("literal_diffusion", "1e2"), t("automatic_scaling", "false"), t("off_diagonals_in_auto_scaling", "false")), kind="optional"),
    CaseSpec("K3_LITERAL_D1E4_RAW", "conditioning", "L1", (t("literal_diffusion", "1e4"), t("automatic_scaling", "false"), t("off_diagonals_in_auto_scaling", "false")), kind="optional"),
    CaseSpec("K4_LITERAL_DFROZEN_RAW", "conditioning", "L1", (t("automatic_scaling", "false"), t("off_diagonals_in_auto_scaling", "false")), kind="optional"),
)


REMEDY_MAP: dict[str, dict[str, str]] = {
    "BOUNDARY_RECONSTRUCTION": {
        "class": "CONFIGURATION_FIX",
        "remedy": "Use the controlled reconstruction setting that produces the PASS transition.",
        "verification": "constant-state diffusion -> R3-E0 -> R3-Econst",
    },
    "VARIABLE_INTERPOLATION": {
        "class": "CONFIGURATION_FIX",
        "remedy": "Use the isolated face/gradient interpolation policy explicitly.",
        "verification": "constant-state diffusion -> R3-E0 -> R3-Econst",
    },
    "VARIABLE_CLASS": {
        "class": "ARCHITECTURE_CHANGE",
        "remedy": "Adopt INSFVScalarFieldVariable only if matched parameter controls cannot reproduce the transition.",
        "verification": "matched reconstruction -> constant-state diffusion -> R3-E0 -> R3-Econst",
    },
    "GENERIC_FUNCTOR_AD": {
        "class": "QPX_LOCAL_CODE_FIX",
        "remedy": "Repair the generic Functor/AD coefficient delivery path before restoring QPX lookup.",
        "verification": "literal -> generic non-AD -> generic AD -> R3-E0",
    },
    "QPX_LOOKUP": {
        "class": "QPX_LOCAL_CODE_FIX",
        "remedy": "Repair QPXElectronTransportLookupMaterial value/context/derivative ownership; frozen generic AD is diagnostic proxy only.",
        "verification": "lookup value/context -> Jacobian -> R3-E0 -> R3-Econst",
    },
    "QPX_BOUNDARY_FACEARG": {
        "class": "QPX_LOCAL_CODE_FIX",
        "remedy": "Repair QPX lookup evaluation on single-sided boundary FaceArg.",
        "verification": "boundary context -> full constant-state diffusion -> R3-E0 -> R3-Econst",
    },
    "STATE_MAGNITUDE_CONDITIONING": {
        "class": "NONDIMENSIONALIZATION_FIX",
        "remedy": "Use a normalized electron unknown (for example n_hat=n_e/n_ref) so physical density remains unchanged while the solved variable is O(1).",
        "verification": "constant-state magnitude sweep -> normalized R3-E0 -> normalized R3-Econst -> production coupling audit",
    },
    "FVDIFFUSION_INTERNAL_ASSEMBLY": {
        "class": "UPSTREAM_OR_INTEGRATION_FIX",
        "remedy": "Localize and repair constant-state FVDiffusion internal assembly after state-magnitude conditioning is explicitly disfavored; geometry remains held fixed/out of scope.",
        "verification": "O(1) literal constant-state diffusion -> real-QVT R3-E0 -> R3-Econst",
    },
    "SOLVER_SCALING": {
        "class": "CONFIGURATION_OR_NONDIMENSIONALIZATION_FIX",
        "remedy": "Correct electron scaling/nondimensionalization rather than masking an operator error with solver tuning.",
        "verification": "residual/Jacobian contract -> scaled solve -> R3-E0 -> R3-Econst",
    },
}
