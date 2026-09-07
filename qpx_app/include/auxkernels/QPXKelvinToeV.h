#pragma once

#include "AuxKernel.h"


class QPXKelvinToeV : public AuxKernel
{
public:
  QPXKelvinToeV(const InputParameters & parameters);

  static InputParameters validParams();

  virtual Real computeValue() override;

protected:

  /// Coupled background gas temperature variable
  const Real _T_gas;
};