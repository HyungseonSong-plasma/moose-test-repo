#include "ADIntegratedBC.h"
#include "FaceInfo.h"
#include "MooseFunctorArguments.h"
#include "MooseMesh.h"
#include "Physics.h"
#include "PhysicsGroundedElectronSheathFlux.h"

class PhysicsFEMLogMolarElectronFieldLimitedFluxBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarElectronFieldLimitedFluxBC(const InputParameters & parameters);
  bool checkVariableBoundaryIntegrity() const override { return false; }

protected:
  ADReal computeQpResidual() override;
  const Moose::Functor<ADReal> & _wall_number_flux;
};

class PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC(const InputParameters & parameters);
  bool checkVariableBoundaryIntegrity() const override { return false; }

protected:
  ADReal computeQpResidual() override;
  const Moose::Functor<ADReal> & _wall_number_flux;
  const Moose::Functor<ADReal> & _mean_energy;
};

registerMooseObject("PhysicsApp", PhysicsFEMLogMolarElectronFieldLimitedFluxBC);
registerMooseObject("PhysicsApp", PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC);

namespace
{
Moose::FaceArg
makeWallFaceArg(MooseMesh & mesh,
                const Elem * current_elem,
                const unsigned int current_side,
                const Moose::Functor<ADReal> & flux)
{
  const FaceInfo * const fi = mesh.faceInfo(current_elem, current_side);
  if (!fi)
    mooseError("Field-limited electron wall BC could not obtain FaceInfo for the current side.");

  const bool on_elem = flux.hasFaceSide(*fi, true);
  const bool on_neighbor = flux.hasFaceSide(*fi, false);

  const Elem * face_side = nullptr;
  if (on_elem && on_neighbor)
    face_side = nullptr;
  else if (on_elem)
    face_side = fi->elemPtr();
  else if (on_neighbor)
    face_side = fi->neighborPtr();
  else
    mooseError("The electron wall-flux functor '", flux.functorName(),
               "' is not defined on either side of the current face.");

  return {fi,
          Moose::FV::LimiterType::CentralDifference,
          /* elem_is_upwind = */ true,
          /* correct_skewness = */ false,
          face_side,
          /* state_limiter = */ nullptr};
}
}

InputParameters
PhysicsFEMLogMolarElectronFieldLimitedFluxBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addClassDescription(
      "Applies a physical electron wall-number-flux functor to a FEM log-molar electron "
      "continuity equation. Positive supplied flux is outward from the plasma.");
  params.addRequiredParam<MooseFunctorName>(
      "wall_number_flux", "Physical electron wall number flux [1/(m^2 s)], positive outward.");
  return params;
}

PhysicsFEMLogMolarElectronFieldLimitedFluxBC::
PhysicsFEMLogMolarElectronFieldLimitedFluxBC(const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _wall_number_flux(getFunctor<ADReal>("wall_number_flux"))
{
}

ADReal
PhysicsFEMLogMolarElectronFieldLimitedFluxBC::computeQpResidual()
{
  const auto block = _current_elem->subdomain_id();
  if (!_var.activeOnSubdomain(block) || !_wall_number_flux.hasBlocks(block))
    return ADReal(0.0);

  const auto face_arg = makeWallFaceArg(_mesh, _current_elem, _current_side, _wall_number_flux);
  const ADReal gamma_number = _wall_number_flux(face_arg, Moose::currentState());
  return _test[_i][_qp] * gamma_number / PHYSICS_CONSTANTS::N_A;
}

InputParameters
PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addClassDescription(
      "Electron-energy wall loss driven by the same field-limited particle wall flux. "
      "Gamma_eps=(Gamma_e/N_A)*(5/2 T_e), with no sheath-potential energy term.");
  params.addRequiredParam<MooseFunctorName>(
      "wall_number_flux", "Physical electron wall number flux [1/(m^2 s)], positive outward.");
  params.addRequiredParam<MooseFunctorName>("mean_energy", "Mean electron energy [eV].");
  return params;
}

PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC::
PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC(const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _wall_number_flux(getFunctor<ADReal>("wall_number_flux")),
    _mean_energy(getFunctor<ADReal>("mean_energy"))
{
}

ADReal
PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC::computeQpResidual()
{
  const auto block = _current_elem->subdomain_id();
  if (!_var.activeOnSubdomain(block) || !_wall_number_flux.hasBlocks(block) ||
      !_mean_energy.hasBlocks(block))
    return ADReal(0.0);

  const auto face_arg = makeWallFaceArg(_mesh, _current_elem, _current_side, _wall_number_flux);
  const ADReal gamma_number = _wall_number_flux(face_arg, Moose::currentState());
  const ADReal mean_energy = _mean_energy(face_arg, Moose::currentState());
  const ADReal Te = PhysicsGroundedElectronSheath::electronTemperatureEV(mean_energy);
  const ADReal gamma_energy_molar = gamma_number / PHYSICS_CONSTANTS::N_A * (2.5 * Te);

  return _test[_i][_qp] * gamma_energy_molar;
}
