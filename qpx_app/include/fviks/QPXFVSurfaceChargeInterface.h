#pragma once

#include "FVInterfaceKernel.h"

#include <utility>

class QPXSurfaceChargeState;

/**
 * Finite-volume electrostatic interface with surface charge.
 *
 * Two modes are supported:
 *
 * prescribed:
 *   use_surface_charge_state = false
 *   surface_charge = <constant or material property>
 *
 * dynamic face state:
 *   use_surface_charge_state = true
 *   surface_charge_state = <QPXSurfaceChargeState>
 *   wall_number_flux = <electron wall flux functor>
 *
 * In dynamic mode the nonlinear residual uses
 *
 *   sigma_s^(n+1)
 *     = sigma_state^n(face)
 *       - e * Gamma_e,w^(n+1)(face) * dt
 *
 * while QPXSurfaceChargeState commits the converged value at TIMESTEP_END.
 *
 * One FV potential variable spans both subdomains:
 *
 *   eps_r2 E2_n - eps_r1 E1_n = sigma_s / eps_0
 *
 * with n pointing from subdomain1 to subdomain2.
 */
class QPXFVSurfaceChargeInterface : public FVInterfaceKernel
{
public:
  static InputParameters validParams();
  QPXFVSurfaceChargeInterface(const InputParameters & parameters);

  void computeResidual(const FaceInfo & fi) override;
  void computeJacobian(const FaceInfo & fi) override;

protected:
  ADReal computeQpResidual() override;

private:
  std::pair<ADReal, ADReal> oneSidedFluxes() const;

  ADReal currentSurfaceCharge() const;

  ADReal evaluateFaceFunctor(
      const Moose::Functor<ADReal> & functor) const;

  const Moose::Functor<ADReal> & _coeff1;
  const Moose::Functor<ADReal> & _coeff2;

  /// Direct prescribed/property mode, retained for isolated regression.
  const ADMaterialProperty<Real> & _surface_charge;

  const bool _use_surface_charge_state;

  const QPXSurfaceChargeState * _surface_charge_state;
  const Moose::Functor<ADReal> * _wall_number_flux;
};
