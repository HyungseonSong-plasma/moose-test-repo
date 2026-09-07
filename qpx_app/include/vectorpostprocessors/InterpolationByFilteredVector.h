#pragma once

#include "GeneralVectorPostprocessor.h"
#include "VectorPostprocessorInterface.h"

/**
 *  Performs an interpolation on the data contained in another VectorPostprocessor
 *  based on the change marker vector
 */

class InterpolationByFilteredVector : public GeneralVectorPostprocessor
{
public:
  static InputParameters validParams();

  /**
   * Class constructor
   * @param parameters The input parameters
   */
  InterpolationByFilteredVector(const InputParameters & parameters);

  /**
   * Initialize, clears old results
   */
  virtual void initialize() override;

  /**
   * Perform the least squares fit
   */
  virtual void execute() override;

protected:
  const VectorPostprocessorValue & _fv_values;

  ///@{ The variables used to write out samples of the filter
  VectorPostprocessorValue * _sample;
  ///@}

  const VectorPostprocessorValue & _changeMarker;  // for column vector only
};
