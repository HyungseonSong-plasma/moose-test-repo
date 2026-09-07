#include "QPXFVSurfaceChargeInterface.h"

#include "QPX.h"
#include "QPXSurfaceChargeState.h"
#include "FaceInfo.h"
#include "MooseVariableFV.h"

#include <cmath>

registerMooseObject("qpxApp", QPXFVSurfaceChargeInterface);

InputParameters
QPXFVSurfaceChargeInterface::validParams()
{
  auto params = FVInterfaceKernel::validParams();

  params.addClassDescription(
      "FV electrostatic interface flux with prescribed or restartable "
      "face-local surface charge.");

  params.addParam<MaterialPropertyName>(
      "surface_charge",
      "0",
      "Surface charge density sigma_s [C/m^2] used when "
      "use_surface_charge_state=false. May be a numeric constant or a "
      "material property.");

  params.addParam<bool>(
      "use_surface_charge_state",
      false,
      "Use QPXSurfaceChargeState plus the current wall-number-flux functor "
      "to construct the current implicit-Euler surface charge.");

  params.addParam<UserObjectName>(
      "surface_charge_state",
      "QPXSurfaceChargeState that owns converged face-local sigma_s.");

  params.addParam<MooseFunctorName>(
      "wall_number_flux",
      "Current electron wall number-flux functor [1/(m^2 s)]. Required when "
      "use_surface_charge_state=true.");

  params.addRequiredParam<MooseFunctorName>(
      "coeff1",
      "Relative permittivity functor on subdomain1.");

  params.addRequiredParam<MooseFunctorName>(
      "coeff2",
      "Relative permittivity functor on subdomain2.");

  return params;
}

QPXFVSurfaceChargeInterface::QPXFVSurfaceChargeInterface(
    const InputParameters & parameters)
  : FVInterfaceKernel(parameters),
    _coeff1(getFunctor<ADReal>("coeff1")),
    _coeff2(getFunctor<ADReal>("coeff2")),
    _surface_charge(getADMaterialProperty<Real>("surface_charge")),
    _use_surface_charge_state(getParam<bool>("use_surface_charge_state")),
    _surface_charge_state(nullptr),
    _wall_number_flux(nullptr)
{
  if (&var1() != &var2())
    paramError(
        "variable2",
        "QPXFVSurfaceChargeInterface requires the same FV potential variable "
        "on both sides. Omit variable2 or set it equal to variable1.");

  if (_use_surface_charge_state)
  {
    if (!isParamValid("surface_charge_state"))
      paramError(
          "surface_charge_state",
          "surface_charge_state is required when "
          "use_surface_charge_state=true.");

    if (!isParamValid("wall_number_flux"))
      paramError(
          "wall_number_flux",
          "wall_number_flux is required when "
          "use_surface_charge_state=true.");

    _surface_charge_state =
        &getUserObject<QPXSurfaceChargeState>("surface_charge_state");

    _wall_number_flux =
        &getFunctor<ADReal>("wall_number_flux");
  }
}

ADReal
QPXFVSurfaceChargeInterface::evaluateFaceFunctor(
    const Moose::Functor<ADReal> & functor) const
{
  const bool on_elem = functor.hasFaceSide(*_face_info, true);
  const bool on_neighbor = functor.hasFaceSide(*_face_info, false);

  const Elem * face_side = nullptr;

  if (on_elem && on_neighbor)
    face_side = nullptr;
  else if (on_elem)
    face_side = _face_info->elemPtr();
  else if (on_neighbor)
    face_side = _face_info->neighborPtr();
  else
    mooseError(
        "Functor '",
        functor.functorName(),
        "' is not defined on either side of FV face ",
        _face_info->id(),
        ".");

  const Moose::FaceArg face_arg = {
      _face_info,
      Moose::FV::LimiterType::CentralDifference,
      /* elem_is_upwind = */ true,
      /* correct_skewness = */ false,
      face_side,
      /* state_limiter = */ nullptr};

  return functor(face_arg, determineState());
}

ADReal
QPXFVSurfaceChargeInterface::currentSurfaceCharge() const
{
  if (!_use_surface_charge_state)
    return _surface_charge[_qp];

  mooseAssert(
      _surface_charge_state && _wall_number_flux,
      "Dynamic surface-charge mode is missing required dependencies.");

  const Real sigma_old =
      _surface_charge_state->surfaceCharge(_face_info->id());

  const ADReal gamma_e_wall =
      evaluateFaceFunctor(*_wall_number_flux);

  return sigma_old
         - QPX_CONSTANTS::e * gamma_e_wall * _dt;
}

