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

  params.addParam<MaterialPropertyName>(
      "reaction_material", "Existing RF reaction coefficient neg_a.");
  params.addParam<MaterialPropertyName>(
      "coupling_material", "Existing RF cross-coupling coefficient b.");
  params.addParam<Real>(
      "imaginary_source", "Prescribed RF imaginary source in solver equation units.");
  params.addParam<std::vector<BoundaryName>>(
      "ground_boundaries", {}, "Zero-field boundaries for both RF components.");
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
  const bool reaction = isParamValid("reaction_material");
  const bool coupling = isParamValid("coupling_material");
  if (reaction != coupling)
    paramError("reaction_material", "Supply both Maxwell material coefficients together.");
  if ((!getParam<std::vector<BoundaryName>>("ground_boundaries").empty() ||
       isParamValid("imaginary_source")) && !reaction)
    paramError("reaction_material", "Provide RF coefficients before creating sources or boundaries.");
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

void
MaxwellPhysics::addFEKernels()
{
  if (!isParamValid("reaction_material"))
    return;
  const auto real = getParam<VariableName>("field_real");
  const auto imag = getParam<VariableName>("field_imag");
  for (const auto & variable : {real, imag})
  {
    {
      const std::string type = "Diffusion";
      auto params = getFactory().getValidParams(type);
      params.set<NonlinearVariableName>("variable") = variable;
      assignBlocks(params, _blocks);
      getProblem().addKernel(type, name() + "_" + variable + "_diffusion", params);
    }
    {
      const std::string type = "MatReaction";
      auto params = getFactory().getValidParams(type);
      params.set<NonlinearVariableName>("variable") = variable;
      params.set<MaterialPropertyName>("reaction_rate") =
          getParam<MaterialPropertyName>("reaction_material");
      assignBlocks(params, _blocks);
      getProblem().addKernel(type, name() + "_" + variable + "_reaction", params);
    }
    {
      const std::string type = "MatCoupledForce";
      auto params = getFactory().getValidParams(type);
      params.set<NonlinearVariableName>("variable") = variable;
      params.set<std::vector<VariableName>>("v") = {variable == real ? imag : real};
      params.set<std::vector<Real>>("coef") = {variable == real ? 1.0 : -1.0};
      params.set<std::vector<MaterialPropertyName>>("material_properties") =
          {getParam<MaterialPropertyName>("coupling_material")};
      assignBlocks(params, _blocks);
      getProblem().addKernel(type, name() + "_" + variable + "_coupling", params);
    }
  }
  if (isParamValid("imaginary_source"))
  {
    const std::string type = "BodyForce";
    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") = imag;
    params.set<Real>("value") = getParam<Real>("imaginary_source");
    assignBlocks(params, _blocks);
    getProblem().addKernel(type, name() + "_imaginary_source", params);
  }
}

void
MaxwellPhysics::addFEBCs()
{
  if (!isParamValid("reaction_material"))
    return;
  const auto real = getParam<VariableName>("field_real");
  const auto imag = getParam<VariableName>("field_imag");
  for (const auto & boundary : getParam<std::vector<BoundaryName>>("ground_boundaries"))
    for (const auto & variable : {real, imag})
    {
      const std::string type = "DirichletBC";
      auto params = getFactory().getValidParams(type);
      params.set<NonlinearVariableName>("variable") = variable;
      params.set<std::vector<BoundaryName>>("boundary") = {boundary};
      params.set<Real>("value") = 0;
      getProblem().addBoundaryCondition(
          type, name() + "_" + variable + "_ground_" + boundary, params);
    }
}

}

using Plasma::MaxwellPhysics;
registerPhysicsBaseTasks("PhysicsApp", MaxwellPhysics);
registerMooseAction("PhysicsApp", MaxwellPhysics, "check_integrity");
registerMooseAction("PhysicsApp", MaxwellPhysics, "add_kernel");
registerMooseAction("PhysicsApp", MaxwellPhysics, "add_bc");
