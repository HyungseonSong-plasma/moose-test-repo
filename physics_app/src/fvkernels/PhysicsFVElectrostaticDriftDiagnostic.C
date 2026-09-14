#include "PhysicsFVElectrostaticDriftDiagnostic.h"

#include "metaphysicl/raw_type.h"

#include <algorithm>

registerMooseObject("PhysicsApp", PhysicsFVElectrostaticDriftDiagnostic);

InputParameters
PhysicsFVElectrostaticDriftDiagnostic::validParams()
{
  auto params = PhysicsFVElectrostaticDrift::validParams();
  params.addClassDescription(
      "Diagnostic-only PhysicsFVElectrostaticDrift wrapper that reports exact internal-face "
      "electrostatic drift quantities for selected element IDs.");
  params.addRequiredParam<std::vector<unsigned int>>(
      "diagnostic_element_ids",
      "Element IDs defining the small internal-face cluster to report.");
  return params;
}

PhysicsFVElectrostaticDriftDiagnostic::PhysicsFVElectrostaticDriftDiagnostic(
    const InputParameters & parameters)
  : PhysicsFVElectrostaticDrift(parameters),
    _diagnostic_element_ids(getParam<std::vector<unsigned int>>("diagnostic_element_ids"))
{
}

bool
PhysicsFVElectrostaticDriftDiagnostic::probeFace() const
{
  if (!_face_info || !_face_info->neighborPtr())
    return false;

  const auto elem_id = static_cast<unsigned int>(_face_info->elem().id());
  const auto neighbor_id = static_cast<unsigned int>(_face_info->neighbor().id());
  const auto selected = [this](const unsigned int id)
  {
    return std::find(_diagnostic_element_ids.begin(), _diagnostic_element_ids.end(), id) !=
           _diagnostic_element_ids.end();
  };
  return selected(elem_id) && selected(neighbor_id);
}

ADReal
PhysicsFVElectrostaticDriftDiagnostic::computeQpResidual()
{
  const ADReal parent_residual = PhysicsFVElectrostaticDrift::computeQpResidual();
  if (!probeFace())
    return parent_residual;

  const auto state = determineState();
  const auto & limiter_time =
      _subproblem.isTransient()
          ? Moose::StateArg(1, Moose::SolutionIterationType::Time)
          : Moose::StateArg(1, Moose::SolutionIterationType::Nonlinear);

  const auto centered_face =
      makeFace(*_face_info,
               Moose::FV::LimiterType::CentralDifference,
               true,
               false,
               &limiter_time);

  const ADRealVectorValue electric_field = -_potential.gradient(centered_face, state);
  const ADReal mobility_face = _mobility(centered_face, state);
  const ADReal carrier_face = _carrier(centered_face, state);
  const ADReal electric_field_normal = electric_field * _normal;
  const ADReal grad_phi_normal = -electric_field_normal;
  const ADReal drift_normal = _charge_number * mobility_face * electric_field_normal;

  const bool elem_is_upwind = MetaPhysicL::raw_value(drift_normal) >= 0.0;
  const auto transported_face =
      makeFace(*_face_info,
               Moose::FV::limiterType(_advected_interp_method),
               elem_is_upwind,
               false,
               &limiter_time);
  const ADReal transported_value = _var(transported_face, state);
  const ADReal reconstructed_residual = carrier_face * transported_value * drift_normal;

  const ADReal phi_elem = _potential(elemArg(), state);
  const ADReal phi_neighbor = _potential(neighborArg(), state);
  const ADReal u_elem = _var(elemArg(), state);
  const ADReal u_neighbor = _var(neighborArg(), state);

  const Real central_grad_phi_normal =
      (MetaPhysicL::raw_value(phi_neighbor) - MetaPhysicL::raw_value(phi_elem)) /
      _face_info->dCNMag() * (_face_info->eCN() * _normal);
  const Real actual_grad_phi_normal = MetaPhysicL::raw_value(grad_phi_normal);
  const auto & fc = _face_info->faceCentroid();

  mooseInfo("ISSUE228_DRIFT",
            " elem=", _face_info->elem().id(),
            " neighbor=", _face_info->neighbor().id(),
            " face_x=", fc(0),
            " face_y=", fc(1),
            " phi_elem=", MetaPhysicL::raw_value(phi_elem),
            " phi_neighbor=", MetaPhysicL::raw_value(phi_neighbor),
            " central_grad_phi_n=", central_grad_phi_normal,
            " actual_grad_phi_n=", actual_grad_phi_normal,
            " nonorth_corr_grad_phi_n=", actual_grad_phi_normal - central_grad_phi_normal,
            " E_n=", MetaPhysicL::raw_value(electric_field_normal),
            " mobility=", MetaPhysicL::raw_value(mobility_face),
            " drift_velocity_n=", MetaPhysicL::raw_value(drift_normal),
            " u_elem=", MetaPhysicL::raw_value(u_elem),
            " u_neighbor=", MetaPhysicL::raw_value(u_neighbor),
            " u_face=", MetaPhysicL::raw_value(transported_value),
            " residual=", MetaPhysicL::raw_value(parent_residual),
            " residual_reconstructed=", MetaPhysicL::raw_value(reconstructed_residual));

  return parent_residual;
}
