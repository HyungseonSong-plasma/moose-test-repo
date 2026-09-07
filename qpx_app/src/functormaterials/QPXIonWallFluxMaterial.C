#include "QPXIonWallFluxMaterial.h"

#include "QPX.h"
#include "FaceInfo.h"
#include "MooseFunctorArguments.h"

#include <cmath>
#include <type_traits>

registerMooseObject("qpxApp", QPXIonWallFluxMaterial);

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

  // Diagnostic regularization:
  //   f(x) = 0.5*x*(1 + tanh(x/eps))
  //
  // f(0)=0 while df/dx|_0 = 0.5, so the initial zero-field state keeps
  // physical zero migration flux but retains AD sensitivity to phi.
  // For |x| >> eps it approaches max(x,0). Use only for diagnosis until
  // the nonlinear wall closure is finalized.
  using std::tanh;
  return 0.5 * directed_field *
         (1.0 + tanh(directed_field / smoothing_width));
}

RealVectorValue
outwardNormal(const Moose::FaceArg & face)
{
  if (!face.fi)
    mooseError("QPXIonWallFluxMaterial received a FaceArg without FaceInfo.");

  RealVectorValue n = face.fi->normal();

  if (face.face_side)
  {
    if (face.face_side == &face.fi->elem())
      return n;

    if (face.fi->neighborPtr() && face.face_side == face.fi->neighborPtr())
      return -n;

    mooseError(
        "QPXIonWallFluxMaterial received a FaceArg whose face_side does not "
        "match either FaceInfo side.");
  }

  // A face without explicit sidedness is unambiguous only for an external
  // boundary. Internal plasma-material interfaces must supply face_side.
  if (face.fi->neighborPtr())
    mooseError(
        "QPXIonWallFluxMaterial requires a sided FaceArg on internal boundaries.");

  return n;
}
}

InputParameters
QPXIonWallFluxMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Provides face-local ion surface, migration, and total wall-loss fluxes "
      "from species density and electrostatic potential.");

  params.addRequiredParam<MooseFunctorName>(
      "ion_number_density", "Ion number density n_i [1/m^3].");

  params.addRequiredParam<MooseFunctorName>(
      "potential", "Electrostatic potential phi [V].");

  params.addRequiredParam<MooseFunctorName>(
      "mobility", "Positive ion mobility magnitude [m^2/(V s)].");

  params.addRequiredParam<MooseFunctorName>(
      "gas_temperature", "Heavy-particle temperature T_g [K].");

  params.addRequiredParam<Real>(
      "charge_number", "Signed charge number z_i.");

  params.addRequiredParam<Real>(
      "molar_mass", "Species molar mass M_i [kg/mol].");

  params.addParam<Real>(
      "sticking", 1.0, "Surface sticking/neutralization probability.");

  params.addParam<Real>(
      "migration_gate_smoothing_width",
      0.0,
      "Diagnostic smoothing width [V/m] for the outward migration gate. "
      "Zero preserves the existing hard active-set behavior.");

  return params;
}

