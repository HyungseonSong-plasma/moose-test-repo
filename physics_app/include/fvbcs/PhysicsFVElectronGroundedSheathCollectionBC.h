#pragma once

#include "FVQpFluxBC.h"

/**
 * Primary-electron collection at a grounded conducting wall for a
 * sheath-unresolved finite-volume plasma model.
 *
 * The plasma-side FV cell is interpreted as the sheath edge.  For the
 * electron-repelling branch (phi_s >= 0 V with grounded phi_w = 0 V),
 *
 *   Gamma_e,out / n_ref
 *     = 0.25 * n_e_hat * cbar_e * exp(-phi_s / T_e)
 *
 * where T_e[eV] = (2/3) * mean_electron_energy[eV] and
 *
 *   cbar_e = sqrt(8 e T_e / (pi m_e)).
 *
 * Positive return values are outward primary-electron loss.  Secondary
 * emission remains a separate owner and is intentionally not represented here.
 */
class PhysicsFVElectronGroundedSheathCollectionBC : public FVQpFluxBC
{
public:
  static InputParameters validParams();
  PhysicsFVElectronGroundedSheathCollectionBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _mean_electron_energy;
  const Moose::Functor<ADReal> & _potential;
};
