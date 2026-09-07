#pragma once

#include "ADMaterial.h"
#include "MooseUtils.h"
#include "QPX.h"

class TotalCrossSection : public ADMaterial
{
public:
  TotalCrossSection(const InputParameters & parameters);

  static InputParameters validParams();

protected:
  virtual void computeQpProperties() override;

  const VectorPostprocessorValue & _x;
  std::vector<unsigned int> _collision_partner_index;
  ADMaterialProperty<Real> & _total_cross_section;
  std::vector<const ADMaterialProperty<Real> *> _cross_sections;
};
