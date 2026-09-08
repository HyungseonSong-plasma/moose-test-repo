#include "PhysicsThermalDiffusionMaterial.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <sstream>
#include <utility>

registerMooseObject("PhysicsApp", PhysicsThermalDiffusionMaterial);

namespace
{
constexpr Real ANGSTROM2_TO_M2 = 1.0e-20;

// Dynamic charged-charged transport follows the pinned Mutation++
// Debye-Huckel implementation (Mason-Munn-Smith / Devoto tables).
// electron_temperature is supplied in K and electron_number_density in m^-3.
constexpr Real EPS0 = 8.8541878128e-12;
constexpr Real QE = 1.602176634e-19;
constexpr Real DEBYE_NE_FLOOR = 1.0e-16;

constexpr std::array<Real, 26> DEBYE_TSTAR = {{0.1, 0.2, 0.3, 0.4, 0.6, 0.8, 1, 2, 3, 4, 6, 8, 10, 20, 30, 40, 60, 80, 100, 200, 300, 400, 600, 800, 1000, 10000}};

// Columns: Q11_att, Q11_rep, Q22_att, Q22_rep, B*_att, B*_rep, C*_att, C*_rep.
// The first four columns are reduced values (T*)^2 Q.  Q11/Q22 are
// dimensionalized at runtime with pi*lambda_D^2/(T*)^2, exactly as in
// Mutation++ CoulombIntegrals.cpp.
constexpr std::array<std::array<Real, 8>, 26> DEBYE_TABLE = {{
    {{0.063, 0.0224, 0.0384, 0.0304, 1.4695, 1.3646, 0.7573, 0.7486}},
    {{0.1364, 0.0511, 0.0967, 0.0697, 1.4577, 1.3865, 0.6585, 0.7104}},
    {{0.1961, 0.0797, 0.1557, 0.1086, 1.4297, 1.3946, 0.615, 0.6858}},
    {{0.248, 0.1072, 0.21, 0.1459, 1.3987, 1.3976, 0.5852, 0.6675}},
    {{0.3297, 0.1584, 0.3037, 0.2144, 1.3668, 1.3972, 0.5549, 0.6411}},
    {{0.3962, 0.205, 0.3818, 0.2757, 1.3425, 1.3933, 0.5356, 0.6221}},
    {{0.4519, 0.2474, 0.4483, 0.331, 1.3252, 1.3884, 0.5226, 0.6075}},
    {{0.6467, 0.4177, 0.684, 0.546, 1.2798, 1.3627, 0.4901, 0.5632}},
    {{0.7746, 0.5442, 0.8385, 0.6999, 1.2585, 1.342, 0.4756, 0.5391}},
    {{0.8719, 0.6455, 0.9541, 0.8197, 1.2442, 1.3255, 0.4663, 0.523}},
    {{1.0173, 0.8026, 1.124, 1.0006, 1.2255, 1.3011, 0.4546, 0.5022}},
    {{1.1259, 0.923, 1.2486, 1.1385, 1.2133, 1.2833, 0.4471, 0.4886}},
    {{1.213, 1.0207, 1.3473, 1.2435, 1.2043, 1.2697, 0.4417, 0.4789}},
    {{1.4972, 1.3431, 1.6626, 1.5892, 1.1798, 1.2295, 0.4273, 0.4529}},
    {{1.6716, 1.5412, 1.8517, 1.7959, 1.1673, 1.2083, 0.42, 0.4404}},
    {{1.7984, 1.6847, 1.9872, 1.9438, 1.159, 1.1945, 0.4154, 0.4326}},
    {{1.9807, 1.8898, 2.1801, 2.1531, 1.1481, 1.177, 0.4094, 0.423}},
    {{2.1123, 2.0368, 2.3184, 2.3019, 1.1409, 1.1659, 0.4056, 0.417}},
    {{2.2156, 2.1515, 2.4266, 2.4171, 1.1358, 1.158, 0.4029, 0.4128}},
    {{2.5427, 2.5087, 2.7672, 2.7713, 1.122, 1.1365, 0.3956, 0.4013}},
    {{2.738, 2.7168, 2.9687, 2.9747, 1.1151, 1.1254, 0.3919, 0.3955}},
    {{2.878, 2.8635, 3.1121, 3.1177, 1.1106, 1.1181, 0.3894, 0.392}},
    {{3.0767, 3.0687, 3.3146, 3.3185, 1.1045, 1.1089, 0.3862, 0.3876}},
    {{3.2185, 3.2135, 3.4583, 3.461, 1.1005, 1.1033, 0.3841, 0.3849}},
    {{3.3289, 3.3256, 3.5699, 3.5719, 1.0975, 1.0994, 0.3825, 0.3831}},
    {{4.4759, 4.4763, 4.7211, 4.7211, 1.0734, 1.0733, 0.3702, 0.3702}}
}};
}

