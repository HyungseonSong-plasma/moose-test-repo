#include "PhysicsElectronDriftDiffusionLimitedWallFluxMaterial.h"

#include "FaceInfo.h"
#include "MooseFunctorArguments.h"
#include "PhysicsElectronWallPhysics.h"

#include <cmath>
#include <type_traits>

registerMooseObject("PhysicsApp", PhysicsElectronDriftDiffusionLimitedWallFluxMaterial);

namespace
{
template <typename SpaceArg>
constexpr bool
isDriftDiffusionFaceArg()
{
  return std::is_same_v<std::decay_t<SpaceArg>, Moose::FaceArg>;
}

ADReal
driftDiffusionPositivePart(const ADReal & value, const Real smoothing_width)
{
  if (smoothing_width <= 0.0)
    return MetaPhysicL::raw_value(value) > 0.0 ? value : ADReal(0.0) * value;

  using std::tanh;
  return 0.5 * value * (1.0 + tanh(value / smoothing_width));
}

RealVectorValue
driftDiffusionOutwardNormal(const Moose::FaceArg & face)
{
  if (!face.fi)
    mooseError("PhysicsElectronDriftDiffusionLimitedWallFluxMaterial received a FaceArg without FaceInfo.");

  RealVectorValue n = face.fi->normal();
  if (face.face_side)
  {
    if (face.face_side == &face.fi->elem())
      return n;
    if (face.fi->neighborPtr() && face.face_side == face.fi->neighborPtr())
      return -n;
    mooseError("PhysicsElectronDriftDiffusionLimitedWallFluxMaterial received an invalid face_side.");
  }

  if (face.fi->neighborPtr())
    mooseError("PhysicsElectronDriftDiffusionLimitedWallFluxMaterial requires a sided FaceArg on internal boundaries.");

  return n;
}

ADRealVectorValue
driftDiffusionSidedGradient(const Moose::Functor<ADReal> & functor,
                            const Moose::FaceArg & face,
                            const Moose::StateArg & state,
                            const bool use_element_gradient)
{
  if (!use_element_gradient)
    return functor.gradient(face, state);

  if (!face.fi)
    mooseError("PhysicsElectronDriftDiffusionLimitedWallFluxMaterial received a FaceArg without FaceInfo.");

  if (face.face_side)
  {
    if (face.face_side == &face.fi->elem())
      return functor.gradient(face.makeElem(), state);
    if (face.fi->neighborPtr() && face.face_side == face.fi->neighborPtr())
      return functor.gradient(face.makeNeighbor(), state);
    mooseError("PhysicsElectronDriftDiffusionLimitedWallFluxMaterial received an invalid face_side.");
  }

  if (!face.fi->neighborPtr())
    return functor.gradient(face.makeElem(), state);

  return 0.5 * (functor.gradient(face.makeElem(), state) +
                functor.gradient(face.makeNeighbor(), state));
}
}

InputParameters
PhysicsElectronDriftDiffusionLimitedWallFluxMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription(
      "Electron absorbing-wall number flux with signed normal drift-diffusion correction: "
      "Gamma_e=n_e*max(s*vbar_e/4-mu_e*E_n-D_e*grad(log_n_e).n_out,0).");
  params.addRequiredParam<MooseFunctorName>("electron_density", "Electron number density n_e [1/m^3].");
  params.addRequiredParam<MooseFunctorName>("mean_energy", "Mean electron energy [eV].");
  params.addRequiredParam<MooseFunctorName>("log_density", "Solved log electron molar density log(c_e).");
  params.addRequiredParam<MooseFunctorName>("potential", "Electrostatic potential phi [V].");
  params.addRequiredParam<MooseFunctorName>("mobility", "Positive electron mobility [m^2/(V s)].");
  params.addRequiredParam<MooseFunctorName>("diffusion", "Electron diffusion coefficient [m^2/s].");
  params.addParam<Real>("sticking", 1.0, "Electron wall absorption probability.");
  params.addParam<Real>(
      "wall_velocity_gate_smoothing_width",
      0.0,
      "Optional smoothing width [m/s] for max(v_out,0); zero uses a hard active set.");
  params.addParam<bool>(
      "use_element_gradient_for_potential",
      false,
      "Evaluate grad(phi) from the sided adjacent element. Enable for continuous FEM potential.");
  params.addParam<bool>(
      "use_element_gradient_for_log_density",
      false,
      "Evaluate grad(log_n_e) from the sided adjacent element. Enable for continuous FEM log density.");
  return params;
}

PhysicsElectronDriftDiffusionLimitedWallFluxMaterial::PhysicsElectronDriftDiffusionLimitedWallFluxMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _mean_energy(getFunctor<ADReal>("mean_energy")),
    _log_density(getFunctor<ADReal>("log_density")),
    _potential(getFunctor<ADReal>("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
    _diffusion(getFunctor<ADReal>("diffusion")),
    _sticking(getParam<Real>("sticking")),
    _wall_velocity_gate_smoothing_width(getParam<Real>("wall_velocity_gate_smoothing_width")),
    _use_element_gradient_for_potential(getParam<bool>("use_element_gradient_for_potential")),
    _use_element_gradient_for_log_density(getParam<bool>("use_element_gradient_for_log_density"))
{
  if (_sticking < 0.0 || _sticking > 1.0)
    paramError("sticking", "Electron sticking must be in [0,1].");
  if (_wall_velocity_gate_smoothing_width < 0.0)
    paramError("wall_velocity_gate_smoothing_width", "Smoothing width must be nonnegative.");

  addFunctorProperty<ADReal>(
      "electron_mean_speed",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal eps_bar = _mean_energy(r, state);
        if (MetaPhysicL::raw_value(eps_bar) <= 0.0)
          mooseError("PhysicsElectronDriftDiffusionLimitedWallFluxMaterial requires mean_energy > 0 eV.");
        return PhysicsElectronWallPhysics::meanSpeed(eps_bar);
      });

  addFunctorProperty<ADReal>(
      "electron_wall_number_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal n_e = _electron_density(r, state);
        const ADReal eps_bar = _mean_energy(r, state);
        if (MetaPhysicL::raw_value(eps_bar) <= 0.0)
          mooseError("PhysicsElectronDriftDiffusionLimitedWallFluxMaterial requires mean_energy > 0 eV.");

        const ADReal vbar = PhysicsElectronWallPhysics::meanSpeed(eps_bar);
        const ADReal thermal_speed = _sticking * 0.25 * vbar;

        using SpaceArg = decltype(r);
        if constexpr (!isDriftDiffusionFaceArg<SpaceArg>())
          return n_e * thermal_speed;
        else
        {
          const RealVectorValue n_out = driftDiffusionOutwardNormal(r);
          const ADRealVectorValue grad_phi =
              driftDiffusionSidedGradient(_potential, r, state, _use_element_gradient_for_potential);
          const ADRealVectorValue grad_log_n =
              driftDiffusionSidedGradient(_log_density, r, state, _use_element_gradient_for_log_density);

          const ADReal E_n = (-grad_phi) * n_out;
          const ADReal grad_log_n_normal = grad_log_n * n_out;
          const ADReal mu_e = _mobility(r, state);
          const ADReal D_e = _diffusion(r, state);

          // Bulk-consistent electron normal drift-diffusion velocity:
          // Gamma_e.dd / n_e = -mu_e E_n - D_e grad(log n_e).n_out.
          const ADReal outward_speed =
              thermal_speed - mu_e * E_n - D_e * grad_log_n_normal;
          return n_e *
                 driftDiffusionPositivePart(outward_speed, _wall_velocity_gate_smoothing_width);
        }
      });
}
