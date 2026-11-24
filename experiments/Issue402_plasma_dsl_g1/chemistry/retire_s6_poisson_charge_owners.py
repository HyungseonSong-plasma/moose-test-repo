"""Issue #652 G5: exact 15-owner Poisson + Charge retirement, Scratch only.

G5 is a fail-closed SOURCE handoff, not a numerical equivalence certificate.
The original 11 S6 layers, Native C0 source, JSON and template are never edited.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from poisson_contract import validate_poisson, PoissonContractError
from retire_s6_ion_fv_owners import ROOT, BLOCK, CutoverError
from retire_s6_p4_duplicate_owners import C0, AFTER_SHA as P4_C0_SHA

G5_OUTPUT_C0_SHA = "10f036ec8e6f1438c5dd854eea10f4680c970d56cb7a478766989a74f767e3e9"
TEMPLATE_SHA = {
    "417": "c89a01124fb96aa760b6753383eaa79ec6ae07d715d53910754dfe22afff6c8d",
    "941": "76f52e0aa5e25bb094ca1946f5cb820ccbf5e64c1abc54fb4f1f5e45b23eacac",
}
G5_OVERLAY_SHA = {
    "417": "f008f9b2beabc62ddb3a2214f1c6baab6d2cdd7c8ecec324bf1cc7db28ab6f08",
    "941": "dae87a4029b3c89c2e658b35a4a4ed97559a9b5779fc406edf7b35f43e59f768",
}
TARGET_SHA = {
    ("Variables", "potential"):
        "54b8a0693a5275f75d2230c7dee63af6080ea9d1b2c1a55f8dc0e5b827755309",
    ("FunctorMaterials", "charge_number_density"):
        "8fca600fe127ec76fe0a6b642460858b3a84cb2c43bbb13225f02a57ec04e6af",
    ("FunctorMaterials", "charge_density"):
        "463d17536ee97f21d001c698cb06bfd36ba9d16a5aadb7781b8445783f84a5c7",
    ("FunctorMaterials", "poisson_source"):
        "95259beac613226b1bb0a52743d09d5136a37500c0504e531d0f470aff4ba5f6",
    ("Materials", "eps_plasma"):
        "71c9f61261a2a7495346fa72b574b0b8189f68446beb3d9477a4cd201feba65c",
    ("Materials", "eps_cover"):
        "cccbada7cfb550ed32f2175d2c1d65d4ab8e13f049303b4ffda380655eec8dd4",
    ("Materials", "eps_wafer"):
        "632e09ab126d69857e33c13a3407e4d17f480b1c78dd37ddd1015af6bab25b8e",
    ("Materials", "eps_focus_ring"):
        "3237fb776c27992324d632d639efe48a9588efa363d30a8dc7d42f32d2cc0198",
    ("Materials", "eps_vacuum"):
        "12b30f6f4fd4c3cd4d6f3225444587150bffd12c48ae98ef21e29fa462e33650",
    ("Kernels", "phi_diffusion"):
        "7cec0efd72a1b9e81fc790171914f31d02f78a1f3fcb35f64478c669ebe1cc81",
    ("Kernels", "phi_source"):
        "062570461eafeed5d4f1721a35592ac727eb8e9d794c4b72355f4c2bcee13725",
    ("BCs", "grounded_potential"):
        "e3f8018bded7a923c0587e385e1e49be10b00af13dd31bb799bba509bf3d154c",
    ("BCs", "cover_surface_charge_poisson"):
        "4f0ea3837be3f796459c18167825715d885cc7d90145ae37a3eadda63e134574",
    ("BCs", "wafer_surface_charge_poisson"):
        "890d205cacae47948f6d850e7ab70a42a5db346570c98735a0cf7e31b7bc258b",
    ("BCs", "focus_ring_surface_charge_poisson"):
        "62e32c8363e7c2feab8cdfc6f337940214b4c44d1120cf7d23b3d7e225d03fa3",
}
SURFACE_SIGMA = ("sigma_s", "sigma_wafer", "sigma_focus_ring")
TARGET_NAMES = {name for _, name in TARGET_SHA}
OVERLAY_OLD_END = "    []\n  []\n[]\n"
OVERLAY_NEW_END = (
    "    []\n"
    "    [Poisson]\n"
    "      fem_potential = potential\n"
    "    []\n"
    "  []\n"
    "[]\n"
)


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def objects(source: str):
    roots = list(ROOT.finditer(source))
    for match in BLOCK.finditer(source):
        section = next(
            (found.group(1) for found in reversed(roots)
             if found.start() < match.start()), ""
        )
        yield section, match


def render_g5_poisson_overlay(template: bytes, variant: str) -> bytes:
    if variant not in TEMPLATE_SHA or digest(template) != TEMPLATE_SHA[variant]:
        raise CutoverError("G5_ORIGINAL_OVERLAY_SHA_CHANGED")
    text = template.decode("utf-8")
    if (not text.endswith(OVERLAY_OLD_END) or "[Poisson]" in text
            or text.count("[Plasmas]") != 1 or text.count("[Transport]") != 1
            or text.count("fem_potential = potential") != 2):
        raise CutoverError("G5_ORIGINAL_OVERLAY_STRUCTURE_CHANGED")
    result = (text[:-len(OVERLAY_OLD_END)] + OVERLAY_NEW_END).encode("utf-8")
    if digest(result) != G5_OVERLAY_SHA[variant]:
        raise CutoverError("G5_OUTPUT_OVERLAY_SHA_CHANGED")
    return result


def plan_g5_poisson_charge_retirement(
    layers: dict[str, bytes], ordered: list[str], mechanism: dict,
    *, post_p4_layer_sha: dict[str, str], original_overlay: bytes,
    variant: str
) -> tuple[bytes, bytes, dict]:
    """Validate all 11 inputs, return C0 and overlay bytes without writes."""
    try:
        validate_poisson(mechanism)
    except PoissonContractError as exc:
        raise CutoverError("G5_POISSON_JSON_CONTRACT_INVALID:" + str(exc)) from exc
    names = [Path(n).name for n in ordered]
    if (variant not in G5_OVERLAY_SHA or len(names) != 11 or
            names[0] != C0 or names[-1] != "migrated_continuity.i" or
            len(set(names)) != 11 or any(n != raw for n, raw in zip(names, ordered))
            or set(layers) != set(names) or set(post_p4_layer_sha) != set(names)):
        raise CutoverError("G5_EXACT_ELEVEN_INPUT_ORDER_INVALID")
    for name in names:
        blob = layers[name]
        if (not isinstance(blob, bytes) or b"\r" in blob
                or digest(blob) != post_p4_layer_sha[name]):
            raise CutoverError("G5_INPUT_LAYER_SHA_CHANGED:" + name)
    if digest(layers[C0]) != P4_C0_SHA:
        raise CutoverError("G5_NOT_EXACT_POST_P4_C0")
    new_overlay = render_g5_poisson_overlay(original_overlay, variant)

    targets = []
    c0_text = layers[C0].decode("utf-8")
    for name in names:
        source = layers[name].decode("utf-8")
        for section, match in objects(source):
            key = section, match["name"]
            if match["name"] in TARGET_NAMES and (name != C0 or key not in TARGET_SHA):
                raise CutoverError("G5_UNEXPECTED_OWNER_SECTION_OR_LAYER:" + name + ":" + match["name"])
            if name == C0 and key in TARGET_SHA:
                old_hash = digest(match.group(0).encode("utf-8"))
                if old_hash != TARGET_SHA[key]:
                    raise CutoverError("G5_EXACT_OWNER_BYTES_CHANGED:" + section + "/" + match["name"])
                targets.append((section, match))
    if len(targets) != 15 or {(section, match["name"]) for section, match in targets} != set(TARGET_SHA):
        raise CutoverError("G5_EXPECTED_FIFTEEN_OWNERS_CHANGED")
    for sigma in SURFACE_SIGMA:
        found = [(section, obj) for section, obj in objects(c0_text)
                 if section == "Variables" and obj["name"] == sigma]
        if len(found) != 1:
            raise CutoverError("G5_LOWER_D_SIGMA_MISSING:" + sigma)

    revised = c0_text
    for _, match in reversed(targets):
        revised = revised[:match.start()] + revised[match.end():]
    out_c0 = revised.encode("utf-8")
    if digest(out_c0) != G5_OUTPUT_C0_SHA:
        raise CutoverError("G5_C0_FULL_BYTE_REMAINDER_CHANGED")
    if any((section, obj["name"]) in TARGET_SHA for section, obj in objects(revised)):
        raise CutoverError("G5_OLD_POISSON_OR_CHARGE_OWNER_SURVIVED")
    for sigma in SURFACE_SIGMA:
        if sum(section == "Variables" and obj["name"] == sigma
               for section, obj in objects(revised)) != 1:
            raise CutoverError("G5_LOWER_D_SIGMA_DAMAGED:" + sigma)
    for required in ("n_i_physical", "n_m_physical", "n_op_physical",
                     "n_e_physical", "carrier_one"):
        if required not in revised:
            raise CutoverError("G5_LIVE_CONSUMER_OR_CARRIER_REMOVED:" + required)

    details = [
        {"section": section, "name": obj["name"], "block_sha256":
         TARGET_SHA[(section, obj["name"])]}
        for section, obj in targets
    ]
    return out_c0, new_overlay, {
        "schema": "issue652.g5.exact_s6_poisson_charge_retirement.v1",
        "variant": variant, "input_c0_sha256": P4_C0_SHA,
        "output_c0_sha256": G5_OUTPUT_C0_SHA,
        "input_overlay_template_sha256": TEMPLATE_SHA[variant],
        "output_overlay_sha256": G5_OVERLAY_SHA[variant],
        "retired_poisson_owners": 12, "retired_charge_owners": 3,
        "retired_owners": details,
        "preserved_other_10_layers": True, "lower_d_sigma_variables_preserved": True,
        "new_poisson_action": "Physics/Plasmas/Poisson",
        "expected_generated_poisson_owners": 12,
        "expected_generated_charge_functors": 3,
        "P1": "NOT_RUN", "Native_P2": "NOT_RUN",
        "science": "SCIENCE_HOLD",
    }


def retire_g5_in_disposable_scratch(
    folder: Path, ordered: list[str], mechanism: dict, *,
    post_p4_layer_sha: dict[str, str], original_overlay: bytes,
    variant: str
) -> dict:
    """No writes until every exact-source and output SHA has been checked."""
    folder = Path(folder).resolve(strict=True)
    if folder.name != "Issue395_powered_chemistry_ladder" or folder.parent.name != "experiments":
        raise CutoverError("G5_UNSAFE_DISPOSABLE_FOLDER")
    marker = folder / ".issue633_disposable_scratch"
    if (marker.is_symlink() or not marker.is_file()
            or marker.read_text().strip() != "issue633-scratch-only"):
        raise CutoverError("G5_DISPOSABLE_MARKER_REQUIRED")
    names = [Path(n).name for n in ordered]
    if len(names) != 11 or any(n != raw for n, raw in zip(names, ordered)):
        raise CutoverError("G5_UNSAFE_LAYER_NAMES")
    paths = {name: folder / name for name in names}
    if any(p.is_symlink() or not p.is_file() or p.resolve().parent != folder for p in paths.values()):
        raise CutoverError("G5_UNSAFE_LAYER_PATH")
    previous = {name: p.read_bytes() for name, p in paths.items()}
    c0, overlay, receipt = plan_g5_poisson_charge_retirement(
        previous, names, mechanism, post_p4_layer_sha=post_p4_layer_sha,
        original_overlay=original_overlay, variant=variant,
    )
    if any(paths[n].read_bytes() != previous[n] for n in names):
        raise CutoverError("G5_INPUT_CHANGED_AFTER_PREFLIGHT")
    paths[C0].write_bytes(c0)
    paths["migrated_continuity.i"].write_bytes(overlay)
    if (paths[C0].read_bytes() != c0 or
            paths["migrated_continuity.i"].read_bytes() != overlay or
            any(paths[n].read_bytes() != previous[n] for n in names[1:-1])):
        raise CutoverError("G5_SCRATCH_READBACK_FAILED")
    return receipt