InputParameters
PhysicsThermalDiffusionMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Computes data-driven heavy-species mixture-averaged and thermal diffusion "
      "coefficients using the canonical collision-data path.");

  params.addRequiredParam<MooseFunctorName>("temperature", "Heavy-species temperature [K].");
  params.addRequiredParam<MooseFunctorName>("pressure", "Mixture absolute pressure [Pa].");

  params.addParam<MooseFunctorName>(
      "electron_temperature",
      "Electron temperature [K]. Required when any active transport pair is charged-charged.");

  params.addParam<MooseFunctorName>(
      "electron_number_density",
      "Electron number density [1/m^3]. Required when any active transport pair is charged-charged.");

  params.addRequiredParam<FileName>(
      "transport_data_file",
      "Text database containing species constants and pair collision-integral tables.");

  params.addRequiredParam<std::vector<std::string>>(
      "species",
      "Ordered active species names. Each name must exist in transport_data_file.");

  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "mass_fractions",
      "Mass-fraction functors in exactly the same order as 'species'.");

  params.addParam<std::vector<MooseFunctorName>>(
      "D_T_names",
      "Optional output functor names in species order. "
      "If omitted, names are generated as D_T_<species>.");

  params.addParam<std::vector<MooseFunctorName>>(
      "kT_names",
      "Optional output functor names in species order. "
      "If omitted, names are generated as kT_<species>.");

  params.addParam<std::vector<MooseFunctorName>>(
      "D_mix_names",
      "Optional output functor names in species order for the mixture-averaged "
      "diffusion coefficients D_k,m [m^2/s]. If omitted, names are generated "
      "as D_mix_<species>.");

  return params;
}

PhysicsThermalDiffusionMaterial::PhysicsThermalDiffusionMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _temperature(getFunctor<ADReal>("temperature")),
    _pressure(getFunctor<ADReal>("pressure")),
    _transport_data_file(getParam<FileName>("transport_data_file")),
    _species_names(getParam<std::vector<std::string>>("species")),
    _mass_fraction_names(getParam<std::vector<MooseFunctorName>>("mass_fractions"))
{
  if (_species_names.size() < 2)
    paramError("species", "At least two heavy species are required.");

  if (_species_names.size() != _mass_fraction_names.size())
    paramError("mass_fractions",
               "'species' and 'mass_fractions' must contain the same number of entries.");

  loadTransportDatabase(_transport_data_file);

  const auto n = _species_names.size();

  _molar_masses.resize(n);
  _transport_aliases.resize(n);
  _mass_fractions.reserve(n);

  for (std::size_t i = 0; i < n; ++i)
  {
    const auto it = _species_database.find(_species_names[i]);
    if (it == _species_database.end())
      paramError("species",
                 "Species '",
                 _species_names[i],
                 "' is not defined in transport database '",
                 _transport_data_file,
                 "'.");

    if (it->second.molar_mass <= 0.0)
      mooseError("Invalid molar mass for species '", _species_names[i], "'.");

    _molar_masses[i] = it->second.molar_mass;
    _transport_aliases[i] = it->second.transport_alias;
    _mass_fractions.push_back(&getFunctorByName<ADReal>(_mass_fraction_names[i]));
  }

  for (std::size_t i = 0; i < n; ++i)
    for (std::size_t j = i; j < n; ++j)
    {
      if (isChargedChargedPair(_transport_aliases[i], _transport_aliases[j]))
        _has_charged_charged_pairs = true;
      else
        (void)collisionTable(_transport_aliases[i], _transport_aliases[j]);
    }

  if (_has_charged_charged_pairs)
  {
    if (!isParamValid("electron_temperature"))
      paramError(
          "electron_temperature",
          "electron_temperature is required when the active species set contains a charged-charged transport pair.");

    if (!isParamValid("electron_number_density"))
      paramError(
          "electron_number_density",
          "electron_number_density is required when the active species set contains a charged-charged transport pair.");

    _electron_temperature = &getFunctor<ADReal>("electron_temperature");
    _electron_number_density = &getFunctor<ADReal>("electron_number_density");
  }

  if (isParamValid("D_T_names"))
    _D_T_names = getParam<std::vector<MooseFunctorName>>("D_T_names");
  else
    for (const auto & species : _species_names)
      _D_T_names.emplace_back("D_T_" + species);

  if (isParamValid("kT_names"))
    _kT_names = getParam<std::vector<MooseFunctorName>>("kT_names");
  else
    for (const auto & species : _species_names)
      _kT_names.emplace_back("kT_" + species);

  if (_D_T_names.size() != n)
    paramError("D_T_names", "D_T_names must have one entry per active species.");

  if (_kT_names.size() != n)
    paramError("kT_names", "kT_names must have one entry per active species.");

  if (isParamValid("D_mix_names"))
    _D_mix_names = getParam<std::vector<MooseFunctorName>>("D_mix_names");
  else
    for (const auto & species : _species_names)
      _D_mix_names.emplace_back("D_mix_" + species);

  if (_D_mix_names.size() != n)
    paramError("D_mix_names", "D_mix_names must have one entry per active species.");

  for (std::size_t i = 0; i < n; ++i)
  {
    addFunctorProperty<ADReal>(
        _D_T_names[i],
        [this, i](const auto & r, const auto & state) -> ADReal
        {
          Vec Y(_mass_fractions.size());
          for (std::size_t j = 0; j < _mass_fractions.size(); ++j)
            Y[j] = (*_mass_fractions[j])(r, state);

          const ADReal Te =
              _has_charged_charged_pairs ? (*_electron_temperature)(r, state) : ADReal(0.0);
          const ADReal ne =
              _has_charged_charged_pairs ? (*_electron_number_density)(r, state) : ADReal(0.0);

          return evaluate(_temperature(r, state), _pressure(r, state), Te, ne, Y).D_T[i];
        });

    addFunctorProperty<ADReal>(
        _kT_names[i],
        [this, i](const auto & r, const auto & state) -> ADReal
        {
          Vec Y(_mass_fractions.size());
          for (std::size_t j = 0; j < _mass_fractions.size(); ++j)
            Y[j] = (*_mass_fractions[j])(r, state);

          const ADReal Te =
              _has_charged_charged_pairs ? (*_electron_temperature)(r, state) : ADReal(0.0);
          const ADReal ne =
              _has_charged_charged_pairs ? (*_electron_number_density)(r, state) : ADReal(0.0);

          return evaluate(_temperature(r, state), _pressure(r, state), Te, ne, Y).kT[i];
        });

    addFunctorProperty<ADReal>(
      _D_mix_names[i],
      [this, i](const auto & r, const auto & state) -> ADReal
      {
        Vec Y(_mass_fractions.size());
        for (std::size_t j = 0; j < _mass_fractions.size(); ++j)
          Y[j] = (*_mass_fractions[j])(r, state);

        const ADReal Te =
            _has_charged_charged_pairs ? (*_electron_temperature)(r, state) : ADReal(0.0);
        const ADReal ne =
            _has_charged_charged_pairs ? (*_electron_number_density)(r, state) : ADReal(0.0);

        return evaluateDmix(
            i,
            _temperature(r, state),
            _pressure(r, state),
            Te,
            ne,
            Y);
      });
  }
}

