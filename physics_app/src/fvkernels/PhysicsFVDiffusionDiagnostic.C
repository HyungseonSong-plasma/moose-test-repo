#include "PhysicsFVDiffusionDiagnostic.h"

#include "metaphysicl/raw_type.h"

#include <algorithm>
#include <iomanip>
#include <iostream>
#include <sstream>

registerMooseObject("PhysicsApp", PhysicsFVDiffusionDiagnostic);

InputParameters
PhysicsFVDiffusionDiagnostic::validParams()
{
  auto params = FVDiffusion::validParams();
  params.addClassDescription(
      "Diagnostic-only FVDiffusion wrapper that reports the framework grad(u).n used by the "
      "parent diffusion residual on selected internal faces and, optionally, selected boundary "
      "faces.");
  params.addRequiredParam<std::vector<unsigned int>>(
      "diagnostic_element_ids",
      "Element IDs defining the cells whose internal or boundary faces may be reported.");
  params.addParam<bool>(
      "diagnostic_boundary_faces",
      false,
      "If true, report boundary faces whose owning element is in diagnostic_element_ids. "
      "The returned residual remains exactly the parent FVDiffusion residual.");
  return params;
}

PhysicsFVDiffusionDiagnostic::PhysicsFVDiffusionDiagnostic(const InputParameters & params)
  : FVDiffusion(params),
    _diagnostic_element_ids(getParam<std::vector<unsigned int>>("diagnostic_element_ids")),
    _diagnostic_boundary_faces(getParam<bool>("diagnostic_boundary_faces"))
{
}

bool
PhysicsFVDiffusionDiagnostic::probeFace() const
{
  if (!_face_info)
    return false;

  const auto selected = [this](const unsigned int id)
  {
    return std::find(_diagnostic_element_ids.begin(), _diagnostic_element_ids.end(), id) !=
           _diagnostic_element_ids.end();
  };

  const auto elem_id = static_cast<unsigned int>(_face_info->elem().id());
  const bool is_internal = _var.isInternalFace(*_face_info);

  // IMPORTANT: do not use neighborPtr()==nullptr to identify a physical FV boundary.
  // MOOSE may attach a ghost neighbor for Dirichlet boundary reconstruction, so a physical
  // boundary can have a non-null neighborPtr().  The variable's isInternalFace() predicate is
  // the framework-semantic discriminator used by FVDiffusion itself.
  if (!is_internal)
    return _diagnostic_boundary_faces && selected(elem_id);

  if (!_face_info->neighborPtr())
    return false;

  const auto neighbor_id = static_cast<unsigned int>(_face_info->neighbor().id());
  return selected(elem_id) && selected(neighbor_id);
}

ADReal
PhysicsFVDiffusionDiagnostic::computeQpResidual()
{
  // The diagnostic is deliberately residual-equivalent: the parent residual is evaluated first
  // and returned unchanged. Any reported dudn therefore comes from the same framework helper
  // used by FVDiffusion itself, including the Dirichlet ghost-cell path on boundary faces.
  const ADReal parent_residual = FVDiffusion::computeQpResidual();
  if (!probeFace())
    return parent_residual;

  const auto state = determineState();
  const ADReal dudn = gradUDotNormal(state, _correct_skewness);
  const ADReal u_elem = _var(elemArg(), state);
  const bool is_boundary = !_var.isInternalFace(*_face_info);

  Real central_dudn = 0.0;
  Real u_neighbor = 0.0;
  if (!is_boundary)
  {
    const ADReal neighbor_value = _var(neighborArg(), state);
    u_neighbor = MetaPhysicL::raw_value(neighbor_value);
    central_dudn =
        (u_neighbor - MetaPhysicL::raw_value(u_elem)) /
        _face_info->dCNMag() * (_face_info->eCN() * _normal);
  }

  std::ostringstream boundary_ids;
  bool first = true;
  for (const auto id : _face_info->boundaryIDs())
  {
    if (!first)
      boundary_ids << ',';
    boundary_ids << id;
    first = false;
  }

  const auto & fc = _face_info->faceCentroid();
  std::cout << std::setprecision(17)
            << "ISSUE228_DIFF"
            << " face_type=" << (is_boundary ? "boundary" : "internal")
            << " elem=" << _face_info->elem().id();
  if (!is_boundary)
    std::cout << " neighbor=" << _face_info->neighbor().id();
  std::cout << " boundary_ids=" << boundary_ids.str()
            << " face_x=" << fc(0)
            << " face_y=" << fc(1)
            << " normal_x=" << _normal(0)
            << " normal_y=" << _normal(1)
            << " dcn_mag=" << _face_info->dCNMag()
            << " ecn_dot_normal=" << (_face_info->eCN() * _normal)
            << " u_elem=" << MetaPhysicL::raw_value(u_elem);
  if (!is_boundary)
    std::cout << " u_neighbor=" << u_neighbor
              << " central_dudn=" << central_dudn
              << " nonorth_corr_dudn=" << MetaPhysicL::raw_value(dudn) - central_dudn;
  std::cout << " actual_dudn=" << MetaPhysicL::raw_value(dudn)
            << " residual=" << MetaPhysicL::raw_value(parent_residual)
            << std::endl;

  return parent_residual;
}
