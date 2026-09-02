from experiments.R3_electron_master_diagnostic.cases import build_r3_proxy_text
from experiments.R3_electron_master_diagnostic.spec import CHEAP_CASES, FROZEN_DIFFUSION


CASES = {spec.case_id: spec for spec in CHEAP_CASES}


def test_literal_and_generic_remedy_proxies_preserve_full_electron_operator():
    for case_id in ("A2_LITERAL_BASE", "A3_GENERIC_AD_BASE"):
        spec = CASES[case_id]
        for field in ("E0", "Econst"):
            text = build_r3_proxy_text(spec, field)
            assert f"R3 remedy proxy: {case_id} / {field}" in text
            assert "  [time]\n" in text
            assert "  [diffusion]\n" in text
            assert "  [drift]\n" in text
            assert "diag_electron_diffusion_min" in text
            assert "diag_electron_diffusion_max" in text


def test_literal_proxy_routes_only_diffusion_coefficient_away_from_qpx_lookup():
    text = build_r3_proxy_text(CASES["A2_LITERAL_BASE"], "Econst")
    assert f"coeff = {FROZEN_DIFFUSION!r}" in text
    assert "type = QPXElectronTransportLookupMaterial" in text
    assert "mobility = electron_mobility" in text


def test_generic_ad_proxy_supplies_both_transport_coefficients_for_econst():
    text = build_r3_proxy_text(CASES["A3_GENERIC_AD_BASE"], "Econst")
    assert "type = ADGenericFunctorMaterial" in text
    assert "prop_names = 'electron_mobility electron_diffusion'" in text
    assert "mobility = electron_mobility" in text