std::string
PhysicsThermalDiffusionMaterial::trim(const std::string & s)
{
  const auto first = s.find_first_not_of(" \t\r\n");
  if (first == std::string::npos)
    return "";

  const auto last = s.find_last_not_of(" \t\r\n");
  return s.substr(first, last - first + 1);
}

std::string
PhysicsThermalDiffusionMaterial::pairKey(std::string a, std::string b)
{
  if (b < a)
    std::swap(a, b);

  return a + "|" + b;
}

void
PhysicsThermalDiffusionMaterial::loadTransportDatabase(const FileName & filename)
{
  std::ifstream in(filename.c_str());
  if (!in.good())
    mooseError("PhysicsThermalDiffusionMaterial could not open transport database '",
               filename,
               "'.");

  bool in_pair = false;
  std::string current_pair_key;
  CollisionTable current_table;

  std::string line;
  unsigned int line_number = 0;

  while (std::getline(in, line))
  {
    ++line_number;

    const auto hash = line.find('#');
    if (hash != std::string::npos)
      line.erase(hash);

    line = trim(line);
    if (line.empty())
      continue;

    std::istringstream iss(line);
    std::string keyword;
    iss >> keyword;

    if (!in_pair)
    {
      if (keyword == "species")
      {
        std::string name;
        Real molar_mass = 0.0;
        std::string alias;

        if (!(iss >> name >> molar_mass >> alias))
          mooseError("Malformed species line in '",
                     filename,
                     "' at line ",
                     line_number,
                     ". Expected: species <name> <molar_mass_kg_per_mol> <transport_alias>");

        if (_species_database.count(name))
          mooseError("Duplicate species '",
                     name,
                     "' in transport database '",
                     filename,
                     "'.");

        _species_database[name] = {molar_mass, alias};
      }
      else if (keyword == "pair")
      {
        std::string a;
        std::string b;

        current_table = CollisionTable();

        if (!(iss >> a >> b >> current_table.Bstar >> current_table.Cstar))
          mooseError("Malformed pair line in '",
                     filename,
                     "' at line ",
                     line_number,
                     ". Expected: pair <alias_a> <alias_b> <Bstar> <Cstar>");

        current_pair_key = pairKey(a, b);

        if (_collision_database.count(current_pair_key))
          mooseError("Duplicate collision pair '",
                     current_pair_key,
                     "' in transport database '",
                     filename,
                     "'.");

        in_pair = true;
      }
      else
        mooseError("Unknown keyword '",
                   keyword,
                   "' in transport database '",
                   filename,
                   "' at line ",
                   line_number,
                   ".");
    }
    else
    {
      if (keyword == "endpair")
      {
        if (current_table.T.size() < 2)
          mooseError("Collision pair '",
                     current_pair_key,
                     "' in '",
                     filename,
                     "' must contain at least two table rows.");

        for (std::size_t i = 1; i < current_table.T.size(); ++i)
          if (!(current_table.T[i] > current_table.T[i - 1]))
            mooseError("Temperature grid for pair '",
                       current_pair_key,
                       "' in '",
                       filename,
                       "' must be strictly increasing.");

        _collision_database[current_pair_key] = current_table;
        in_pair = false;
      }
      else
      {
        Real T = 0.0;
        Real q11 = 0.0;
        Real q22 = 0.0;

        std::istringstream row(line);
        if (!(row >> T >> q11 >> q22))
          mooseError("Malformed collision-table row in '",
                     filename,
                     "' at line ",
                     line_number,
                     ". Expected: <T_K> <Q11_Angstrom2> <Q22_Angstrom2>");

        if (T <= 0.0 || q11 <= 0.0 || q22 <= 0.0)
          mooseError("Collision-table values must be positive in '",
                     filename,
                     "' at line ",
                     line_number,
                     ".");

        current_table.T.push_back(T);
        current_table.Q11.push_back(q11);
        current_table.Q22.push_back(q22);
      }
    }
  }

  if (in_pair)
    mooseError("Transport database '",
               filename,
               "' ended before 'endpair' for collision pair '",
               current_pair_key,
               "'.");

  if (_species_database.empty())
    mooseError("Transport database '", filename, "' defines no species.");

  if (_collision_database.empty())
    mooseError("Transport database '", filename, "' defines no collision pairs.");
}

