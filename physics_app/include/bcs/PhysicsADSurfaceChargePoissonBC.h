#pragma once

#include "ADIntegratedBC.h"

/**
 * Adds a lower-dimensional dielectric surface-charge state to the FEM Poisson
 * weak form.
 *
 * The canonical normalized Poisson equation is
 *
 *   -div(epsilon_r grad(phi)) = rho_volume/epsilon_0
 *
 * and a dielectric surface charge sigma_s contributes the internal-surface
 * source
 *
 *   - integral_Gamma test * sigma_s/epsilon_0 dA
 *
 * to the residual.  For a continuous FEM potential spanning plasma and
 * dielectric blocks this weak term is equivalent to
 *
 *   n . (D_dielectric - D_plasma) = sigma_s.
 */
class PhysicsADSurfaceChargePoissonBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();

  PhysicsADSurfaceChargePoissonBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

private:
  const ADVariableValue & _surface_charge;
};
