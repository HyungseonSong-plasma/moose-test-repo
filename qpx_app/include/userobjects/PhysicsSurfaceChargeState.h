#pragma once

#include "SideUserObject.h"
#include "ADFunctorInterface.h"

#include <map>

/**
 * Owns converged local surface-charge state on FV faces.
 *
 * State storage is deliberately separated from MaterialData. Each FV face is
 * keyed by FaceInfo::id(), and the converged sigma_s is stored in restartable
 * data.
 *
 * At TIMESTEP_END:
 *
 *   sigma_s^(n+1) = sigma_s^n - e * Gamma_e,w^(n+1) * dt
 *
 * using the same wall-number-flux functor consumed by the electron FV BC.
 *
 * During the nonlinear solve, PhysicsFVSurfaceChargeInterface queries sigma_s^n
 * from this object and adds the current AD wall-flux increment itself.
 */
class PhysicsSurfaceChargeState : public SideUserObject, public ADFunctorInterface
{
public:
  static InputParameters validParams();
  PhysicsSurfaceChargeState(const InputParameters & parameters);

  void initialize() override;
  void execute() override;
  void threadJoin(const UserObject & y) override;
  void finalize() override;

  /// Converged surface charge on one FV face [C/m^2].
  Real surfaceCharge(dof_id_type face_id) const;

  /// Global diagnostics after finalize().
  Real totalCharge() const { return _total_charge; }
  Real surfaceArea() const { return _surface_area; }
  Real averageSurfaceCharge() const
  {
    return _surface_area > 0.0 ? _total_charge / _surface_area : 0.0;
  }

private:
  ADReal evaluateFaceFunctor(
      const Moose::Functor<ADReal> & functor,
      const FaceInfo & fi) const;

  const Moose::Functor<ADReal> & _wall_number_flux;
  const Real _initial_surface_charge;

  /// Converged, restartable face-local state.
  std::map<dof_id_type, Real> & _surface_charge;

  /// Thread-local staging for the just-converged timestep.
  std::map<dof_id_type, Real> _pending_surface_charge;
  std::map<dof_id_type, Real> _pending_face_measure;

  /// Global diagnostics for the latest finalized state.
  Real _total_charge;
  Real _surface_area;
};