const PhysicsThermalDiffusionMaterial::CollisionTable &
PhysicsThermalDiffusionMaterial::collisionTable(const std::string & alias_a,
                                                 const std::string & alias_b) const
{
  const auto key = pairKey(alias_a, alias_b);
  const auto it = _collision_database.find(key);

  if (it == _collision_database.end())
    mooseError("No collision table for transport aliases '",
               alias_a,
               "' and '",
               alias_b,
               "' in database '",
               _transport_data_file,
               "'.");

  return it->second;
}

int
PhysicsThermalDiffusionMaterial::aliasCharge(const std::string & alias)
{
  if (alias.empty())
    return 0;

  if (alias.back() == '+')
    return 1;

  if (alias.back() == '-')
    return -1;

  return 0;
}

bool
PhysicsThermalDiffusionMaterial::isChargedChargedPair(const std::string & alias_a,
                                                       const std::string & alias_b)
{
  return aliasCharge(alias_a) != 0 && aliasCharge(alias_b) != 0;
}

PhysicsThermalDiffusionMaterial::CollisionData
PhysicsThermalDiffusionMaterial::debyeHuckelCollisionData(const ADReal & T,
                                                           const ADReal & Te,
                                                           const ADReal & ne,
                                                           const CoulombBranch branch) const
{
  if (T.value() <= 0.0)
    mooseError("Debye-Huckel collision evaluation requires T > 0 K.");

  if (Te.value() <= 0.0)
    mooseError("Debye-Huckel collision evaluation requires electron_temperature > 0 K. Got ",
               Te.value());

  if (ne.value() < 0.0)
    mooseError("Debye-Huckel collision evaluation requires electron_number_density >= 0. Got ",
               ne.value());

  using std::sqrt;

  const ADReal b =
      QE * QE / (8.0 * PHYSICS_CONSTANTS::pi * EPS0 * PHYSICS_CONSTANTS::k_boltz * T);

  const ADReal ne_eff = positiveFloor(ne, DEBYE_NE_FLOOR);
  const ADReal lambda_raw =
      sqrt(0.5 * EPS0 * PHYSICS_CONSTANTS::k_boltz * Te / (ne_eff * QE * QE));

  const ADReal lambda_max = 2.0 * DEBYE_TSTAR.back() * b;
  ADReal lambda_D = lambda_raw.value() < lambda_max.value() ? lambda_raw : lambda_max;

  ADReal Tstar = 0.5 * lambda_D / b;
  if (Tstar.value() < DEBYE_TSTAR.front())
    Tstar = DEBYE_TSTAR.front();
  else if (Tstar.value() > DEBYE_TSTAR.back())
    Tstar = DEBYE_TSTAR.back();

  std::size_t upper = 0;
  if (Tstar.value() <= DEBYE_TSTAR.front())
    upper = 0;
  else if (Tstar.value() >= DEBYE_TSTAR.back())
    upper = DEBYE_TSTAR.size() - 1;
  else
  {
    const auto it = std::upper_bound(DEBYE_TSTAR.begin(), DEBYE_TSTAR.end(), Tstar.value());
    upper = static_cast<std::size_t>(it - DEBYE_TSTAR.begin());
  }

  auto reducedValue = [&](const std::size_t column) -> ADReal
  {
    if (upper == 0)
      return DEBYE_TABLE.front()[column];

    if (upper >= DEBYE_TSTAR.size())
      return DEBYE_TABLE.back()[column];

    if (Tstar.value() >= DEBYE_TSTAR.back())
      return DEBYE_TABLE.back()[column];

    const std::size_t lower = upper - 1;
    return DEBYE_TABLE[lower][column] +
           (Tstar - DEBYE_TSTAR[lower]) *
               (DEBYE_TABLE[upper][column] - DEBYE_TABLE[lower][column]) /
               (DEBYE_TSTAR[upper] - DEBYE_TSTAR[lower]);
  };

  const std::size_t branch_offset = branch == CoulombBranch::ATTRACTIVE ? 0 : 1;
  const ADReal scale =
      PHYSICS_CONSTANTS::pi * lambda_D * lambda_D / (Tstar * Tstar);

  CollisionData data;
  data.Q11 = reducedValue(branch_offset) * scale;
  data.Q22 = reducedValue(2 + branch_offset) * scale;
  data.Bstar = reducedValue(4 + branch_offset);
  data.Cstar = reducedValue(6 + branch_offset);
  return data;
}

