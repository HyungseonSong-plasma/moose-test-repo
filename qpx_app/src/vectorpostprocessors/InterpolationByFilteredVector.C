#include "InterpolationByFilteredVector.h"

registerMooseObject("qpxApp", InterpolationByFilteredVector);

InputParameters
InterpolationByFilteredVector::validParams()
{
  InputParameters params = GeneralVectorPostprocessor::validParams();

  params.addRequiredParam<VectorPostprocessorName>(
      "vpp",
      "The vectorpostprocessor on whose values we perform a filter-forward interpolation.");
  params.addRequiredParam<std::string>("vector_name", "The name of the vector to be filtered.");
  params.addRequiredParam<VectorPostprocessorName>("change_marker_vpp", "The vector to store the change status of the original vector.");
  params.addRequiredParam<std::string>("marker_vector_name", "The name of the vector to be filtered.");

  params.addClassDescription("Performs a filter-forward interpolation on the data contained in "
                             "another VectorPostprocessor");
  return params;
}

InterpolationByFilteredVector::InterpolationByFilteredVector(const InputParameters & parameters)
  : GeneralVectorPostprocessor(parameters),
    _fv_values(getVectorPostprocessorValue("vpp", getParam<std::string>("vector_name"))),
    _changeMarker(getVectorPostprocessorValue("change_marker_vpp", getParam<std::string>("marker_vector_name")))
{
  _sample = &declareVector(getParam<std::string>("vector_name"));
}

void
InterpolationByFilteredVector::initialize()
{
  _sample->clear();
}

void
InterpolationByFilteredVector::execute()
{
  size_t n = _fv_values.size();

  *_sample = _fv_values;

  // Build the anchor list using indices where master was 'Unchanged'
  std::vector<size_t> anchors;
  for (size_t i = 0; i < n; ++i) {
    if (_changeMarker[i] == 0) {
      anchors.push_back(i);
    }
  }

  if (anchors.size() < 2) return;

  // Interpolate the secondary gaps using its own anchor values
  for (size_t a = 0; a < anchors.size() - 1; ++a) {
    size_t idx_start = anchors[a];
    size_t idx_end = anchors[a + 1];

    if (idx_end - idx_start > 1) {
      double y_start = _fv_values[idx_start];
      double y_end = _fv_values[idx_end];
      double num_steps = static_cast<double>(idx_end - idx_start);

      for (size_t i = idx_start + 1; i < idx_end; ++i) {
        double t = static_cast<double>(i - idx_start) / num_steps;
        (*_sample)[i] = y_start + t * (y_end - y_start);
      }
    }
  }

  // Handle any trailing edge elements that the master forward-filled
  size_t last_anchor = anchors.back();
  if (last_anchor < n - 1) {
    for (size_t i = last_anchor + 1; i < n; ++i) {
      (*_sample)[i] = _fv_values[last_anchor]; // Forward-fill using secondary's last valid anchor
    }
  }
}