std::pair<ADReal, ADReal>
QPXFVSurfaceChargeInterface::oneSidedFluxes() const
{
  const auto state = determineState();

  const Elem * const elem1 =
      elemIsOne() ? _face_info->elemPtr() : _face_info->neighborPtr();
  const Elem * const elem2 =
      elemIsOne() ? _face_info->neighborPtr() : _face_info->elemPtr();

  const Point & center1 =
      elemIsOne() ? _face_info->elemCentroid() : _face_info->neighborCentroid();
  const Point & center2 =
      elemIsOne() ? _face_info->neighborCentroid() : _face_info->elemCentroid();

  Point n12 = _face_info->normal();
  if (!elemIsOne())
    n12 *= -1.0;

  const Point & face_center = _face_info->faceCentroid();

  const Real d1 = std::abs((face_center - center1) * n12);
  const Real d2 = std::abs((center2 - face_center) * n12);

  if (d1 <= 0.0 || d2 <= 0.0)
    mooseError(
        "QPXFVSurfaceChargeInterface encountered a non-positive cell-to-face "
        "normal distance.");

  const Moose::ElemArg arg1 = elemIsOne() ? elemArg() : neighborArg();
  const Moose::ElemArg arg2 = elemIsOne() ? neighborArg() : elemArg();

  const ADReal eps1 = _coeff1(arg1, state);
  const ADReal eps2 = _coeff2(arg2, state);

  if (MetaPhysicL::raw_value(eps1) <= 0.0 ||
      MetaPhysicL::raw_value(eps2) <= 0.0)
    mooseError(
        "QPXFVSurfaceChargeInterface requires positive relative permittivity.");

  const ADReal phi1 = var1().getElemValue(elem1, state);
  const ADReal phi2 = var2().getElemValue(elem2, state);

  const ADReal g1 = eps1 / d1;
  const ADReal g2 = eps2 / d2;

  const ADReal sigma_scaled =
      currentSurfaceCharge() / QPX_CONSTANTS::eps_0;

  const ADReal phi_face =
      (g1 * phi1 + g2 * phi2 + sigma_scaled) / (g1 + g2);

  const ADReal flux1 = g1 * (phi1 - phi_face);
  const ADReal flux2 = g2 * (phi2 - phi_face);

  return {flux1, flux2};
}

ADReal
QPXFVSurfaceChargeInterface::computeQpResidual()
{
  return oneSidedFluxes().first;
}

void
QPXFVSurfaceChargeInterface::computeResidual(const FaceInfo & fi)
{
  setupData(fi);

  const auto [flux1, flux2] = oneSidedFluxes();
  const Real scale = fi.faceArea() * fi.faceCoord();

  const Real r1 = MetaPhysicL::raw_value(flux1) * scale;
  const Real r2 = MetaPhysicL::raw_value(flux2) * scale;

  addResidual(r1, var1().number(), /* neighbor = */ !elemIsOne());
  addResidual(r2, var2().number(), /* neighbor = */ elemIsOne());
}

void
QPXFVSurfaceChargeInterface::computeJacobian(const FaceInfo & fi)
{
  setupData(fi);

  const auto [flux1, flux2] = oneSidedFluxes();
  const ADReal scale = fi.faceArea() * fi.faceCoord();

  const ADReal r1 = flux1 * scale;
  const ADReal r2 = flux2 * scale;

  const auto & dofs1 =
      elemIsOne() ? var1().dofIndices() : var1().dofIndicesNeighbor();

  const auto & dofs2 =
      elemIsOne() ? var2().dofIndicesNeighbor() : var2().dofIndices();

  mooseAssert(
      dofs1.size() == 1 && dofs2.size() == 1,
      "QPXFVSurfaceChargeInterface currently requires CONSTANT MONOMIAL FV "
      "variables.");

  addResidualsAndJacobian(
      _assembly,
      std::array<ADReal, 1>{{r1}},
      dofs1,
      var1().scalingFactor());

  addResidualsAndJacobian(
      _assembly,
      std::array<ADReal, 1>{{r2}},
      dofs2,
      var2().scalingFactor());
}