PhysicsThermalDiffusionMaterial::CollisionData
PhysicsThermalDiffusionMaterial::collisionData(const ADReal & T,
                                                const ADReal & Te,
                                                const ADReal & ne,
                                                const std::string & alias_a,
                                                const std::string & alias_b) const
{
  const int charge_a = aliasCharge(alias_a);
  const int charge_b = aliasCharge(alias_b);

  if (charge_a != 0 && charge_b != 0)
  {
    const auto branch = charge_a * charge_b < 0 ? CoulombBranch::ATTRACTIVE
                                                : CoulombBranch::REPULSIVE;
    return debyeHuckelCollisionData(T, Te, ne, branch);
  }

  const auto & table = collisionTable(alias_a, alias_b);

  CollisionData data;
  data.Q11 = interpolateCollisionIntegral(T, table.T, table.Q11);
  data.Q22 = interpolateCollisionIntegral(T, table.T, table.Q22);
  data.Bstar = table.Bstar;
  data.Cstar = table.Cstar;
  return data;
}

ADReal
PhysicsThermalDiffusionMaterial::positiveFloor(const ADReal & value, const Real floor)
{
  return value.value() < floor ? ADReal(floor) : value;
}

ADReal
PhysicsThermalDiffusionMaterial::interpolateCollisionIntegral(
    const ADReal & T,
    const std::vector<Real> & grid,
    const std::vector<Real> & values) const
{
  if (grid.size() != values.size() || grid.size() < 2)
    mooseError("Invalid collision table in '", _transport_data_file, "'.");

  const Real T_raw = T.value();

  if (T_raw <= grid.front())
    return values.front() * PHYSICS_CONSTANTS::pi * ANGSTROM2_TO_M2;

  if (T_raw >= grid.back())
    return values.back() * PHYSICS_CONSTANTS::pi * ANGSTROM2_TO_M2;

  const auto upper = std::upper_bound(grid.begin(), grid.end(), T_raw);
  const std::size_t i = static_cast<std::size_t>(upper - grid.begin() - 1);

  const ADReal q =
      values[i] +
      (T - grid[i]) * (values[i + 1] - values[i]) / (grid[i + 1] - grid[i]);

  return q * PHYSICS_CONSTANTS::pi * ANGSTROM2_TO_M2;
}

PhysicsThermalDiffusionMaterial::Vec
PhysicsThermalDiffusionMaterial::solveSystem(Mat A, Vec b) const
{
  const std::size_t n = A.size();

  if (n == 0 || b.size() != n)
    mooseError("PhysicsThermalDiffusionMaterial received an invalid linear system.");

  for (const auto & row : A)
    if (row.size() != n)
      mooseError("PhysicsThermalDiffusionMaterial requires a square linear system.");

  Real scale = 0.0;
  for (const auto & row : A)
    for (const auto & a : row)
      scale = std::max(scale, std::abs(a.value()));

  if (scale == 0.0)
    mooseError("PhysicsThermalDiffusionMaterial encountered a zero transport matrix.");

  for (std::size_t k = 0; k < n; ++k)
  {
    std::size_t pivot = k;
    Real pivot_abs = std::abs(A[k][k].value());

    for (std::size_t i = k + 1; i < n; ++i)
    {
      const Real candidate = std::abs(A[i][k].value());
      if (candidate > pivot_abs)
      {
        pivot = i;
        pivot_abs = candidate;
      }
    }

    if (pivot_abs <= 1.0e-14 * scale)
      mooseError("PhysicsThermalDiffusionMaterial encountered a singular/ill-conditioned ",
                 n,
                 "x",
                 n,
                 " transport matrix at column ",
                 k,
                 ". pivot=",
                 pivot_abs,
                 ", scale=",
                 scale);

    if (pivot != k)
    {
      std::swap(A[pivot], A[k]);
      std::swap(b[pivot], b[k]);
    }

    for (std::size_t i = k + 1; i < n; ++i)
    {
      const ADReal factor = A[i][k] / A[k][k];
      A[i][k] = 0.0;

      for (std::size_t j = k + 1; j < n; ++j)
        A[i][j] -= factor * A[k][j];

      b[i] -= factor * b[k];
    }
  }

  Vec x(n, 0.0);

  for (int ii = static_cast<int>(n) - 1; ii >= 0; --ii)
  {
    ADReal rhs = b[ii];

    for (std::size_t j = static_cast<std::size_t>(ii) + 1; j < n; ++j)
      rhs -= A[ii][j] * x[j];

    x[ii] = rhs / A[ii][ii];
  }

  return x;
}

