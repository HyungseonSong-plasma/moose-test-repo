#include "CreateChangeMarker.h"

registerMooseObject("PhysicsApp", CreateChangeMarker);

InputParameters
CreateChangeMarker::validParams()
{
  InputParameters params = GeneralVectorPostprocessor::validParams();

  params.addRequiredParam<VectorPostprocessorName>(
      "original_vpp",
      "The original vectorpostprocessor.");
  params.addRequiredParam<std::string>("original_vector_name", "The name of the vector to be filtered.");
  params.addRequiredParam<VectorPostprocessorName>(
      "filtered_vpp",
      "The filtered vectorpostprocessor.");
  params.addRequiredParam<std::string>("filtered_vector_name", "The name of the vector to be filtered.");

  params.addClassDescription("Create a change marker vector by comparing original "
                             "VectorPostprocessor to changed VectorPostprocessor.");
  return params;
}

CreateChangeMarker::CreateChangeMarker(const InputParameters & parameters)
  : GeneralVectorPostprocessor(parameters),
    _fv_values(getVectorPostprocessorValue("filtered_vpp", getParam<std::string>("filtered_vector_name"))),
    _ov_values(getVectorPostprocessorValue("original_vpp", getParam<std::string>("original_vector_name")))
{
  _changeMarker = &declareVector("change_marker");
}

void
CreateChangeMarker::initialize()
{
  _changeMarker->clear();
}

void
CreateChangeMarker::execute()
{
  // Sanity check to prevent out-of-bounds errors if vectors do not match
  if (_fv_values.size() != _ov_values.size())
  {
    mooseError("The two coupled VectorPostprocessors must have the same size. "
               "Original vector size: ", _ov_values.size(), ", Filtered vector size: ", _fv_values.size());
  }

  size_t n = _fv_values.size();
  _changeMarker->resize(n);

  for (size_t k = 0; k < n; k++) {
    if (_ov_values[k] == _fv_values[k])
      (*_changeMarker)[k] = 0;
    else
      (*_changeMarker)[k] = 1;
  }
}
