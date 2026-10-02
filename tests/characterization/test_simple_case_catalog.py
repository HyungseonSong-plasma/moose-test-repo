from __future__ import annotations

from pathlib import Path

from physics_harness.specification.simple_cases import (
    STABLE_STATUS,
    format_simple_case_choices,
    is_simple_case_request,
    load_simple_case_catalog,
    reproduction_command,
    resolve_simple_case,
    simple_case_menu_for_request,
    validate_simple_case_catalog,
)

ROOT = Path(__file__).resolve().parents[2]


def test_simple_case_catalog_is_valid_and_ordered() -> None:
    assert validate_simple_case_catalog(ROOT) == ()
    cases = load_simple_case_catalog(ROOT / "experiments" / "simple_case_inventory.json")
    assert [case.order for case in cases] == list(range(1, len(cases) + 1))
    assert cases[0].simple_case_id == "electron-diffusion-experiment"
    assert cases[0].status == STABLE_STATUS
    assert cases[0].experiment_id == "2d-icp-electron-diffusion-experiment"
    assert cases[0].reproducible is True
    assert all(not case.reproducible for case in cases[1:])


def test_simple_case_request_triggers_korean_and_english() -> None:
    for request in (
        "simple case부터 해야겠다",
        "simple case 로 돌아가자",
        "최소 케이스부터 보자",
        "처음부터 다시 시작하자",
        "baseline부터 확인하자",
    ):
        assert is_simple_case_request(request)
        menu = simple_case_menu_for_request(request)
        assert menu is not None
        assert "1. electron-diffusion-experiment [ready]" in menu
        assert "2. electron-drift-diffusion-experiment [planned]" in menu

    assert simple_case_menu_for_request("현재 결과를 분석해줘") is None


def test_simple_case_resolution_and_reproduction_delegate_to_existing_harness() -> None:
    case = resolve_simple_case("electron diffusion")
    assert case.simple_case_id == "electron-diffusion-experiment"
    assert resolve_simple_case("1") == case
    command = reproduction_command(case, executable="/opt/physics/physics-opt")
    assert command == (
        "python3 bin/physics.py test "
        "experiments/2d-icp-electron-diffusion-experiment "
        "--qpx /opt/physics/physics-opt"
    )


def test_menu_is_numbered_in_increasing_physics_order() -> None:
    text = format_simple_case_choices()
    lines = text.splitlines()
    assert lines[0].startswith("1. electron-diffusion-experiment [ready]")
    assert lines[1].startswith("2. electron-drift-diffusion-experiment [planned]")
    assert lines[2].startswith("3. electron-poisson-experiment [planned]")
    assert lines[-1].startswith("6. full-icp-coupled-experiment [planned]")
