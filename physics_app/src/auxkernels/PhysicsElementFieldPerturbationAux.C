#include "PhysicsElementFieldPerturbationAux.h"

#include "libmesh/elem.h"

registerMooseObject("PhysicsApp", PhysicsElementFieldPerturbationAux);

InputParameters
PhysicsElementFieldPerturbationAux::validParams()
{
  InputParameters params = AuxKernel::validParams();
  params.addRequiredCoupledVar("base", "Unperturbed elemental field.");
  params.addRequiredParam<std::vector<unsigned int>>(
      "element_ids", "libMesh element IDs receiving the perturbation.");
  params.addParam<std::vector<Real>>(
      "element_scales",
      std::vector<Real>{},
      "Optional per-element multipliers. Empty means unit multiplier.");
  params.addRequiredParam<Real>("amplitude", "Common perturbation amplitude.");
  params.addClassDescription(
      "Applies a deterministic element-ID perturbation to an elemental auxiliary field. "
      "This object is intended for response/Jacobian diagnostics, not production physics.");
  return params;
}

PhysicsElementFieldPerturbationAux::PhysicsElementFieldPerturbationAux(
    const InputParameters & parameters)
  : AuxKernel(parameters),
    _base(coupledValue("base")),
    _amplitude(getParam<Real>("amplitude"))
{
  const auto & ids = getParam<std::vector<unsigned int>>("element_ids");
  const auto & scales = getParam<std::vector<Real>>("element_scales");
  if (!scales.empty() && scales.size() != ids.size())
    paramError("element_scales", "element_scales must be empty or match element_ids length.");

  for (std::size_t i = 0; i < ids.size(); ++i)
  {
    const dof_id_type id = static_cast<dof_id_type>(ids[i]);
    const Real scale = scales.empty() ? 1.0 : scales[i];
    if (!_scale_by_elem.emplace(id, scale).second)
      paramError("element_ids", "element_ids must be unique.");
  }
}

Real
PhysicsElementFieldPerturbationAux::computeValue()
{
  if (!_current_elem)
    mooseError("PhysicsElementFieldPerturbationAux requires an elemental evaluation.");

  const auto it = _scale_by_elem.find(_current_elem->id());
  if (it == _scale_by_elem.end())
    return _base[_qp];

  return _base[_qp] + _amplitude * it->second;
}
