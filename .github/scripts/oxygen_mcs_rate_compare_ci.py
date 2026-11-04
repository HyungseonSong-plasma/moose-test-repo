#!/usr/bin/env python3
"""Compare MCS.OUT reference rates to in-run MOOSE oxygen chemistry rates.

Inputs: selected MCS rate constants (cm3/s assumed), and existing MOOSE
mean-energy lookup directory. Legacy ratio mode writes ratio/statistics only.
The explicit linear-3x3 mode writes ONLY a derived PNG inside an authorized
runner; that image still requires disclosure approval before release. No raw
lookup rows or coefficient files are written or printed by either mode.
"""
import argparse
import csv
import importlib.util
import math
from functools import lru_cache
from pathlib import Path

NA = 6.02214076e23
ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments/Issue395_powered_chemistry_ladder"
LOOKUP = (407, 413, 414, 415, 2058, 2067, 2068, 2069, 2072, 2074, 944)
FORMULAS = (2259, 936)
NOT_SAME_PROCESS = (2073,)
ALL = LOOKUP + FORMULAS + NOT_SAME_PROCESS
PANEL_REACTIONS = (401, 411, 412, 417, 935, 941, 943, 2738, 407)
PRIVATE_PANEL_REACTIONS = (411, 412, 417, 935, 943, 407)
PUBLIC_PANEL_FILES = {401: "o2_attachment.txt", 941: "o_ionization.txt"}
PNG_NAME = "MCS_MOOSE_3x3_LINEAR.png"


@lru_cache(maxsize=None)
def source_owner(name):
    """Load the existing scientific owner, without reading numeric rate data."""
    spec = importlib.util.spec_from_file_location(name, BASE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def interp(table, x):
    if not math.isfinite(x) or x <= 0:
        raise ValueError("Interpolation energy must be positive and finite")
    if len(table) < 2:
        raise ValueError("Interpolation requires a validated table")
    if x < table[0][0] or x > table[-1][0]:
        return None
    for i in range(1, len(table)):
        if x <= table[i][0]:
            x0, y0 = table[i-1]
            x1, y1 = table[i]
            return y0 + (y1-y0)*(x-x0)/(x1-x0)
    return table[-1][1]

def read_table(path):
    # Reuse the production owner: exactly 100 finite two-column points,
    # positive strictly increasing energies, nonnegative molar coefficients.
    # Its float-parser exception may contain a raw input token: sanitize it.
    try:
        return source_owner("build_oxygen_24_source_overlay").validate_table(path)
    except (OSError, ValueError, OverflowError):
        raise ValueError("Invalid or missing 100-point Lookup table") from None


def molar_lookup_to_cm3_s(raw):
    """m^3/(mol s) -> m^3/(particle s) -> cm^3/(particle s), once."""
    if not math.isfinite(raw) or raw < 0:
        raise ValueError("Invalid molar rate coefficient")
    return raw / NA * 1e6

def analytical(rid, mean_energy):
    if not math.isfinite(mean_energy) or mean_energy <= 0:
        raise ValueError("Formula energy must be positive and finite")
    te=(2.0/3.0)*mean_energy
    if te < 1.0 or te > 7.0:
        return None
    if rid==2259:
        return 2.4e-13*(300.0/(te*11604.51812155))**0.70*1e6
    if rid==936:
        return 4.54e-15*math.exp(-4.49/te)*1e6
    if rid==2738:
        owner = source_owner("build_ei2738_detachment_formula_overlay")
        # The existing formula is already a particle rate in m^3/s; NO N_A.
        return owner.RATE_PREF_M3_S * math.exp(-owner.TE_EXP_EV / te) * 1e6
    raise ValueError("Formula not implemented")

def write_csv(path, rows, fields):
    with path.open("w", newline="") as stream:
        writer=csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def read_mcs_cases(paths, require_complete=False):
    """Join verified references by case AND exact energy/field identity.

    Missing reaction columns stay absent, never zero-filled. Every supplied
    reaction column must contain 24 finite nonnegative rates, including zeros.
    Optional supplemental CSVs use the same case/EoverN_Td/mean_energy_eV schema.
    """
    merged = {}
    identity_fields = ("case", "EoverN_Td", "mean_energy_eV")
    for path in paths:
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)) or not set(identity_fields) <= set(fields):
                raise ValueError("MCS reference has missing or duplicate identity columns")
            reactions = [rid for rid in PANEL_REACTIONS if f"EI-{rid}" in fields]
            rows = list(reader)
        if len(rows) != 24:
            raise ValueError("Expected exactly 24 MCS cases in each reference")
        batch = {}
        for row in rows:
            if None in row:
                raise ValueError("Malformed MCS reference row")
            case = row["case"]
            if not case or case in batch:
                raise ValueError("Missing or duplicate MCS case identity")
            try:
                field = float(row["EoverN_Td"])
                energy = float(row["mean_energy_eV"])
                rates = {rid: float(row[f"EI-{rid}"]) for rid in reactions}
            except (TypeError, ValueError, OverflowError):
                raise ValueError("MCS reference contains an invalid numeric value") from None
            if not all(math.isfinite(v) and v > 0 for v in (field, energy)):
                raise ValueError("MCS reference field/energy must be positive and finite")
            if not all(math.isfinite(v) and v >= 0 for v in rates.values()):
                raise ValueError("MCS reference rates must be nonnegative and finite")
            batch[case] = {"case": case, "field": field, "energy": energy, "rates": rates}
        if len({row["energy"] for row in batch.values()}) != 24:
            raise ValueError("Duplicate MCS mean-energy point")
        if len({row["field"] for row in batch.values()}) != 24:
            raise ValueError("Duplicate MCS reduced-field point")
        if merged and set(batch) != set(merged):
            raise ValueError("MCS reference case identities do not match")
        for case, row in batch.items():
            if case not in merged:
                merged[case] = row
                continue
            previous = merged[case]
            if (previous["field"], previous["energy"]) != (row["field"], row["energy"]):
                raise ValueError("MCS reference case energy/field identities do not match")
            for rid, value in row["rates"].items():
                if rid in previous["rates"] and previous["rates"][rid] != value:
                    raise ValueError("Conflicting MCS reaction references")
                previous["rates"][rid] = value
    if not merged:
        raise ValueError("No MCS reference cases supplied")
    cases = sorted(merged.values(), key=lambda row: row["energy"])
    if require_complete and any(set(row["rates"]) != set(PANEL_REACTIONS) for row in cases):
        raise ValueError("Complete MCS references required for all nine panels")
    return cases