PhysicsThermalDiffusionMaterial::Result
PhysicsThermalDiffusionMaterial::evaluate(const ADReal & T,
                                          const ADReal & p,
                                          const ADReal & Te,
                                          const ADReal & ne,
                                          const Vec & Y) const
{
  const std::size_t n = _species_names.size();

  if (T.value() <= 0.0)
    mooseError("PhysicsThermalDiffusionMaterial requires T > 0 K. Got ", T.value());

  if (p.value() <= 0.0)
    mooseError("PhysicsThermalDiffusionMaterial requires absolute p > 0 Pa. Got ", p.value());

  if (Y.size() != n)
    mooseError("Internal species/mass-fraction size mismatch.");

  if (_has_charged_charged_pairs)
  {
    if (Te.value() <= 0.0)
      mooseError("PhysicsThermalDiffusionMaterial requires electron_temperature > 0 K when charged-charged pairs are active. Got ",
                 Te.value());

    if (ne.value() < 0.0)
      mooseError("PhysicsThermalDiffusionMaterial requires electron_number_density >= 0 when charged-charged pairs are active. Got ",
                 ne.value());
  }

  ADReal Y_sum = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    if (Y[i].value() < 0.0)
      mooseError("PhysicsThermalDiffusionMaterial requires non-negative mass fractions. "
                 "Species '",
                 _species_names[i],
                 "' has Y=",
                 Y[i].value());

    Y_sum += Y[i];
  }

  if (std::abs(Y_sum.value() - 1.0) > 1.0e-10)
    mooseError("PhysicsThermalDiffusionMaterial requires sum(Y)=1. Got ", Y_sum.value());

  ADReal mole_denominator = 0.0;
  for (std::size_t i = 0; i < n; ++i)
    mole_denominator += Y[i] / _molar_masses[i];

  Vec X(n);
  for (std::size_t i = 0; i < n; ++i)
    X[i] = (Y[i] / _molar_masses[i]) / mole_denominator;

  Vec X_alpha(n);
  for (std::size_t i = 0; i < n; ++i)
    X_alpha[i] = positiveFloor(X[i], 1.0e-16);

  Vec X_sm(n);
  ADReal X_sm_sum = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    X_sm[i] = X[i] + 1.0e-16;
    X_sm_sum += X_sm[i];
  }
  for (std::size_t i = 0; i < n; ++i)
    X_sm[i] /= X_sm_sum;

  Mat q11(n, Vec(n, 0.0));
  Mat q22(n, Vec(n, 0.0));
  Mat Ast(n, Vec(n, 0.0));
  Mat Bst(n, Vec(n, 0.0));
  Mat Cst(n, Vec(n, 0.0));
  Mat nDij(n, Vec(n, 0.0));

  std::vector<Real> particle_mass(n);
  for (std::size_t i = 0; i < n; ++i)
    particle_mass[i] = _molar_masses[i] / PHYSICS_CONSTANTS::N_A;

  using std::sqrt;

  for (std::size_t i = 0; i < n; ++i)
    for (std::size_t j = i; j < n; ++j)
    {
      const auto data = collisionData(
          T, Te, ne, _transport_aliases[i], _transport_aliases[j]);

      q11[i][j] = q11[j][i] = data.Q11;
      q22[i][j] = q22[j][i] = data.Q22;
      Ast[i][j] = Ast[j][i] = data.Q22 / data.Q11;
      Bst[i][j] = Bst[j][i] = data.Bstar;
      Cst[i][j] = Cst[j][i] = data.Cstar;

      const Real fac =
          (3.0 / 16.0) *
          std::sqrt(2.0 * PHYSICS_CONSTANTS::pi * PHYSICS_CONSTANTS::k_boltz * (particle_mass[i] + particle_mass[j]) /
                    (particle_mass[i] * particle_mass[j]));

      const ADReal nd = sqrt(T) * fac / data.Q11;
      nDij[i][j] = nDij[j][i] = nd;
    }

  const ADReal number_density = p / (PHYSICS_CONSTANTS::k_boltz * T);

  Vec D_mix(n, 0.0);
  for (std::size_t i = 0; i < n; ++i)
  {
    const ADReal one_minus_Y = 1.0 - Y[i];

    if (one_minus_Y.value() <= 1.0e-16)
    {
      D_mix[i] = 0.0;
      continue;
    }

    ADReal denominator = 0.0;
    for (std::size_t j = 0; j < n; ++j)
    {
      if (j == i)
        continue;

      const ADReal Dij = nDij[i][j] / number_density;
      if (Dij.value() <= 0.0)
        mooseError("PhysicsThermalDiffusionMaterial obtained non-positive binary diffusion coefficient for species '",
                   _species_names[i],
                   "' and '",
                   _species_names[j],
                   "'. D_ij=",
                   Dij.value());

      denominator += X[j] / Dij;
    }

    if (denominator.value() <= 0.0)
      mooseError("PhysicsThermalDiffusionMaterial could not construct positive D_k,m for species '",
                 _species_names[i],
                 "'. denominator=",
                 denominator.value());

    D_mix[i] = one_minus_Y / denominator;
  }

  Vec eta(n, 0.0);
  for (std::size_t i = 0; i < n; ++i)
  {
    const Real eta_fac =
        (5.0 / 16.0) * std::sqrt(PHYSICS_CONSTANTS::pi * PHYSICS_CONSTANTS::k_boltz) * std::sqrt(particle_mass[i]);

    eta[i] = sqrt(T) * eta_fac / q22[i][i];
  }

  Mat ce(n, Vec(n, 0.0));

  for (std::size_t i = 0; i < n; ++i)
    ce[i][i] =
        (4.0 / (15.0 * PHYSICS_CONSTANTS::k_boltz)) * X_alpha[i] * X_alpha[i] * particle_mass[i] / eta[i];

  for (std::size_t i = 1; i < n; ++i)
    for (std::size_t j = 0; j < i; ++j)
    {
      const Real mi = particle_mass[i];
      const Real mj = particle_mass[j];
      const Real miij = mi / (mi + mj);
      const Real mjij = mj / (mi + mj);

      const ADReal fac = X_alpha[i] * X_alpha[j] / (nDij[i][j] * 25.0 * PHYSICS_CONSTANTS::k_boltz);

      const ADReal lower =
          fac * miij * mjij * (16.0 * Ast[i][j] + 12.0 * Bst[i][j] - 55.0);

      ce[i][j] = lower;
      ce[j][i] = lower;

      ce[i][i] +=
          fac * (miij * (30.0 * miij + 16.0 * mjij * Ast[i][j]) +
                 mjij * mjij * (25.0 - 12.0 * Bst[i][j]));

      ce[j][j] +=
          fac * (mjij * (30.0 * mjij + 16.0 * miij * Ast[i][j]) +
                 miij * miij * (25.0 - 12.0 * Bst[i][j]));
    }

  const Vec alpha = solveSystem(ce, X_alpha);

  Mat ratio(n, Vec(n, 0.0));

  for (std::size_t i = 1; i < n; ++i)
    for (std::size_t j = 0; j < i; ++j)
    {
      const Real mi = particle_mass[i];
      const Real mj = particle_mass[j];

      const ADReal fac =
          X_alpha[i] * X_alpha[j] / (mi + mj) *
          (1.2 * Cst[i][j] - 1.0) / nDij[i][j];

      ratio[i][j] = fac * mi;
      ratio[j][i] = fac * mj;
      ratio[i][i] -= ratio[j][i];
      ratio[j][j] -= ratio[i][j];
    }

  Vec kT(n, 0.0);
  for (std::size_t i = 0; i < n; ++i)
  {
    for (std::size_t j = 0; j < n; ++j)
      kT[i] += ratio[i][j] * alpha[j];

    kT[i] /= PHYSICS_CONSTANTS::k_boltz;
  }

  Mat G(n, Vec(n, 0.0));

  for (std::size_t i = 0; i < n; ++i)
    for (std::size_t j = i + 1; j < n; ++j)
    {
      const ADReal fac = X_sm[i] * X_sm[j] / nDij[i][j] * number_density;

      G[i][j] = -fac;
      G[i][i] += fac;
      G[j][i] = -fac;
      G[j][j] += fac;
    }

  ADReal mass_denominator_sm = 0.0;
  for (std::size_t i = 0; i < n; ++i)
    mass_denominator_sm += X_sm[i] * _molar_masses[i];

  Vec Y_sm(n);
  for (std::size_t i = 0; i < n; ++i)
    Y_sm[i] = X_sm[i] * _molar_masses[i] / mass_denominator_sm;

  std::size_t max_diag = 0;
  for (std::size_t i = 1; i < n; ++i)
    if (G[i][i].value() > G[max_diag][max_diag].value())
      max_diag = i;

  const ADReal a = G[max_diag][max_diag];

  for (std::size_t i = 0; i < n; ++i)
    for (std::size_t j = 0; j < n; ++j)
      G[i][j] += a * Y_sm[i] * Y_sm[j];

  Vec driving(n);
  for (std::size_t i = 0; i < n; ++i)
    driving[i] = -kT[i] / T;

  Vec V = solveSystem(G, driving);

  ADReal mass_average_velocity = 0.0;
  for (std::size_t i = 0; i < n; ++i)
    mass_average_velocity += V[i] * Y[i];

  for (std::size_t i = 0; i < n; ++i)
    V[i] -= mass_average_velocity;

  // Physics mass-flux coefficient:
  //   rho Y_i V_i = -D_T,i grad(T)/T
  const ADReal mean_molar_mass = 1.0 / mole_denominator;
  const ADReal rho = p * mean_molar_mass / (PHYSICS_CONSTANTS::R * T);

  Vec D_T(n);
  for (std::size_t i = 0; i < n; ++i)
    D_T[i] = -rho * Y[i] * V[i] * T;

  return {kT, D_T, V, D_mix};
}

