#pragma once

#include "FVDiffusion.h"

#include <vector>

/** Diagnostic-only wrapper around framework FVDiffusion for Issue #228. */
class PhysicsFVDiffusionDiagnostic : public FVDiffusion
{
public:
  static InputParameters validParams();
  PhysicsFVDiffusionDiagnostic(const InputParameters & params);

protected:
  ADReal computeQpResidual() override;
  bool probeFace() const;

  const std::vector<unsigned int> _diagnostic_element_ids;
  const bool _diagnostic_boundary_faces;
};