#include "FilterForwardInterpolate.h"

registerMooseObject("qpxApp", FilterForwardInterpolate);

InputParameters
FilterForwardInterpolate::validParams()
{
  InputParameters params = GeneralVectorPostprocessor::validParams();

  params.addRequiredParam<VectorPostprocessorName>(
      "vpp",
      "The vectorpostprocessor on whose values we perform a filter-forward interpolation.");
  params.addRequiredParam<std::string>("filtered_vector", "The name of the vector to be filtered.");

  params.addClassDescription("Performs a filter-forward interpolation on the data contained in "
                             "another VectorPostprocessor");
  return params;
}

FilterForwardInterpolate::FilterForwardInterpolate(const InputParameters & parameters)
  : GeneralVectorPostprocessor(parameters),
    _fv_name(getParam<std::string>("filtered_vector")),
    _fv_values(getVectorPostprocessorValue("vpp", _fv_name))
{
  _sample = &declareVector(_fv_name);
}

void
FilterForwardInterpolate::initialize()
{
  _sample->clear();
}

void
FilterForwardInterpolate::execute()
{
  size_t n = _fv_values.size();
  if (n == 0) return;

  *_sample = _fv_values;
  if (n <= 2) return;

  // Step 1: Find all valid "anchor" indices that form a monotonically increasing sequence
  std::vector<size_t> anchors;
  anchors.push_back(0);

  double current_max = _fv_values[0];
  for (size_t i = 1; i < n; ++i) {
    if (_fv_values[i] >= current_max) {
      current_max = _fv_values[i];
      anchors.push_back(i);
    }
  }

  // Step 2: Linearly interpolate the gaps between anchor points
  for (size_t a = 0; a < anchors.size() - 1; ++a) {
    size_t idx_start = anchors[a];
    size_t idx_end = anchors[a + 1];

    // If there are indices trapped between two valid record peaks, interpolate them
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

  // Step 3: Handle trailing dips (if data ends while dropping below the highest peak)
  size_t last_anchor = anchors.back();
  if (last_anchor < n - 1) {
    for (size_t i = last_anchor + 1; i < n; ++i) {
      (*_sample)[i] = _fv_values[last_anchor];
    }
  }
}
