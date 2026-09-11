#pragma once

/**
 *  PHYSICS_CONSTANTS contains various constants useful in plasma modeling
 */
namespace PHYSICS_CONSTANTS
{
/// Pi.
inline constexpr Real pi =
    3.141592653589793238462643383279502884;

/// Boltzmann solver energy factor, sqrt(2*e/m).
inline constexpr Real gamma = 593097.0;

/// Elementary charge [C] (exact SI definition).
inline constexpr Real e = 1.602176634e-19;

/// Electron mass [kg].
inline constexpr Real m = 9.1095e-31;

/// Avogadro constant [1/mol].
inline constexpr Real N_A = 6.02214076e23;

/// Boltzmann constant [J/K].
inline constexpr Real k_boltz = 1.380649e-23;

/// Boltzmann constant [eV/K].
inline constexpr Real k_boltzeV = 8.617333e-5;

/// Universal gas constant [J/(mol K)].
inline constexpr Real R = 8.31446261815324;

/// Permittivity of free space [F/m] (CODATA/SI-consistent value).
inline constexpr Real eps_0 = 8.8541878128e-12;

/// Permeability of free space [H/m].
inline constexpr Real mu_0 = 4.0 * pi * 1e-7;

} // namespace PHYSICS_CONSTANTS
