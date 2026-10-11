#include "PhysicsLowerDSurfaceCurrent.h"

#include "FEProblemBase.h"
#include "FaceInfo.h"
#include "FVUtils.h"
#include "MooseMesh.h"

registerMooseObject("PhysicsApp", PhysicsLowerDSurfaceCurrent);

InputParameters
PhysicsLowerDSurfaceCurrent::validParams()
{
  auto params = ADKernel::validParams();
  params.addClassDescription(
      "Lower-dimensional surface-charge source driven by a signed higher-dimensional FV face "
      "current density functor. Pair with ADTimeDerivative so d(sigma_s)/dt=j_to_surface.");
  params.addRequiredParam<MooseFunctorName>(
      "surface_current_density",
      "Signed conventional current density to the dielectric surface [A/m^2]. Positive current "
      "increases sigma_s.");
  return params;
}

PhysicsLowerDSurfaceCurrent::PhysicsLowerDSurfaceCurrent(const InputParameters & parameters)
  : ADKernel(parameters),
    _surface_current_density(getFunctor<ADReal>("surface_current_density"))
{
  // The lower-D sigma_s residual depends directly on higher-D FV unknowns carried
  // by the face-current functor. Permit those AD couplings while the dedicated
  // lower-D/higher-D sparsity relationship is being constructed by libMesh/MOOSE.
  if (_tid == 0)
    getCheckedPointerParam<FEProblemBase *>("_fe_problem_base")
        ->setErrorOnJacobianNonzeroReallocation(false);
}

ADReal
PhysicsLowerDSurfaceCurrent::computeQpResidual()
{
  const Elem * const parent = _current_elem->interior_parent();
  if (!parent)
    mooseError(name(),
               ": lower-dimensional surface element ",
               _current_elem->id(),
               " has no interior_parent(). Use LowerDBlockFromSidesetGenerator on the "
               "plasma-dielectric sideset.");

  const unsigned int side = _mesh.getHigherDSide(_current_elem);
  if (side == libMesh::invalid_uint)
    mooseError(name(),
               ": cannot recover the higher-dimensional side for lower-D element ",
               _current_elem->id(),
               ".");

  const Elem * const neighbor = parent->neighbor_ptr(side);
  const FaceInfo * fi = nullptr;

  if (!neighbor || Moose::FV::elemHasFaceInfo(*parent, neighbor))
    fi = _mesh.faceInfo(parent, side);
  else
    fi = _mesh.faceInfo(neighbor, neighbor->which_neighbor_am_i(parent));

  if (!fi)
    mooseError(name(),
               ": no FV FaceInfo exists for lower-D element ",
               _current_elem->id(),
               " and its higher-D parent face.");

  // LowerDBlockFromSidesetGenerator preserves a higher-D parent, but that parent
  // is not guaranteed to be the plasma element: its orientation depends on the
  // source sideset/mesh. Infer the physical plasma owner from the current functor
  // domain instead. A dielectric interface current must have exactly one such side.
  const bool on_elem = _surface_current_density.hasFaceSide(*fi, true);
  const bool on_neighbor = _surface_current_density.hasFaceSide(*fi, false);

  if (on_elem == on_neighbor)
  {
    if (on_elem)
      mooseError(name(),
                 ": surface-current functor '",
                 _surface_current_density.functorName(),
                 "' is defined on both higher-dimensional sides of FV face ",
                 fi->id(),
                 ". Expected exactly one plasma-side owner for the dielectric interface.");
    else
      mooseError(name(),
                 ": surface-current functor '",
                 _surface_current_density.functorName(),
                 "' is not defined on either higher-dimensional side of FV face ",
                 fi->id(),
                 ".");
  }

  const Elem * const current_side = on_elem ? fi->elemPtr() : fi->neighborPtr();
  if (!current_side)
    mooseError(name(),
               ": could not recover the unique higher-dimensional owner for surface-current "
               "functor '",
               _surface_current_density.functorName(),
               "' on FV face ",
               fi->id(),
               ".");

  const Moose::FaceArg face_arg = {
      fi,
      Moose::FV::LimiterType::CentralDifference,
      /* elem_is_upwind = */ true,
      /* correct_skewness = */ false,
      current_side,
      /* state_limiter = */ nullptr};

  const ADReal j_to_surface = _surface_current_density(face_arg, determineState());

  // ADTimeDerivative contributes +test*d(sigma_s)/dt.  Therefore this
  // source contributes -test*j_to_surface to obtain d(sigma_s)/dt=j.
  return -_test[_i][_qp] * j_to_surface;
}
