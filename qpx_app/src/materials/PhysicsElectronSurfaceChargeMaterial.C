#include "PhysicsElectronSurfaceChargeMaterial.h"

#include "Physics.h"
#include "FaceInfo.h"
#include "MooseMesh.h"

registerMooseObject("PhysicsApp", PhysicsElectronSurfaceChargeMaterial);

InputParameters
PhysicsElectronSurfaceChargeMaterial::validParams()
{
  auto params = ADMaterial::validParams();

  params.addClassDescription(
      "Accumulates local electron-deposited surface charge by directly "
      "consuming the same wall-number-flux functor used by the FV electron "
      "boundary condition.");

  params.addRequiredParam<MooseFunctorName>(
      "wall_number_flux",
      "Electron wall number-flux functor [1/(m^2 s)]. Positive means "
      "electrons leave the plasma.");

  params.addParam<Real>(
      "initial_surface_charge",
      0.0,
      "Initial local surface charge density [C/m^2].");

  return params;
}

PhysicsElectronSurfaceChargeMaterial::PhysicsElectronSurfaceChargeMaterial(
    const InputParameters & parameters)
  : ADMaterial(parameters),
    _wall_number_flux(getFunctor<ADReal>("wall_number_flux")),
    _initial_surface_charge(getParam<Real>("initial_surface_charge")),
    _surface_electron_number_flux(
        declareADProperty<Real>("surface_electron_number_flux")),
    _surface_current_density(
        declareADProperty<Real>("surface_current_density")),
    _surface_charge(
        declareADProperty<Real>("surface_charge")),
    _surface_charge_old(
        getMaterialPropertyOld<Real>("surface_charge"))
{
}

void
PhysicsElectronSurfaceChargeMaterial::initQpStatefulProperties()
{
  _surface_charge[_qp] = _initial_surface_charge;
}

void
PhysicsElectronSurfaceChargeMaterial::computeQpProperties()
{
  const FaceInfo * const fi = _mesh.faceInfo(_current_elem, _current_side);

  if (!fi)
    mooseError(
        "PhysicsElectronSurfaceChargeMaterial could not obtain FaceInfo for the "
        "current boundary side.");

  // Match the FV boundary-condition face evaluation:
  //
  //   limiter          = CentralDifference
  //   elem_is_upwind   = true
  //   correct_skewness = false
  //
  // Select the side on which the supplied functor is defined.
  const bool on_elem = _wall_number_flux.hasFaceSide(*fi, true);
  const bool on_neighbor = _wall_number_flux.hasFaceSide(*fi, false);

  const Elem * face_side = nullptr;

  if (on_elem && on_neighbor)
    face_side = nullptr;
  else if (on_elem)
    face_side = fi->elemPtr();
  else if (on_neighbor)
    face_side = fi->neighborPtr();
  else
    mooseError(
        "The wall-number-flux functor '",
        _wall_number_flux.functorName(),
        "' is not defined on either side of the current face.");

  const Moose::FaceArg face_arg = {
      fi,
      Moose::FV::LimiterType::CentralDifference,
      /* elem_is_upwind = */ true,
      /* correct_skewness = */ false,
      face_side,
      /* state_limiter = */ nullptr};

  // This is now the supplied FV wall-flux functor itself.
  // No second n_e evaluation and no duplicated wall-flux formula.
  const ADReal flux = _wall_number_flux(face_arg, determineState());

  _surface_electron_number_flux[_qp] = flux;

  // Positive electron number flux leaves plasma and deposits negative charge.
  _surface_current_density[_qp] = -PHYSICS_CONSTANTS::e * flux;

  // Local implicit-Euler accumulation.
  _surface_charge[_qp] =
      _surface_charge_old[_qp] + _surface_current_density[_qp] * _dt;
}
