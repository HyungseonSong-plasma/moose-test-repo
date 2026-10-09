#include "PhysicsIonWallFluxMaterial.h"

#include "Physics.h"
#include "FaceInfo.h"
#include "MooseFunctorArguments.h"

#include <cmath>
#include <string>
#include <type_traits>

registerMooseObject("PhysicsApp", PhysicsIonWallFluxMaterial);

namespace
{
template <typename SpaceArg>
constexpr bool
isFaceArg()
{
  return std::is_same_v<std::decay_t<SpaceArg>, Moose::FaceArg>;
}

ADReal
outwardPositivePart(const ADReal & directed_field, const Real smoothing_width)
{
  if (smoothing_width <= 0.0)
    return MetaPhysicL::raw_value(directed_field) > 0.0
               ? directed_field
               : ADReal(0.0) * directed_field;

  using std::tanh;
  return 0.5 * directed_field *
         (1.0 + tanh(directed_field / smoothing_width));
}

RealVectorValue
outwardNormal(const Moose::FaceArg & face)
{
  if (!face.fi)
    mooseError("PhysicsIonWallFluxMaterial received a FaceArg without FaceInfo.");

  RealVectorValue n = face.fi->normal();

  if (face.face_side)
  {
    if (face.face_side == &face.fi->elem())
      return n;

    if (face.fi->neighborPtr() && face.face_side == face.fi->neighborPtr())
      return -n;

    mooseError(
        "PhysicsIonWallFluxMaterial received a FaceArg whose face_side does not "
        "match either FaceInfo side.");
  }

  if (face.fi->neighborPtr())
    mooseError(
        "PhysicsIonWallFluxMaterial requires a sided FaceArg on internal boundaries.");

  return n;
}

ADRealVectorValue
faceElectricField(const Moose::Functor<ADReal> & potential,
                  const Moose::FaceArg & face,
                  const Moose::StateArg & state,
                  const bool use_element_gradient)
{
  if (!use_element_gradient)
    return -potential.gradient(face, state);

  if (!face.fi)
    mooseError("PhysicsIonWallFluxMaterial received a FaceArg without FaceInfo.");

  // Continuous FEM variables do not implement FaceArg gradients. Evaluate the
  // gradient in the element that owns the sided wall face instead. For the
  // unlikely unsided interior case, use the symmetric average of both element
  // gradients, matching the FV drift hybrid bridge.
  if (face.face_side)
  {
    if (face.face_side == &face.fi->elem())
      return -potential.gradient(face.makeElem(), state);

    if (face.fi->neighborPtr() && face.face_side == face.fi->neighborPtr())
      return -potential.gradient(face.makeNeighbor(), state);

    mooseError(
        "PhysicsIonWallFluxMaterial received a FaceArg whose face_side does not "
        "match either FaceInfo side.");
  }

  if (!face.fi->neighborPtr())
    return -potential.gradient(face.makeElem(), state);

  return -0.5 * (potential.gradient(face.makeElem(), state) +
                 potential.gradient(face.makeNeighbor(), state));
}
}

InputParameters
PhysicsIonWallFluxMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Provides face-local ion surface, migration, and total wall-loss fluxes "
      "from species density and electrostatic potential. The thermal surface "
      "speed may use either gas_temperature or a user-defined ion_temperature_eV.");

  params.addRequiredParam<MooseFunctorName>(
      "ion_number_density", "Ion number density n_i [1/m^3].");

  params.addRequiredParam<MooseFunctorName>(
      "potential", "Electrostatic potential phi [V].");

  params.addRequiredParam<MooseFunctorName>(
      "mobility", "Positive ion mobility magnitude [m^2/(V s)].");

  params.addRequiredParam<MooseFunctorName>(
      "gas_temperature",
      "Heavy-particle temperature T_g [K], used for the thermal wall speed when "
      "ion_temperature_eV is zero.");

  params.addRequiredParam<Real>(
      "charge_number", "Signed charge number z_i.");

  params.addRequiredParam<Real>(
      "molar_mass", "Species molar mass M_i [kg/mol].");

  params.addParam<Real>(
      "sticking", 1.0, "Surface sticking/neutralization probability.");

  params.addParam<Real>(
      "ion_temperature_eV",
      0.0,
      "User-defined ion temperature [eV] used only for the thermal surface velocity. "
      "A value of zero preserves the existing behavior and uses gas_temperature.");

  params.addParam<Real>(
      "migration_gate_smoothing_width",
      0.0,
      "Diagnostic smoothing width [V/m] for the outward migration gate. "
      "Zero preserves the existing hard active-set behavior.");

  params.addParam<bool>(
      "use_element_gradient_for_potential",
      false,
      "Evaluate E=-grad(phi) from the sided adjacent element instead of a FaceArg. "
      "Enable this when potential is a continuous FEM variable.");

  params.addParam<std::string>(
      "property_prefix",
      "",
      "Optional prefix prepended to all generated ion wall-flux functor names. "
      "The empty default preserves the historical ion_* names.");

  return params;
}

