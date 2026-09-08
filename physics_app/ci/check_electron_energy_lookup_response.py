import csv
import math

FILES = [
    ("low", 0.5, "ci/electron_energy_lookup_response_low.csv"),
    ("base", 1.0, "ci/electron_energy_lookup_response_base.csv"),
    ("high", 1.5, "ci/electron_energy_lookup_response_high.csv"),
]

N_NEUTRAL = 101325.0 / (1.380649e-23 * 300.0)
ENERGY_REFERENCE_EV = 5.73276

values = []
for name, n_epsilon_hat, path in FILES:
    with open(path, newline="") as handle:
        row = list(csv.DictReader(handle))[-1]

    mean_energy = float(row["mean_en_solved_avg"])
    mobility = float(row["electron_mobility_avg"])
    diffusion = float(row["electron_diffusion_avg"])

    expected_mean = ENERGY_REFERENCE_EV * n_epsilon_hat
    reduced_mobility = 1.0e24 + (expected_mean - 1.0) * (3.0e24 / 9.0)
    reduced_diffusion = 2.0e24 + (expected_mean - 1.0) * (6.0e24 / 9.0)

    assert math.isclose(mean_energy, expected_mean, rel_tol=1.0e-11, abs_tol=1.0e-12), (
        name,
        mean_energy,
        expected_mean,
    )
    assert math.isclose(mobility, reduced_mobility / N_NEUTRAL, rel_tol=1.0e-9), (
        name,
        mobility,
        reduced_mobility / N_NEUTRAL,
    )
    assert math.isclose(diffusion, reduced_diffusion / N_NEUTRAL, rel_tol=1.0e-9), (
        name,
        diffusion,
        reduced_diffusion / N_NEUTRAL,
    )
    values.append((mean_energy, mobility, diffusion))

assert values[0][0] < values[1][0] < values[2][0]
assert values[0][1] < values[1][1] < values[2][1]
assert values[0][2] < values[1][2] < values[2][2]

print("PHYSICS_ELECTRON_SOLVED_MEAN_ENERGY_REACHES_LOOKUP_PASS")
print("PHYSICS_ELECTRON_TRANSPORT_RESPONSE_DISCRIMINATOR_PASS")
