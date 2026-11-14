#pragma once

#include "PlasmaInterface.h"

namespace Plasma
{
/** Generates the heavy-species NVMaterial from validated shared JSON only. */
class NVTransport : public PlasmaInterface
{
public:
  static InputParameters validParams();
  explicit NVTransport(const InputParameters & parameters);

private:
  void addFunctorMaterials() override;
};
} // namespace Plasma
