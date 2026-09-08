#pragma once

#include "ADMaterial.h"

/**
 * Local electron surface-charge accumulator.
 *
 * The electron wall number flux is NOT reconstructed here.
 * This material directly consumes the same wall-number-flux functor used by
 * the FV electron boundary condition.
 *
 * Local state:
 *
 *   J_s = -e Gamma_e,w
 *
 *   sigma_s^(n+1) = sigma_s^n + J_s^(n+1) dt
 *
 * Current scope:
 *   - electron contribution only
 *   - no ion current
 *   - no secondary electron emission
 *   - no surface conduction
 *   - downstream electrostatic coupling is handled by the interface kernel
 */
class PhysicsElectronSurfaceChargeMaterial : public ADMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronSurfaceChargeMaterial(const InputParameters & parameters);

protected:
  void initQpStatefulProperties() override;
  void computeQpProperties() override;

  /// Exact wall-flux functor also consumed by FVFunctorNeumannBC.
  const Moose::Functor<ADReal> & _wall_number_flux;

  const Real _initial_surface_charge;

  ADMaterialProperty<Real> & _surface_electron_number_flux;
  ADMaterialProperty<Real> & _surface_current_density;
  ADMaterialProperty<Real> & _surface_charge;

  const MaterialProperty<Real> & _surface_charge_old;
};
