#include "PhysicsElectronAdjacentSheathWallFluxMaterial.h"

#include "FaceInfo.h"
#include "MooseFunctorArguments.h"
#include "PhysicsElectronWallPhysics.h"
#include "PhysicsGroundedElectronSheathFlux.h"

#include <cmath>
#include <type_traits>

registerMooseObject("PhysicsApp", PhysicsElectronAdjacentSheathWallFluxMaterial);

namespace
{
template <typename SpaceArg>
constexpr bool
isAdjacentSheathFaceArg()
{
  return std::is_same_v<std::decay_t<SpaceArg>, Moose::FaceArg>;
}

RealVectorValue
adjacentSheathOutwardNormal(const Moose::FaceArg & face)
{
  if (!face.fi)
    mooseError("PhysicsElectronAdjacentSheathWallFluxMaterial received a FaceArg without FaceInfo.");

  RealVectorValue n = face.fi->normal();
  if (face.face_side)
  {
    if (face.face_side == &face.fi->elem())
      return n;
    if (face.fi->neighborPtr() && face.face_side == face.fi->neighborPtr())
      return -n;
    mooseError("PhysicsElectronAdjacentSheathWallFluxMaterial received an invalid face_side.");
  }

  if (face.fi->neighborPtr())
    mooseError("PhysicsElectronAdjacentSheathWallFluxMaterial requires a sided FaceArg on internal boundaries.");

  return n;
}

ADRealVectorValue
adjacentSheathElectricField(const Moose::Functor<ADReal> & potential,
                            const Moose::FaceArg & face,
                            const Moose::StateArg & state,
                            const bool use_element_gradient)
{
  if (!use_element_gradient)
    return -potential.gradient(face, state);

  if (!face.fi)
    mooseError("PhysicsElectronAdjacentSheathWallFluxMaterial received a FaceArg without FaceInfo.");

  if (face.face_side)
  {
    if (face.face_side == &face.fi->elem())
      return -potential.gradient(face.makeElem(), state);
    if (face.fi->neighborPtr() && face.face_side == face.fi->neighborPtr())
      return -potential.gradient(face.makeNeighbor(), state);
    mooseError("PhysicsElectronAdjacentSheathWallFluxMaterial received an invalid face_side.");
  }

  if (!face.fi->neighborPtr())
    return -potential.gradient(face.makeElem(), state);

  return -0.5 * (potential.gradient(face.makeElem(), state) +
                 potential.gradient(face.makeNeighbor(), state));
}

Real
adjacentSheathNormalDistance(const Moose::FaceArg & face, const RealVectorValue & n_out)
{
  if (!face.fi)
    mooseError("PhysicsElectronAdjacentSheathWallFluxMaterial received a FaceArg without FaceInfo.");

  Point center;
  if (face.face_side)
  {
    if (face.face_side == &face.fi->elem())
      center = face.fi->elemCentroid();
    else if (face.fi->neighborPtr() && face.face_side == face.fi->neighborPtr())
      center = face.fi->neighborCentroid();
    else
      mooseError("PhysicsElectronAdjacentSheathWallFluxMaterial received an invalid face_side.");
  }
  else
  {
    if (face.fi->neighborPtr())
      mooseError("PhysicsElectronAdjacentSheathWallFluxMaterial requires a sided FaceArg on internal boundaries.");
    center = face.fi->elemCentroid();
  }

  const Real d_perp = std::abs((center - face.fi->faceCentroid()) * n_out);
  if (d_perp <= 0.0)
    mooseError("PhysicsElectronAdjacentSheathWallFluxMaterial requires a positive wall-to-cell normal distance.");
  return d_perp;
}

ADReal
adjacentSheathDrop(const Moose::Functor<ADReal> & potential,
                   const Moose::FaceArg & face,
                   const Moose::StateArg & state,
                   const bool use_element_gradient)
{
  const RealVectorValue n_out = adjacentSheathOutwardNormal(face);
  const ADRealVectorValue electric_field =
      adjacentSheathElectricField(potential, face, state, use_element_gradient);
  const ADReal E_n = electric_field * n_out;
  const Real d_perp = adjacentSheathNormalDistance(face, n_out);
  return PhysicsGroundedElectronSheath::smoothPositiveDropV(E_n * d_perp);
}
} // namespace

InputParameters
PhysicsElectronAdjacentSheathWallFluxMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription(
      "Electron thermal wall collection suppressed by an adjacent-cell sheath drop: "
      "Delta_phi=max(E_n*d_perp,0), Gamma_e=s*n_e*vbar/4*exp(-Delta_phi/T_e).");
  params.addRequiredParam<MooseFunctorName>("electron_density", "Electron number density n_e [1/m^3].");
  params.addRequiredParam<MooseFunctorName>("mean_energy", "Mean electron energy [eV].");
  params.addRequiredParam<MooseFunctorName>("potential", "Electrostatic potential phi [V].");
  params.addParam<Real>("sticking", 1.0, "Electron wall absorption probability.");
  params.addParam<bool>(
      "use_element_gradient_for_potential",
      false,
      "Evaluate E=-grad(phi) from the sided adjacent element. Enable for continuous FEM potential.");
  return params;
}

PhysicsElectronAdjacentSheathWallFluxMaterial::PhysicsElectronAdjacentSheathWallFluxMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _mean_energy(getFunctor<ADReal>("mean_energy")),
    _potential(getFunctor<ADReal>("potential")),
    _sticking(getParam<Real>("sticking")),
    _use_element_gradient_for_potential(getParam<bool>("use_element_gradient_for_potential"))
{
  if (_sticking < 0.0 || _sticking > 1.0)
    paramError("sticking", "Electron sticking must be in [0,1].");

  addFunctorProperty<ADReal>(
      "electron_mean_speed",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal eps_bar = _mean_energy(r, state);
        if (MetaPhysicL::raw_value(eps_bar) <= 0.0)
          mooseError("PhysicsElectronAdjacentSheathWallFluxMaterial requires mean_energy > 0 eV.");
        return PhysicsElectronWallPhysics::meanSpeed(eps_bar);
      });

  addFunctorProperty<ADReal>(
      "electron_sheath_drop_V",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using SpaceArg = decltype(r);
        if constexpr (!isAdjacentSheathFaceArg<SpaceArg>())
          return ADReal(0.0);
        else
          return adjacentSheathDrop(_potential, r, state, _use_element_gradient_for_potential);
      });

  addFunctorProperty<ADReal>(
      "electron_wall_number_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal n_e = _electron_density(r, state);
        const ADReal eps_bar = _mean_energy(r, state);
        if (MetaPhysicL::raw_value(eps_bar) <= 0.0)
          mooseError("PhysicsElectronAdjacentSheathWallFluxMaterial requires mean_energy > 0 eV.");

        using SpaceArg = decltype(r);
        if constexpr (!isAdjacentSheathFaceArg<SpaceArg>())
          return PhysicsElectronWallPhysics::absorbingNumberFlux(n_e, eps_bar, _sticking);
        else
        {
          const ADReal drop =
              adjacentSheathDrop(_potential, r, state, _use_element_gradient_for_potential);
          return _sticking *
                 PhysicsGroundedElectronSheath::primaryParticleFluxHat(n_e, eps_bar, drop);
        }
      });
}
