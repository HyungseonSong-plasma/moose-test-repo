#include "PhysicsWaferD1GeometryProbeAux.h"

#include "FaceInfo.h"
#include "FVUtils.h"
#include "MooseMesh.h"
#include "MooseFunctorArguments.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsWaferD1GeometryProbeAux);

InputParameters
PhysicsWaferD1GeometryProbeAux::validParams()
{
  auto params = AuxKernel::validParams();
  params.addClassDescription(
      "Observational Issue397 D1 plasma-sided face geometry and adjacent FEM E_n; no physics modifications.");
  params.addRequiredParam<MooseFunctorName>(
      "surface_current_density", "Plasma-only current functor used to resolve FaceInfo side.");
  params.addRequiredParam<MooseFunctorName>(
      "potential", "Continuous FEM potential used by the actual electron sheath material.");
  params.addRequiredParam<MooseEnum>(
      "component", MooseEnum("normal_r normal_z owner d_perp e_n"),
      "Plasma-outward unit normal component, FaceInfo owner sign, adjacent-cell "
      "normal separation [m], or plasma-sided E dot n [V/m].");
  return params;
}

PhysicsWaferD1GeometryProbeAux::PhysicsWaferD1GeometryProbeAux(const InputParameters & parameters)
  : AuxKernel(parameters),
    _surface_current_density(getFunctor<ADReal>("surface_current_density")),
    _potential(getFunctor<ADReal>("potential")),
    _component(getParam<MooseEnum>("component"))
{
}

Real
PhysicsWaferD1GeometryProbeAux::computeValue()
{
  const Elem * const parent = _current_elem->interior_parent();
  if (!parent)
    mooseError(name(), ": lower-D element has no interior_parent: ", _current_elem->id());

  const unsigned int side = _mesh.getHigherDSide(_current_elem);
  if (side == libMesh::invalid_uint)
    mooseError(name(), ": invalid higher-dimensional side.");

  const Elem * const neighbor = parent->neighbor_ptr(side);
  const FaceInfo * fi = (!neighbor || Moose::FV::elemHasFaceInfo(*parent, neighbor))
                            ? _mesh.faceInfo(parent, side)
                            : _mesh.faceInfo(neighbor, neighbor->which_neighbor_am_i(parent));
  if (!fi)
    mooseError(name(), ": no FaceInfo for lower-D element.");

  const bool on_elem = _surface_current_density.hasFaceSide(*fi, true);
  const bool on_neighbor = _surface_current_density.hasFaceSide(*fi, false);
  if (on_elem == on_neighbor)
    mooseError(name(), ": expected exactly one plasma owner of face ", fi->id());

  const Real sign = on_elem ? 1.0 : -1.0;
  const RealVectorValue n_out = sign * fi->normal();
  if (_component == "normal_r")
    return n_out(0);
  if (_component == "normal_z")
    return n_out(1);
  if (_component == "owner")
    return sign;

  const Point center = on_elem ? fi->elemCentroid() : fi->neighborCentroid();
  const Real d_perp = std::abs((center - fi->faceCentroid()) * n_out);
  if (d_perp <= 0.0)
    mooseError(name(), ": non-positive plasma face normal distance.");

  if (_component == "d_perp")
    return d_perp;

  const Elem * current_side = on_elem ? fi->elemPtr() : fi->neighborPtr();
  const Moose::FaceArg face_arg = {
      fi, Moose::FV::LimiterType::CentralDifference, true, false, current_side, nullptr};
  const ADRealVectorValue electric_field =
      on_elem ? -_potential.gradient(face_arg.makeElem(), Moose::currentState())
              : -_potential.gradient(face_arg.makeNeighbor(), Moose::currentState());
  const ADReal electric_normal = electric_field * n_out;
  return MetaPhysicL::raw_value(electric_normal);
}
