#include "ADIntegratedBC.h"
#include "FaceInfo.h"
#include "FVUtils.h"
#include "MooseFunctorArguments.h"
#include "MooseMesh.h"
#include "Physics.h"

/** Consumes the same electron-number flux; energy carried away is 5/2 T_e. */
class FEMElectronEnergySheathBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  FEMElectronEnergySheathBC(const InputParameters & parameters);
  bool checkVariableBoundaryIntegrity() const override { return false; }

protected:
  ADReal computeQpResidual() override;
  const Moose::Functor<ADReal> & _wall_number_flux;
  const Moose::Functor<ADReal> & _mean_energy;
};

registerMooseObject("PhysicsApp", FEMElectronEnergySheathBC);

InputParameters
FEMElectronEnergySheathBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addClassDescription(
      "FEM log-molar electron-energy wall loss using the same adjacent-cell "
      "sheath-limited number flux as electron continuity and charge ledger: "
      "Gamma_energy=(Gamma_number/N_A)*(5/2 T_e), T_e=2/3 mean_energy [eV].");
  params.addRequiredParam<MooseFunctorName>(
      "wall_number_flux", "Electron number flux [1/(m^2 s)], positive out of plasma.");
  params.addRequiredParam<MooseFunctorName>(
      "mean_energy", "Mean electron energy [eV] in the plasma block.");
  return params;
}

FEMElectronEnergySheathBC::
FEMElectronEnergySheathBC(const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _wall_number_flux(getFunctor<ADReal>("wall_number_flux")),
    _mean_energy(getFunctor<ADReal>("mean_energy"))
{
}

ADReal
FEMElectronEnergySheathBC::computeQpResidual()
{
  const auto block = _current_elem->subdomain_id();
  if (!_var.activeOnSubdomain(block) || !_wall_number_flux.hasBlocks(block) ||
      !_mean_energy.hasBlocks(block))
    return ADReal(0.0);

  const FaceInfo * const fi = _mesh.faceInfo(_current_elem, _current_side);
  if (!fi)
    mooseError("Field-limited FEM electron energy BC could not obtain FaceInfo.");
  const bool on_elem = _wall_number_flux.hasFaceSide(*fi, true);
  const bool on_neighbor = _wall_number_flux.hasFaceSide(*fi, false);
  if (on_elem == on_neighbor)
    mooseError("Field-limited FEM electron energy BC needs one plasma-side flux owner.");
  const Elem * const plasma_side = on_elem ? fi->elemPtr() : fi->neighborPtr();
  if (plasma_side != _current_elem)
    return ADReal(0.0);

  const Moose::FaceArg face_arg = {
      fi,
      Moose::FV::LimiterType::CentralDifference,
      /* elem_is_upwind = */ true,
      /* correct_skewness = */ false,
      plasma_side,
      /* state_limiter = */ nullptr};
  const ADReal particle_flux = _wall_number_flux(face_arg, Moose::currentState());
  const ADReal mean_energy = _mean_energy(face_arg, Moose::currentState());
  if (MetaPhysicL::raw_value(mean_energy) <= 0.0)
    mooseError("Field-limited FEM electron energy BC requires mean_energy > 0 eV.");
  const ADReal Te = (2.0 / 3.0) * mean_energy;
  return _test[_i][_qp] * (particle_flux / PHYSICS_CONSTANTS::N_A) * (2.5 * Te);
}
