#include "ADIntegratedBC.h"
#include "FaceInfo.h"
#include "FVUtils.h"
#include "MooseFunctorArguments.h"
#include "MooseMesh.h"
#include "Physics.h"

/**
 * Shared plasma-side FaceArg evaluation for the Issue 395 electron particle and
 * electron-energy wall BCs. The same sided functor is used in the surface
 * current/charge ledger. Never evaluate this sheath-limited functor through
 * ElemQpArg: that intentionally selects its thermal-only fallback.
 */
namespace
{
ADReal
plasmaSideElectronWallNumberFlux(MooseMesh & mesh,
                                 const Elem * const elem,
                                 const unsigned int side,
                                 const Moose::Functor<ADReal> & flux)
{
  const FaceInfo * const fi = mesh.faceInfo(elem, side);
  if (!fi)
    mooseError("Field-limited FEM electron BC could not obtain FaceInfo.");

  const bool on_elem = flux.hasFaceSide(*fi, true);
  const bool on_neighbor = flux.hasFaceSide(*fi, false);
  if (on_elem == on_neighbor)
    mooseError("Field-limited FEM electron BC needs one plasma-side flux owner.");

  const Elem * const plasma_side = on_elem ? fi->elemPtr() : fi->neighborPtr();
  if (plasma_side != elem)
    return ADReal(0.0);

  const Moose::FaceArg face_arg = {
      fi,
      Moose::FV::LimiterType::CentralDifference,
      /* elem_is_upwind = */ true,
      /* correct_skewness = */ false,
      plasma_side,
      /* state_limiter = */ nullptr};
  return flux(face_arg, Moose::currentState());
}
} // namespace

class FEMElectronSheathBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  FEMElectronSheathBC(const InputParameters & parameters);
  bool checkVariableBoundaryIntegrity() const override { return false; }

protected:
  ADReal computeQpResidual() override;
  const Moose::Functor<ADReal> & _wall_number_flux;
};

registerMooseObject("PhysicsApp", FEMElectronSheathBC);

InputParameters
FEMElectronSheathBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addClassDescription(
      "FEM log-molar electron particle loss sharing the exact one-sided "
      "adjacent-cell-sheath number-flux functor with the dielectric charge ledger.");
  params.addRequiredParam<MooseFunctorName>(
      "wall_number_flux", "Electron number flux [1/(m^2 s)], positive out of plasma.");
  return params;
}

FEMElectronSheathBC::
FEMElectronSheathBC(const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _wall_number_flux(getFunctor<ADReal>("wall_number_flux"))
{
}

ADReal
FEMElectronSheathBC::computeQpResidual()
{
  const auto block = _current_elem->subdomain_id();
  if (!_var.activeOnSubdomain(block) || !_wall_number_flux.hasBlocks(block))
    return ADReal(0.0);

  const ADReal number_flux =
      plasmaSideElectronWallNumberFlux(_mesh, _current_elem, _current_side, _wall_number_flux);
  return _test[_i][_qp] * number_flux / PHYSICS_CONSTANTS::N_A;
}

