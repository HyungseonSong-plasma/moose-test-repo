#pragma once

#include "Action.h"

// Opt-in action for [Physics]/[Plasmas]/[Transport]/[DriftDiffusion].
// Reuses existing electron mean-energy, adjacent-sheath flux, and wall BC
// objects. Default plasma_boundary=none does not create a second owner.
class PlasmaDriftDiffusionBoundaryAction : public Action
{
public:
  static InputParameters validParams();
  explicit PlasmaDriftDiffusionBoundaryAction(const InputParameters & params);
  void act() override;
};
