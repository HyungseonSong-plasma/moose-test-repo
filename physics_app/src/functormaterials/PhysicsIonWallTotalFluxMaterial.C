#include "FunctorMaterial.h"
#include "FaceInfo.h"
#include "MooseFunctorArguments.h"
#include "Physics.h"

#include <cmath>
#include <type_traits>

class PhysicsIonWallTotalFluxMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsIonWallTotalFluxMaterial(const InputParameters & parameters);

private:
  const Moose::Functor<ADReal> & _ion_number_density;
  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _gas_temperature;
  const Real _charge_number;
  const Real _molar_mass;
  const Real _sticking;
  const Real _ion_temperature_eV;
  const Real _migration_gate_smoothing_width;
  const bool _use_element_gradient_for_potential;
  const std::string _output_prefix;
};

registerMooseObject("PhysicsApp", PhysicsIonWallTotalFluxMaterial);

namespace
{
template <typename SpaceArg>
constexpr bool
isTotalFluxFaceArg()
{
  return std::is_same_v<std::decay_t<SpaceArg>, Moose::FaceArg>;
}

ADReal
outwardPositivePartTotal(const ADReal & directed_field, const Real smoothing_width)
{
  if (smoothing_width <= 0.0)
    return MetaPhysicL::raw_value(directed_field) > 0.0
               ? directed_field
               : ADReal(0.0) * directed_field;

  using std::tanh;
  return 0.5 * directed_field * (1.0 + tanh(directed_field / smoothing_width));
}

RealVectorValue
outwardNormalTotal(const Moose::FaceArg & face)
{
  if (!face.fi)
    mooseError("PhysicsIonWallTotalFluxMaterial received a FaceArg without FaceInfo.");

  RealVectorValue n = face.fi->normal();
  if (face.face_side)
  {
    if (face.face_side == &face.fi->elem())
      return n;
    if (face.fi->neighborPtr() && face.face_side == face.fi->neighborPtr())
      return -n;
    mooseError("PhysicsIonWallTotalFluxMaterial received a FaceArg whose face_side does not match either FaceInfo side.");
  }

  if (face.fi->neighborPtr())
    mooseError("PhysicsIonWallTotalFluxMaterial requires a sided FaceArg on internal boundaries.");
  return n;
}

ADRealVectorValue
faceElectricFieldTotal(const Moose::Functor<ADReal> & potential,
                       const Moose::FaceArg & face,
                       const Moose::StateArg & state,
                       const bool use_element_gradient)
{
  if (!use_element_gradient)
    return -potential.gradient(face, state);

  if (!face.fi)
    mooseError("PhysicsIonWallTotalFluxMaterial received a FaceArg without FaceInfo.");

  if (face.face_side)
  {
    if (face.face_side == &face.fi->elem())
      return -potential.gradient(face.makeElem(), state);
    if (face.fi->neighborPtr() && face.face_side == face.fi->neighborPtr())
      return -potential.gradient(face.makeNeighbor(), state);
    mooseError("PhysicsIonWallTotalFluxMaterial received a FaceArg whose face_side does not match either FaceInfo side.");
  }

  if (!face.fi->neighborPtr())
    return -potential.gradient(face.makeElem(), state);
  return -0.5 * (potential.gradient(face.makeElem(), state) +
                 potential.gradient(face.makeNeighbor(), state));
}
} // namespace

InputParameters
PhysicsIonWallTotalFluxMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription(
      "Provides the total outward ion wall number and mass flux with an explicit output prefix. "
      "This preserves the PhysicsIonWallFluxMaterial thermal+migration law while allowing "
      "multiple charged heavy species on one block without functor-name collisions.");
  params.addRequiredParam<MooseFunctorName>("ion_number_density", "Ion number density [1/m^3].");
  params.addRequiredParam<MooseFunctorName>("potential", "Electrostatic potential [V].");
  params.addRequiredParam<MooseFunctorName>("mobility", "Mobility magnitude [m^2/(V s)].");
  params.addRequiredParam<MooseFunctorName>("gas_temperature", "Heavy-particle temperature [K].");
  params.addRequiredParam<Real>("charge_number", "Signed charge number.");
  params.addRequiredParam<Real>("molar_mass", "Species molar mass [kg/mol].");
  params.addParam<Real>("sticking", 1.0, "Wall sticking/neutralization probability.");
  params.addParam<Real>("ion_temperature_eV", 0.0, "Optional ion temperature [eV].");
  params.addParam<Real>("migration_gate_smoothing_width", 0.0, "Outward migration gate smoothing width [V/m].");
  params.addParam<bool>("use_element_gradient_for_potential", false, "Use the sided adjacent element gradient for continuous FEM potential.");
  params.addParam<std::string>("output_prefix", "", "Prefix prepended to ion_wall_number_flux and ion_wall_mass_flux.");
  return params;
}

