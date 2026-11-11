#pragma once

#include "PlasmaInterface.h"

namespace Plasma
{

/**
 * Validates plasma species and their resolved solver variables.
 *
 * Generates supported FEM drift-diffusion kernels; FV kernels remain external.
 * Shares species and duplicate-operator checks with other plasma Physics.
 */
class ContinuityEq : public PlasmaInterface
{
public:
  static InputParameters validParams();
  explicit ContinuityEq(const InputParameters & parameters);

private:
  void checkIntegrity() const override;
  void addFEKernels() override;
};

}