def prepare_linear_comparison(rate_dir, mcs_paths, public_rate_dir=None, require_complete=False):
    """Keep coefficients in runner memory; return plotting data, never files."""
    cases = read_mcs_cases(mcs_paths, require_complete=require_complete)
    public_rate_dir = public_rate_dir or ROOT / "physics_app/data/electron_impact"
    owner = source_owner("build_oxygen_24_source_overlay")
    targets = {"O2": "O2_X", "O": "O_3P", "Os": "O_1D"}
    tables = {}
    for rid in PRIVATE_PANEL_REACTIONS:
        filename = f"EI-{rid}_{targets[owner.PARENT[rid]]}.txt"
        tables[rid] = read_table(rate_dir / filename)
    for rid, filename in PUBLIC_PANEL_FILES.items():
        tables[rid] = read_table(public_rate_dir / filename)
    # The private package contract uses a common grid. Check only the six
    # required reactions; do not inspect unrelated private reaction tables.
    grid = [point[0] for point in tables[PRIVATE_PANEL_REACTIONS[0]]]
    for rid in PRIVATE_PANEL_REACTIONS[1:]:
        if any(not math.isclose(expected, point[0], rel_tol=1e-10, abs_tol=1e-10)
               for expected, point in zip(grid, tables[rid])):
            raise ValueError("Private Lookup mean-energy grids do not match")
    panels = []
    for rid in PANEL_REACTIONS:
        model = []
        for case in cases:
            if rid == 2738:
                value = analytical(rid, case["energy"])
            else:
                raw = interp(tables[rid], case["energy"])
                value = None if raw is None else molar_lookup_to_cm3_s(raw)
            model.append(value)
        if not any(value is not None for value in model):
            raise ValueError("No MCS energy points overlap a MOOSE rate domain")
        panels.append({
            "reaction": rid,
            "energies": [row["energy"] for row in cases],
            "mcs": [row["rates"].get(rid) for row in cases],
            "moose": model,
            "source": ("Formula: Te = 2/3 mean energy; Te in [1, 7] eV" if rid == 2738
                       else "Public Lookup: 100 points; in-domain interpolation" if rid in PUBLIC_PANEL_FILES
                       else "Private Lookup: 100 points; in-domain interpolation"),
            "hold": "HOLD: reaction identity" if rid in (411, 412) else "",
            "mcs_reference_files": tuple(Path(path).name for path in mcs_paths),
        })
    return panels