PhysicsIonWallTotalFluxMaterial::PhysicsIonWallTotalFluxMaterial(const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _ion_number_density(getFunctor<ADReal>("ion_number_density")),
    _potential(getFunctor<ADReal>("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
    _gas_temperature(getFunctor<ADReal>("gas_temperature")),
    _charge_number(getParam<Real>("charge_number")),
    _molar_mass(getParam<Real>("molar_mass")),
    _sticking(getParam<Real>("sticking")),
    _ion_temperature_eV(getParam<Real>("ion_temperature_eV")),
    _migration_gate_smoothing_width(getParam<Real>("migration_gate_smoothing_width")),
    _use_element_gradient_for_potential(getParam<bool>("use_element_gradient_for_potential")),
    _output_prefix(getParam<std::string>("output_prefix"))
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
    paramError("migration_gate_smoothing_width", "migration_gate_smoothing_width must be nonnegative.");

  const auto number_name = _output_prefix + "ion_wall_number_flux";
  const auto mass_name = _output_prefix + "ion_wall_mass_flux";

  addFunctorProperty<ADReal>(
      number_name,
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);
        if constexpr (!isTotalFluxFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          using std::sqrt;
          const ADReal n_i = _ion_number_density(r, state);
          const ADReal T_i = _ion_temperature_eV > 0.0
                                 ? ADReal(_ion_temperature_eV / PHYSICS_CONSTANTS::k_boltzeV)
                                 : _gas_temperature(r, state);
          if (MetaPhysicL::raw_value(T_i) <= 0.0)
            mooseError("PhysicsIonWallTotalFluxMaterial requires ion thermal temperature > 0 K.");
          const ADReal v_th = sqrt(8.0 * PHYSICS_CONSTANTS::R * T_i /
                                   (PHYSICS_CONSTANTS::pi * _molar_mass));
          const ADReal surface = _sticking * 0.25 * n_i * v_th;
          const RealVectorValue n_out = outwardNormalTotal(r);
          const ADRealVectorValue electric_field = faceElectricFieldTotal(
              _potential, r, state, _use_element_gradient_for_potential);
          const ADReal directed_field = _charge_number * (electric_field * n_out);
          const ADReal migration = n_i * _mobility(r, state) *
                                   outwardPositivePartTotal(directed_field, _migration_gate_smoothing_width);
          return surface + migration;
        }
      });

  addFunctorProperty<ADReal>(
      mass_name,
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);
        if constexpr (!isTotalFluxFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          using std::sqrt;
          const ADReal n_i = _ion_number_density(r, state);
          const ADReal T_i = _ion_temperature_eV > 0.0
                                 ? ADReal(_ion_temperature_eV / PHYSICS_CONSTANTS::k_boltzeV)
                                 : _gas_temperature(r, state);
          if (MetaPhysicL::raw_value(T_i) <= 0.0)
            mooseError("PhysicsIonWallTotalFluxMaterial requires ion thermal temperature > 0 K.");
          const ADReal v_th = sqrt(8.0 * PHYSICS_CONSTANTS::R * T_i /
                                   (PHYSICS_CONSTANTS::pi * _molar_mass));
          const ADReal surface = _sticking * 0.25 * n_i * v_th;
          const RealVectorValue n_out = outwardNormalTotal(r);
          const ADRealVectorValue electric_field = faceElectricFieldTotal(
              _potential, r, state, _use_element_gradient_for_potential);
          const ADReal directed_field = _charge_number * (electric_field * n_out);
          const ADReal migration = n_i * _mobility(r, state) *
                                   outwardPositivePartTotal(directed_field, _migration_gate_smoothing_width);
          return (surface + migration) * _molar_mass / PHYSICS_CONSTANTS::N_A;
        }
      });
}
