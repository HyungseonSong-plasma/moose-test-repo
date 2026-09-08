#pragma once

#include "GeneralVectorPostprocessor.h"
#include "VectorPostprocessorInterface.h"

/**
 *  Create a change marker vector by comparing original VectorPostprocessor to changed VectorPostprocessor
 */

class CreateChangeMarker : public GeneralVectorPostprocessor
{
public:
  static InputParameters validParams();

  /**
   * Class constructor
   * @param parameters The input parameters
   */
  CreateChangeMarker(const InputParameters & parameters);

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
  const VectorPostprocessorValue & _ov_values;

  // Change marker
  VectorPostprocessorValue * _changeMarker;
};