QPXIonWallFluxMaterial::QPXIonWallFluxMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _ion_number_density(getFunctor<ADReal>("ion_number_density")),
    _potential(getFunctor<ADReal>("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
    _gas_temperature(getFunctor<ADReal>("gas_temperature")),
    _charge_number(getParam<Real>("charge_number")),
    _molar_mass(getParam<Real>("molar_mass")),
    _sticking(getParam<Real>("sticking")),
    _migration_gate_smoothing_width(
        getParam<Real>("migration_gate_smoothing_width"))
{
  if (_charge_number == 0.0)
    paramError("charge_number", "Ion wall migration requires nonzero charge_number.");

  if (_molar_mass <= 0.0)
    paramError("molar_mass", "molar_mass must be positive.");

  if (_sticking < 0.0 || _sticking > 1.0)
    paramError("sticking", "sticking must lie in [0,1].");

  if (_migration_gate_smoothing_width < 0.0)
    paramError(
        "migration_gate_smoothing_width",
        "migration_gate_smoothing_width must be nonnegative.");

  addFunctorProperty<ADReal>(
      "ion_surface_number_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);

        if constexpr (!isFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          using std::sqrt;

          const ADReal n_i = _ion_number_density(r, state);
          const ADReal T_g = _gas_temperature(r, state);

          if (MetaPhysicL::raw_value(T_g) <= 0.0)
            mooseError("QPXIonWallFluxMaterial requires gas_temperature > 0 K.");

          const ADReal v_th =
              sqrt(8.0 * QPX_CONSTANTS::R * T_g /
                   (QPX_CONSTANTS::pi * _molar_mass));

          return _sticking * 0.25 * n_i * v_th;
        }
      });

  addFunctorProperty<ADReal>(
      "ion_migration_number_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);

        if constexpr (!isFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          const RealVectorValue n_out = outwardNormal(r);
          const ADRealVectorValue electric_field =
              -_potential.gradient(r, state);
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
      "ion_wall_number_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);

        if constexpr (!isFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          using std::sqrt;

          const ADReal n_i = _ion_number_density(r, state);
          const ADReal T_g = _gas_temperature(r, state);

          if (MetaPhysicL::raw_value(T_g) <= 0.0)
            mooseError("QPXIonWallFluxMaterial requires gas_temperature > 0 K.");

          const ADReal v_th =
              sqrt(8.0 * QPX_CONSTANTS::R * T_g /
                   (QPX_CONSTANTS::pi * _molar_mass));

          const ADReal surface =
              _sticking * 0.25 * n_i * v_th;

          const RealVectorValue n_out = outwardNormal(r);
          const ADRealVectorValue electric_field =
              -_potential.gradient(r, state);
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
      "ion_surface_mass_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);

        if constexpr (!isFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          using std::sqrt;

          const ADReal n_i = _ion_number_density(r, state);
          const ADReal T_g = _gas_temperature(r, state);
          const ADReal v_th =
              sqrt(8.0 * QPX_CONSTANTS::R * T_g /
                   (QPX_CONSTANTS::pi * _molar_mass));

          return _sticking * 0.25 * n_i * v_th *
                 _molar_mass / QPX_CONSTANTS::N_A;
        }
      });

  addFunctorProperty<ADReal>(
      "ion_migration_mass_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);

        if constexpr (!isFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          const RealVectorValue n_out = outwardNormal(r);
          const ADRealVectorValue electric_field =
              -_potential.gradient(r, state);
          const ADReal directed_field =
              _charge_number * (electric_field * n_out);
          const ADReal outward_drift_field =
              outwardPositivePart(
                  directed_field, _migration_gate_smoothing_width);

          return _ion_number_density(r, state) *
                 _mobility(r, state) *
                 outward_drift_field *
                 _molar_mass / QPX_CONSTANTS::N_A;
        }
      });

  addFunctorProperty<ADReal>(
      "ion_wall_mass_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);

        if constexpr (!isFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
        {
          using std::sqrt;

          const ADReal n_i = _ion_number_density(r, state);
          const ADReal T_g = _gas_temperature(r, state);
          const ADReal v_th =
              sqrt(8.0 * QPX_CONSTANTS::R * T_g /
                   (QPX_CONSTANTS::pi * _molar_mass));

          const ADReal surface =
              _sticking * 0.25 * n_i * v_th;

          const RealVectorValue n_out = outwardNormal(r);
          const ADRealVectorValue electric_field =
              -_potential.gradient(r, state);
          const ADReal directed_field =
              _charge_number * (electric_field * n_out);
          const ADReal outward_drift_field =
              outwardPositivePart(
                  directed_field, _migration_gate_smoothing_width);

          const ADReal migration =
              n_i * _mobility(r, state) * outward_drift_field;

          return (surface + migration) *
                 _molar_mass / QPX_CONSTANTS::N_A;
        }
      });
}
