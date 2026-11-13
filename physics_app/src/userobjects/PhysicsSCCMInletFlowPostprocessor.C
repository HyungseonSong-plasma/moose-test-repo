#include "PhysicsSCCMInletFlowPostprocessor.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsSCCMInletFlowPostprocessor);

InputParameters
PhysicsSCCMInletFlowPostprocessor::validParams()
{
  InputParameters params = GeneralPostprocessor::validParams();
  params.addClassDescription(
      "Convert a species-owned SCCM inlet mass-flow rate into a mesh-area-normalized "
      "inlet mass-flux magnitude [kg/(m^2 s)] or inlet speed magnitude [m/s].");
  params.addRequiredParam<Real>("mdot_kg_per_s", "Positive inward mass-flow magnitude [kg/s].");
  params.addRequiredParam<Real>("rho_inlet_kg_per_m3",
                                "Ideal-gas density at the prescribed inlet composition [kg/m^3].");
  params.addRequiredParam<PostprocessorName>(
      "area_pp", "AreaPostprocessor on the exact inlet sideset [m^2].");
  params.addParam<MooseEnum>(
      "quantity", MooseEnum("mass_flux velocity", "mass_flux"),
      "Report mass-flux magnitude or inlet normal speed magnitude.");
  return params;
}

PhysicsSCCMInletFlowPostprocessor::PhysicsSCCMInletFlowPostprocessor(
    const InputParameters & parameters)
  : GeneralPostprocessor(parameters),
    _mdot(getParam<Real>("mdot_kg_per_s")),
    _inlet_density(getParam<Real>("rho_inlet_kg_per_m3")),
    _quantity(getParam<MooseEnum>("quantity")),
    _inlet_area(getPostprocessorValue("area_pp"))
{
  if (!std::isfinite(_mdot) || _mdot <= 0.0)
    paramError("mdot_kg_per_s", "The SCCM-converted mass-flow magnitude must be positive and finite.");
  if (!std::isfinite(_inlet_density) || _inlet_density <= 0.0)
    paramError("rho_inlet_kg_per_m3", "The inlet gas density must be positive and finite.");
}

PostprocessorValue
PhysicsSCCMInletFlowPostprocessor::getValue() const
{
  if (!std::isfinite(_inlet_area) || _inlet_area <= 0.0)
    mooseError("The SCCM inlet area must be positive and finite; got ", _inlet_area);
  const Real flux = _mdot / _inlet_area;
  if (_quantity == "mass_flux")
    return flux;
  if (_quantity == "velocity")
    return flux / _inlet_density;
  mooseError("Unsupported SCCM derived quantity: ", _quantity);
}
