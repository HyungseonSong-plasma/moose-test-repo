from __future__ import annotations

import math
from pathlib import Path

from experiments.Issue92_r3_nonlinear.characteristic_time import audit_case


MESH = """$MeshFormat
4.1 0 8
$EndMeshFormat
$PhysicalNames
2
2 53 "plasma"
2 94 "port"
$EndPhysicalNames
$Entities
0 5 2 0
1 0 0 0 0 1 0 0 0
2 0 0 0 1 0 0 0 0
3 1 0 0 1 1 0 0 0
4 0 1 0 1 1 0 0 0
5 1.2 0 0 1.2 1 0 0 0
1 0 0 0 1 1 0 1 53 4 1 2 3 4
2 1 0 0 1.2 1 0 1 94 1 3
$EndEntities
$Nodes
1 4 1 4
2 1 0 4
1 2 3 4
0 0 0
1 0 0
1 1 0
0 1 0
$EndNodes
$Elements
1 2 1 2
2 1 2 2
1 1 2 3
2 1 3 4
$EndElements
"""

BASE = """Q_sccm = 100
Vm_std = 0.0224136
outlet_pressure = 1.33322
T_g_value = 600
E0_migration = 0.01
Yin_O2 = 0.7
Yin_O2s = 0.05
Yin_O2p = 0.01
Yin_O = 0.1
Yin_Om = 0.01
Yin_Op = 0.01
Yin_Os = 0.12
"""

TRANSPORT = """species O2 0.032 O2
species O2s 0.032 O2
species O2p 0.032 O2+
species O 0.016 O
species Om 0.016 O-
species Op 0.016 O+
species Os 0.016 O
"""

MOMENTS = "5.73276 1.57e24 6.64e24\n"


def _case(tmp_path: Path) -> Path:
    case = tmp_path / "case"
    case.mkdir()
    (case / "heavy_base.i").write_text(BASE)
    (case / "qvt.msh").write_text(MESH)
    (case / "transport_data.txt").write_text(TRANSPORT)
    (case / "electron_moments.txt").write_text(MOMENTS)
    return case


def test_t0_is_qpx_free_and_reports_domain_mesh_and_transport_scales(tmp_path: Path) -> None:
    out = audit_case(_case(tmp_path))
    assert out["qpx_executed"] is False
    assert out["scientific_evr_consumed"] == 0
    assert out["mesh"]["plasma_entity"] == 1
    assert out["mesh"]["domain_length_min"] == 1.0
    assert out["mesh"]["mesh_edge_min"] == 1.0
    assert out["mesh"]["inlet_shared_curve_entities"] == [3]
    assert math.isclose(out["mesh"]["inlet_rz_area"], 2.0 * math.pi, rel_tol=1e-12)
    assert out["electron_state"]["prescribed_E_V_m"] == 0.0
    assert out["electron_times"]["mesh_min"]["tau_drift_s"] is None
    assert out["electron_times"]["mesh_min"]["tau_diff_s"] > 0
    assert out["heavy_advection"]["status"] == "ESTABLISHED"
    assert out["heavy_diffusion"]["status"] == "NOT_ESTABLISHED"


def test_t0_candidate_dt_is_derived_from_electron_time_not_fixed_decade(tmp_path: Path) -> None:
    out = audit_case(_case(tmp_path), current_dt=1.0)
    tau = out["electron_times"]["mesh_min"]["tau_diff_s"]
    if out["decision"] == "T0-B":
        assert math.isclose(out["candidate_temporal_dt_s"], tau / 10.0, rel_tol=1e-12)
    else:
        assert out["decision"] in {"T0-A", "T0-C"}


def test_t0_parses_real_issue91_qvt_assets_without_qpx() -> None:
    case = Path("experiments/Issue91_real_qvt_r3/r3_e0")
    out = audit_case(case)
    assert out["qpx_executed"] is False
    assert out["scientific_evr_consumed"] == 0
    assert out["decision"] in {"T0-A", "T0-B", "T0-C"}
    assert out["mesh"]["plasma_entity"] == 2
    assert out["mesh"]["mesh_edge_min"] > 0
    assert out["mesh"]["mesh_edge_median"] >= out["mesh"]["mesh_edge_min"]
    assert out["electron_state"]["electron_diffusion_m2_s"] > 0
    assert out["heavy_advection"]["status"] in {"ESTABLISHED", "NOT_ESTABLISHED"}
