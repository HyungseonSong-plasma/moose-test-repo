#pragma once

#include "SideUserObject.h"
#include "ADFunctorInterface.h"

#include <map>

/**
 * Owns converged local dielectric surface-charge state on mesh faces.
 *
 * State storage is deliberately separated from MaterialData. Each face is
 * keyed by FaceInfo::id(), and the converged sigma_s is stored in restartable
 * data.
 *
 * The canonical sign convention is:
 *
 *   n                  = outward from plasma toward the dielectric
 *   j_to_surface > 0   = positive conventional charge current from plasma
 *                        into the dielectric surface
 *
 * At TIMESTEP_END:
 *
 *   sigma_s^(n+1) = sigma_s^n + j_to_surface^(n+1) * dt
 *
 * The supplied current-density functor must be assembled from the same
 * canonical particle-wall flux functors used by the transport boundary
 * residuals. This object does not re-evaluate ion, electron, or SEE physics.
 *
 * During a nonlinear electrostatic solve, an interface/boundary object may
 * query sigma_s^n from this object and add the current AD increment itself.
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

  /// Converged surface charge on one face [C/m^2].
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

  /// Signed conventional charge-current density into the surface [A/m^2].
  const Moose::Functor<ADReal> & _surface_current_density;
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