def build_linear_figure(panels):
    """Explicit linear axes and missing-data annotations, without numeric dumps."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if tuple(panel["reaction"] for panel in panels) != PANEL_REACTIONS:
        raise ValueError("Incorrect nine-panel reaction mapping")
    fig, axes = plt.subplots(3, 3, figsize=(15, 12), layout="constrained")
    for ax, panel in zip(axes.flat, panels):
        ax.set_title(f'EI-{panel["reaction"]}', fontweight="bold")
        ax.set_xscale("linear")
        ax.set_yscale("linear")
        ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
        ax.grid(alpha=0.25)
        if any(value is not None for value in panel["mcs"]):
            ax.plot(panel["energies"], panel["mcs"], "o-", markersize=3, label="MCS.OUT")
        else:
            ax.text(0.03, 0.66, "MCS.OUT unavailable: verified reference missing",
                    transform=ax.transAxes, fontsize=8, color="darkred", wrap=True)
        model = [math.nan if value is None else value for value in panel["moose"]]
        ax.plot(panel["energies"], model, "s--", markersize=3, label="MOOSE")
        # Reserve annotation headroom independently of the plotted rate span.
        # A linear axis must still auto-scale to the actual coefficient size.
        ax.set_ylim(0, ax.get_ylim()[1] * 1.30)
        ax.text(0.03, 0.97, panel["source"], transform=ax.transAxes,
                va="top", fontsize=7, wrap=True,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85})
        if panel["hold"]:
            ax.text(0.03, 0.84, panel["hold"], transform=ax.transAxes,
                    va="top", color="darkred", fontsize=9, fontweight="bold",
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85})
        ax.legend(loc="lower right", fontsize=8)
    fig.supxlabel("Mean Electron Energy (eV)")
    fig.supylabel("Rate Coefficient k (cm³/s), Linear Scale")
    sources = ", ".join(panels[0].get("mcs_reference_files", ()))
    title = ("MCS.OUT–MOOSE absolute rate coefficients\n"
             "MCS RATE CONST units assumed cm³/s — unit confirmation HOLD\n"
             "Table/formula comparison only; no MOOSE simulation")
    if sources:
        title += "\nMCS reference files: " + sources
    fig.suptitle(title, fontsize=10)
    return fig


def write_linear_png(panels, output_dir):
    """Create a sole derived PNG, never coefficient CSVs or source tables."""
    import matplotlib.pyplot as plt
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ValueError("Linear PNG requires a new or empty output directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    fig = build_linear_figure(panels)
    target = output_dir / PNG_NAME
    temporary = output_dir / (PNG_NAME + ".partial")
    try:
        fig.savefig(temporary, format="png", dpi=180)
        temporary.replace(target)
    finally:
        plt.close(fig)
        temporary.unlink(missing_ok=True)
    return target


def run_ratios(a):
    modpath=BASE/"build_oxygen_24_source_overlay.py"
    spec=importlib.util.spec_from_file_location("oxygen_lookup_validator",modpath)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    paths=mod.validate_files(a.rate_dir)
    if not set(LOOKUP).issubset(paths):
        raise ValueError("Missing reaction lookup data")
    tables={rid:read_table(paths[rid]) for rid in LOOKUP}
    if 936 in paths:
        tables[936]=read_table(paths[936])
    with a.mcs_csv.open(newline="") as f:
        cases=list(csv.DictReader(f))
    if len(cases)!=24:
        raise ValueError("Expected exactly 24 MCS cases")
    want={"case","EoverN_Td","mean_energy_eV"}|{f"EI-{rid}" for rid in ALL}
    if not want.issubset(cases[0]):
        raise ValueError("MCS reference lacks required columns")
    a.output_dir.mkdir(parents=True,exist_ok=True)
    values=[]
    summaries=[]
    for rid in ALL:
        if rid in NOT_SAME_PROCESS:
            summaries.append({"reaction":f"EI-{rid}","mode":"PROCESS_IDENTITY_HOLD",
                              "matched_points":0,"mean_absolute_relative_error_pct":"",
                              "median_ratio":"","max_absolute_relative_error_pct":""})
            continue
        mode="LOOKUP" if rid in LOOKUP else "LOOKUP" if rid in tables else "FORMULA_FALLBACK" if rid==936 else "FORMULA"
        comparisons=[]
        for case in cases:
            en=float(case["mean_energy_eV"])
            mcs=float(case[f"EI-{rid}"])
            if mcs<=0:
                continue
            if mode=="LOOKUP":
                raw=interp(tables[rid], en)
                if raw is None:
                    continue
                model=molar_lookup_to_cm3_s(raw)
            else:
                model=analytical(rid,en)
                if model is None:
                    continue
            if not math.isfinite(model) or model < 0:
                raise ValueError("Invalid model rate")
            ratio=model/mcs
            rec={"reaction":f"EI-{rid}","mode":mode,"case":case["case"],
                 "EoverN_Td":case["EoverN_Td"],"mean_energy_eV":case["mean_energy_eV"],
                 "moose_over_mcs":format(ratio, ".9g")}
            values.append(rec)
            comparisons.append(ratio)
        if not comparisons:
            raise ValueError(f"Missing matched rates for EI-{rid}")
        deviations=sorted(abs(100.0*(q-1)) for q in comparisons)
        sorted_ratios=sorted(comparisons)
        n=len(sorted_ratios)
        median=(sorted_ratios[(n-1)//2]+sorted_ratios[n//2])/2.0
        summaries.append({"reaction":f"EI-{rid}","mode":mode,
            "matched_points":n,
            "mean_absolute_relative_error_pct":format(sum(deviations)/n,".7g"),
            "median_ratio":format(median,".8g"),
            "max_absolute_relative_error_pct":format(deviations[-1],".7g")})
    write_csv(a.output_dir/"rate_ratios.csv",values,
              ["reaction","mode","case","EoverN_Td","mean_energy_eV","moose_over_mcs"])
    write_csv(a.output_dir/"summary.csv",summaries,
              ["reaction","mode","matched_points","mean_absolute_relative_error_pct",
               "median_ratio","max_absolute_relative_error_pct"])
    (a.output_dir/"DATA_POLICY.txt").write_text(
        "This artifact contains ratio/statistics ONLY; private rate tables not included.\n"
        "MCS.OUT RATE CONST interpreted as cm^3/s (source unit not confirmed).\n"
        "Mean electron energies from MCS; MOOSE lookup linearly interpolated.\n"
        "EI-2073 is not source-process-equivalent; numerical comparison deliberately excluded.\n"
        "EI-2068/2069 and EI-413/414 process mappings remain scientific HOLD.\n"
        "Formula comparisons use Te=(2/3)*mean energy, Te in [1,7] eV.\n"
        "No MOOSE simulation was run; this is a rate-coefficient table comparison only.\n")
    print("MCS_RATE_COMPARISON_RESULT_WRITTEN",
          "reactions",len(summaries),"ratios",len(values),
          "ei936_mode","LOOKUP" if 936 in paths else "FORMULA_FALLBACK")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("ratios", "linear-3x3"), default="ratios")
    p.add_argument("--rate-dir", required=True, type=Path)
    p.add_argument("--mcs-csv", required=True, type=Path)
    p.add_argument("--additional-mcs-csv", action="append", default=[], type=Path,
                   help="Additional verified CSVs with matching case/field/energy identities")
    p.add_argument("--public-rate-dir", type=Path,
                   default=ROOT / "physics_app/data/electron_impact")
    p.add_argument("--require-complete-mcs", action="store_true",
                   help="Fail unless verified MCS data exists for all nine panels")
    p.add_argument("--output-dir", required=True, type=Path)
    a = p.parse_args()
    if a.mode == "ratios":
        run_ratios(a)
        return
    try:
        panels = prepare_linear_comparison(a.rate_dir, [a.mcs_csv] + a.additional_mcs_csv,
                                          a.public_rate_dir, a.require_complete_mcs)
        write_linear_png(panels, a.output_dir)
    except Exception:
        # Never print a traceback: parser/renderer errors may contain source
        # coefficient strings or private paths. The authorized runner can
        # diagnose its inputs internally, without putting them in public logs.
        p.exit(2, "MCS_LINEAR_COMPARISON_FAILED: input validation or rendering failed; no source data logged\n")
    print("MCS_LINEAR_COMPARISON_PNG_WRITTEN", PNG_NAME)


if __name__ == "__main__":
    main()
