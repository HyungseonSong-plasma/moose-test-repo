#include "MaxwellPhysics.h"

namespace Plasma
{

InputParameters
MaxwellPhysics::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Checks existing maxwell inputs without creating or modifying solver equations.");
  params.addRequiredParam<VariableName>(
      "field_real", "Existing solver variable for the real electromagnetic field.");
  params.addRequiredParam<VariableName>(
      "field_imag", "Existing solver variable for the imaginary electromagnetic field.");
  params.addRequiredParam<Real>(
      "frequency_hz", "Positive electromagnetic driving frequency in hertz.");
  return params;
}

MaxwellPhysics::MaxwellPhysics(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  if (getParam<Real>("frequency_hz") <= 0)
    paramError("frequency_hz", "The frequency must be greater than zero.");
  if (getParam<VariableName>("field_real").empty() ||
      getParam<VariableName>("field_imag").empty() ||
      getParam<VariableName>("field_real") == getParam<VariableName>("field_imag"))
    paramError("field_imag", "Real and imaginary fields must use different solver variables.");
}

void
MaxwellPhysics::checkIntegrity() const
{
  const auto & real_field = getParam<VariableName>("field_real");
  const auto & imaginary_field = getParam<VariableName>("field_imag");
  if (!solverVariableExists(real_field))
    paramError("field_real", "Real electromagnetic field was not found: ", real_field);
  if (!solverVariableExists(imaginary_field))
    paramError("field_imag", "Imaginary electromagnetic field was not found: ", imaginary_field);
  if (isVariableFV(real_field) != isVariableFV(imaginary_field))
    paramError("field_imag", "Real and imaginary fields must use the same numerical method.");
}

}

using Plasma::MaxwellPhysics;
registerPhysicsBaseTasks("PhysicsApp", MaxwellPhysics);
registerMooseAction("PhysicsApp", MaxwellPhysics, "check_integrity");
