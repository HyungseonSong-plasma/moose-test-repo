#pragma once

#include "FunctorMaterial.h"

#include <string>

/**
 * Transparent pass-through functor used to record the exact spatial/state
 * argument at which a scalar source first becomes invalid.
 *
 * The returned ADReal is exactly the value obtained from ``source`` at the
 * caller-supplied argument and state.  Diagnostics are therefore observational:
 * they do not clamp, floor, reconstruct, or otherwise alter the source value.
 */
class PhysicsPassThroughForensicMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsPassThroughForensicMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _source;
  const MooseFunctorName _property_name;
  const std::string _diagnostic_file;
  const std::string _diagnostic_tag;
};
