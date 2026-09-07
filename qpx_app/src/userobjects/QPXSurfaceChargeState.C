#include "QPXSurfaceChargeState.h"

#include "QPX.h"
#include "FaceInfo.h"

registerMooseObject("qpxApp", QPXSurfaceChargeState);

InputParameters
QPXSurfaceChargeState::validParams()
{
  auto params = SideUserObject::validParams();
  params += ADFunctorInterface::validParams();

  params.addClassDescription(
      "Stores converged FV face-local surface charge in restartable data and "
      "updates it from an electron wall-number-flux functor.");

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

QPXSurfaceChargeState::QPXSurfaceChargeState(
    const InputParameters & parameters)
  : SideUserObject(parameters),
    ADFunctorInterface(this),
    _wall_number_flux(getFunctor<ADReal>("wall_number_flux")),
    _initial_surface_charge(getParam<Real>("initial_surface_charge")),
    _surface_charge(
        declareRestartableData<std::map<dof_id_type, Real>>("surface_charge")),
    _total_charge(0.0),
    _surface_area(0.0)
{
}

void
QPXSurfaceChargeState::initialize()
{
  _pending_surface_charge.clear();
  _pending_face_measure.clear();
}

ADReal
QPXSurfaceChargeState::evaluateFaceFunctor(
    const Moose::Functor<ADReal> & functor,
    const FaceInfo & fi) const
{
  const bool on_elem = functor.hasFaceSide(fi, true);
  const bool on_neighbor = functor.hasFaceSide(fi, false);

  const Elem * face_side = nullptr;

  if (on_elem && on_neighbor)
    face_side = nullptr;
  else if (on_elem)
    face_side = fi.elemPtr();
  else if (on_neighbor)
    face_side = fi.neighborPtr();
  else
    mooseError(
        "Functor '",
        functor.functorName(),
        "' is not defined on either side of FV face ",
        fi.id(),
        ".");

  const Moose::FaceArg face_arg = {
      &fi,
      Moose::FV::LimiterType::CentralDifference,
      /* elem_is_upwind = */ true,
      /* correct_skewness = */ false,
      face_side,
      /* state_limiter = */ nullptr};

  return functor(face_arg, determineState());
}

Real
QPXSurfaceChargeState::surfaceCharge(const dof_id_type face_id) const
{
  const auto it = _surface_charge.find(face_id);
  return it == _surface_charge.end() ? _initial_surface_charge : it->second;
}

void
QPXSurfaceChargeState::execute()
{
  // SideUserObject supplies the active FaceInfo(s) corresponding to the
  // currently visited sideset side. This also handles the case in which
  // FaceInfo ownership/orientation is on the neighbor side.
  getFaceInfos();

  for (const FaceInfo * const fi : _face_infos)
  {
    const ADReal gamma_ad = evaluateFaceFunctor(_wall_number_flux, *fi);
    const Real gamma = MetaPhysicL::raw_value(gamma_ad);

    // Commit exactly the same implicit-Euler law used by the FV Poisson
    // interface during the nonlinear solve.
    const Real sigma_new =
        surfaceCharge(fi->id())
        - QPX_CONSTANTS::e * gamma * _dt;

    _pending_surface_charge[fi->id()] = sigma_new;
    _pending_face_measure[fi->id()] =
        fi->faceArea() * fi->faceCoord();
  }
}

void
QPXSurfaceChargeState::threadJoin(const UserObject & y)
{
  const auto & other = static_cast<const QPXSurfaceChargeState &>(y);

  for (const auto & [id, value] : other._pending_surface_charge)
    _pending_surface_charge[id] = value;

  for (const auto & [id, value] : other._pending_face_measure)
    _pending_face_measure[id] = value;
}

void
QPXSurfaceChargeState::finalize()
{
  // Commit the just-converged timestep to restartable storage.
  for (const auto & [id, sigma] : _pending_surface_charge)
    _surface_charge[id] = sigma;

  Real local_charge = 0.0;
  Real local_area = 0.0;

  // Every active face on the restricted boundary is staged each execution.
  // Use those measures for diagnostics so we do not need a second geometry
  // store in restartable data.
  for (const auto & [id, measure] : _pending_face_measure)
  {
    const auto it = _surface_charge.find(id);
    if (it == _surface_charge.end())
      mooseError(
          "Surface-charge state was not committed for FV face ",
          id,
          ".");

    local_charge += it->second * measure;
    local_area += measure;
  }

  _total_charge = local_charge;
  _surface_area = local_area;

  _communicator.sum(_total_charge);
  _communicator.sum(_surface_area);
}
