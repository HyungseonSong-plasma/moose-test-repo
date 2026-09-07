#pragma once

#include "FVFluxBC.h"

/**
 * Outward wall flux for the normalized electron-energy equation.
 *
 * The frozen #26 E4-E5 contract is
 *
 *   Gamma_eps / (n_ref * epsilon_ref)
 *     = (5/6) * v_e,th * n_eps_hat
 *       - (4 eV / epsilon_ref) * (Gamma_e,SEE / n_ref).
 *
 * The SEE particle-number flux is deliberately supplied as a functor.  This
 * object therefore does not own gamma or ion-incidence semantics from #27 A8.
 * Positive return values are outward energy loss; negative values inject
 * electron energy into the domain.
 */
class QPXFVElectronEnergyWallFluxBC : public FVFluxBC
{
public:
  static InputParameters validParams();
  QPXFVElectronEnergyWallFluxBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _electron_energy_density;
  const Moose::Functor<ADReal> & _mean_electron_energy;
  const Moose::Functor<ADReal> & _see_number_flux;
  const Real _energy_reference_eV;
};
