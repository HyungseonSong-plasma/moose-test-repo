#pragma once

#include "FVFluxBC.h"

/**
 * Applies a signed particle-number flux on a plasma-dielectric interface to a
 * log-molar FV species balance.
 *
 * The species variable is defined only on the plasma block.  Therefore the
 * plasma-dielectric mesh face is an internal mesh face but a boundary of the
 * species variable domain, which is exactly the case supported by FVFluxBC.
 *
 * signed_number_flux [1/(m^2 s)] is positive outward from the plasma/species
 * domain and negative inward.  The conservative molar residual is
 *
 *   Gamma_signed / N_A  [mol/(m^2 s)].
 *
 * The same signed-number-flux functor should be reused by the dielectric
 * surface-current construction, so particle loss and surface charging have one
 * physical owner.
 */
class PhysicsFVLogMolarDielectricFluxBC : public FVFluxBC
{
public:
  static InputParameters validParams();

  PhysicsFVLogMolarDielectricFluxBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

private:
  const Moose::Functor<ADReal> & _signed_number_flux;
};
