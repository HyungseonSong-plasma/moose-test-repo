#pragma once

#include "GeneralVectorPostprocessor.h"
#include "VectorPostprocessorInterface.h"

/**
 *  Performs a filter-forward interpolation on the data contained in another VectorPostprocessor
 */

class FilterForwardInterpolate : public GeneralVectorPostprocessor
{
public:
  static InputParameters validParams();

  /**
   * Class constructor
   * @param parameters The input parameters
   */
  FilterForwardInterpolate(const InputParameters & parameters);

  /**
   * Initialize, clears old results
   */
  virtual void initialize() override;

  /**
   * Perform the least squares fit
   */
  virtual void execute() override;

protected:
  const std::string _fv_name;

  const VectorPostprocessorValue & _fv_values;

  ///@{ The variables used to write out samples of the filter
  VectorPostprocessorValue * _sample;
  ///@}
};
