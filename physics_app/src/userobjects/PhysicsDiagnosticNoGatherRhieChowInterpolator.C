#include "PhysicsDiagnosticNoGatherRhieChowInterpolator.h"

registerMooseObject("PhysicsApp", PhysicsDiagnosticNoGatherRhieChowInterpolator);

InputParameters
PhysicsDiagnosticNoGatherRhieChowInterpolator::validParams()
{
  auto params = INSFVRhieChowInterpolator::validParams();
  params.addClassDescription(
      "Diagnostic-only INSFVRhieChowInterpolator that skips execute() to attribute GatherRCData/AD setup memory.");
  return params;
}

PhysicsDiagnosticNoGatherRhieChowInterpolator::PhysicsDiagnosticNoGatherRhieChowInterpolator(
    const InputParameters & parameters)
  : INSFVRhieChowInterpolator(parameters)
{
}