ADReal
PhysicsThermalDiffusionMaterial::evaluateDmix(const std::size_t species_i,
                                              const ADReal & T,
                                              const ADReal & p,
                                              const ADReal & Te,
                                              const ADReal & ne,
                                              const Vec & Y) const
{
  const std::size_t n = _species_names.size();

  if (species_i >= n)
    mooseError("PhysicsThermalDiffusionMaterial received invalid species index ",
               species_i,
               " for D_mix evaluation.");

  if (T.value() <= 0.0)
    mooseError("PhysicsThermalDiffusionMaterial requires T > 0 K. Got ", T.value());

  if (p.value() <= 0.0)
    mooseError("PhysicsThermalDiffusionMaterial requires absolute p > 0 Pa. Got ", p.value());

  if (Y.size() != n)
    mooseError("Internal species/mass-fraction size mismatch.");

  if (_has_charged_charged_pairs)
  {
    if (Te.value() <= 0.0)
      mooseError(
          "PhysicsThermalDiffusionMaterial requires electron_temperature > 0 K "
          "when charged-charged pairs are active. Got ",
          Te.value());

    if (ne.value() < 0.0)
      mooseError(
          "PhysicsThermalDiffusionMaterial requires electron_number_density >= 0 "
          "when charged-charged pairs are active. Got ",
          ne.value());
  }

  ADReal Y_sum = 0.0;
  ADReal mole_denominator = 0.0;

  for (std::size_t j = 0; j < n; ++j)
  {
    if (Y[j].value() < 0.0)
      mooseError("PhysicsThermalDiffusionMaterial requires non-negative mass fractions. "
                 "Species '",
                 _species_names[j],
                 "' has Y=",
                 Y[j].value());

    Y_sum += Y[j];
    mole_denominator += Y[j] / _molar_masses[j];
  }

  if (std::abs(Y_sum.value() - 1.0) > 1.0e-10)
    mooseError("PhysicsThermalDiffusionMaterial requires sum(Y)=1. Got ", Y_sum.value());

  const ADReal one_minus_Y = 1.0 - Y[species_i];

  if (one_minus_Y.value() <= 1.0e-16)
    return 0.0;

  const ADReal number_density =
      p / (PHYSICS_CONSTANTS::k_boltz * T);

  const Real particle_mass_i =
      _molar_masses[species_i] / PHYSICS_CONSTANTS::N_A;

  ADReal denominator = 0.0;

  using std::sqrt;

  for (std::size_t j = 0; j < n; ++j)
  {
    if (j == species_i)
      continue;

    const std::size_t pair_i =
        species_i < j ? species_i : j;

    const std::size_t pair_j =
        species_i < j ? j : species_i;

    const auto data =
        collisionData(T,
                      Te,
                      ne,
                      _transport_aliases[pair_i],
                      _transport_aliases[pair_j]);

    const Real particle_mass_j =
        _molar_masses[j] / PHYSICS_CONSTANTS::N_A;

    const Real fac =
        (3.0 / 16.0) *
        std::sqrt(
            2.0 *
            PHYSICS_CONSTANTS::pi *
            PHYSICS_CONSTANTS::k_boltz *
            (particle_mass_i + particle_mass_j) /
            (particle_mass_i * particle_mass_j));

    const ADReal nDij =
        sqrt(T) * fac / data.Q11;

    const ADReal Dij =
        nDij / number_density;

    if (Dij.value() <= 0.0)
      mooseError(
          "PhysicsThermalDiffusionMaterial obtained non-positive binary diffusion "
          "coefficient for species '",
          _species_names[species_i],
          "' and '",
          _species_names[j],
          "'. D_ij=",
          Dij.value());

    const ADReal Xj =
        (Y[j] / _molar_masses[j]) / mole_denominator;

    denominator += Xj / Dij;
  }

  if (denominator.value() <= 0.0)
    mooseError(
        "PhysicsThermalDiffusionMaterial could not construct positive D_k,m for species '",
        _species_names[species_i],
        "'. denominator=",
        denominator.value());

  return one_minus_Y / denominator;
}
