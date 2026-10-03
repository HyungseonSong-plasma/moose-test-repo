#pragma once

#include "AuxKernel.h"

#include "libmesh/id_types.h"

#include <unordered_map>

class PhysicsElementFieldPerturbationAux : public AuxKernel
{
public:
  PhysicsElementFieldPerturbationAux(const InputParameters & parameters);

  static InputParameters validParams();

protected:
  virtual Real computeValue() override;

  const VariableValue & _base;
  const Real _amplitude;
  std::unordered_map<dof_id_type, Real> _scale_by_elem;
};