PhysicsIonWallFluxMaterial::PhysicsIonWallFluxMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _ion_number_density(getFunctor<ADReal>("ion_number_density")),
    _potential(getFunctor<ADReal>("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
    _gas_temperature(getFunctor<ADReal>("gas_temperature")),
    _charge_number(getParam<Real>("charge_number")),
    _molar_mass(getParam<Real>("molar_mass")),
    _sticking(getParam<Real>("sticking")),
    _ion_temperature_eV(getParam<Real>("ion_temperature_eV")),
    _migration_gate_smoothing_width(
        getParam<Real>("migration_gate_smoothing_width")),
    _use_element_gradient_for_potential(
        getParam<bool>("use_element_gradient_for_potential"))
{
  if (_charge_number == 0.0)
    paramError("charge_number", "Ion wall migration requires nonzero charge_number.");

  if (_molar_mass <= 0.0)
    paramError("molar_mass", "molar_mass must be positive.");

  if (_sticking < 0.0 || _sticking > 1.0)
    paramError("sticking", "sticking must lie in [0,1].");

  if (_ion_temperature_eV < 0.0)
    paramError("ion_temperature_eV", "ion_temperature_eV must be nonnegative.");

  if (_migration_gate_smoothing_width < 0.0)
    paramError(
        "migration_gate_smoothing_width",
        "migration_gate_smoothing_width must be nonnegative.");

  const std::string property_prefix = getParam<std::string>("property_prefix");

  addFunctorProperty<ADReal>(
      property_prefix + "ion_surface_number_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);

        if constexpr (!isFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          using std::sqrt;

          const ADReal n_i = _ion_number_density(r, state);
          const ADReal T_i =
              _ion_temperature_eV > 0.0
                  ? ADReal(_ion_temperature_eV / PHYSICS_CONSTANTS::k_boltzeV)
                  : _gas_temperature(r, state);

          if (MetaPhysicL::raw_value(T_i) <= 0.0)
            mooseError("PhysicsIonWallFluxMaterial requires ion thermal temperature > 0 K.");

          const ADReal v_th =
              sqrt(8.0 * PHYSICS_CONSTANTS::R * T_i /
                   (PHYSICS_CONSTANTS::pi * _molar_mass));

          return _sticking * 0.25 * n_i * v_th;
        }
      });

  addFunctorProperty<ADReal>(
      property_prefix + "ion_migration_number_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);

        if constexpr (!isFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          const RealVectorValue n_out = outwardNormal(r);
          const ADRealVectorValue electric_field =
              faceElectricField(_potential, r, state, _use_element_gradient_for_potential);
          const ADReal E_n = electric_field * n_out;

          const ADReal directed_field = _charge_number * E_n;
          const ADReal outward_drift_field =
              outwardPositivePart(
                  directed_field, _migration_gate_smoothing_width);

          return _ion_number_density(r, state) *
                 _mobility(r, state) *
                 outward_drift_field;
        }
      });

  addFunctorProperty<ADReal>(
      property_prefix + "ion_wall_number_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);

        if constexpr (!isFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          using std::sqrt;

          const ADReal n_i = _ion_number_density(r, state);
          const ADReal T_i =
              _ion_temperature_eV > 0.0
                  ? ADReal(_ion_temperature_eV / PHYSICS_CONSTANTS::k_boltzeV)
                  : _gas_temperature(r, state);

          if (MetaPhysicL::raw_value(T_i) <= 0.0)
            mooseError("PhysicsIonWallFluxMaterial requires ion thermal temperature > 0 K.");

          const ADReal v_th =
              sqrt(8.0 * PHYSICS_CONSTANTS::R * T_i /
                   (PHYSICS_CONSTANTS::pi * _molar_mass));

          const ADReal surface =
              _sticking * 0.25 * n_i * v_th;

          const RealVectorValue n_out = outwardNormal(r);
          const ADRealVectorValue electric_field =
              faceElectricField(_potential, r, state, _use_element_gradient_for_potential);
          const ADReal directed_field =
              _charge_number * (electric_field * n_out);
          const ADReal outward_drift_field =
              outwardPositivePart(
                  directed_field, _migration_gate_smoothing_width);

          const ADReal migration =
              n_i * _mobility(r, state) * outward_drift_field;

          return surface + migration;
        }
      });

  addFunctorProperty<ADReal>(
      property_prefix + "ion_surface_mass_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);

        if constexpr (!isFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          using std::sqrt;

          const ADReal n_i = _ion_number_density(r, state);
          const ADReal T_i =
              _ion_temperature_eV > 0.0
                  ? ADReal(_ion_temperature_eV / PHYSICS_CONSTANTS::k_boltzeV)
                  : _gas_temperature(r, state);

          if (MetaPhysicL::raw_value(T_i) <= 0.0)
            mooseError("PhysicsIonWallFluxMaterial requires ion thermal temperature > 0 K.");

          const ADReal v_th =
              sqrt(8.0 * PHYSICS_CONSTANTS::R * T_i /
                   (PHYSICS_CONSTANTS::pi * _molar_mass));

          return _sticking * 0.25 * n_i * v_th *
                 _molar_mass / PHYSICS_CONSTANTS::N_A;
        }
      });

  addFunctorProperty<ADReal>(
      property_prefix + "ion_migration_mass_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);

        if constexpr (!isFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          const RealVectorValue n_out = outwardNormal(r);
          const ADRealVectorValue electric_field =
              faceElectricField(_potential, r, state, _use_element_gradient_for_potential);
          const ADReal directed_field =
              _charge_number * (electric_field * n_out);
          const ADReal outward_drift_field =
              outwardPositivePart(
                  directed_field, _migration_gate_smoothing_width);

          return _ion_number_density(r, state) *
                 _mobility(r, state) * outward_drift_field *
                 _molar_mass / PHYSICS_CONSTANTS::N_A;
        }
      });

  addFunctorProperty<ADReal>(
      property_prefix + "ion_wall_mass_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);

        if constexpr (!isFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          using std::sqrt;

          const ADReal n_i = _ion_number_density(r, state);
          const ADReal T_i =
              _ion_temperature_eV > 0.0
                  ? ADReal(_ion_temperature_eV / PHYSICS_CONSTANTS::k_boltzeV)
                  : _gas_temperature(r, state);

          if (MetaPhysicL::raw_value(T_i) <= 0.0)
            mooseError("PhysicsIonWallFluxMaterial requires ion thermal temperature > 0 K.");

          const ADReal v_th =
              sqrt(8.0 * PHYSICS_CONSTANTS::R * T_i /
                   (PHYSICS_CONSTANTS::pi * _molar_mass));

          const ADReal surface =
              _sticking * 0.25 * n_i * v_th;

          const RealVectorValue n_out = outwardNormal(r);
          const ADRealVectorValue electric_field =
              faceElectricField(_potential, r, state, _use_element_gradient_for_potential);
          const ADReal directed_field =
              _charge_number * (electric_field * n_out);
          const ADReal outward_drift_field =
              outwardPositivePart(
                  directed_field, _migration_gate_smoothing_width);

          const ADReal migration =
              n_i * _mobility(r, state) * outward_drift_field;

          return (surface + migration) *
                 _molar_mass / PHYSICS_CONSTANTS::N_A;
        }
      });
}
