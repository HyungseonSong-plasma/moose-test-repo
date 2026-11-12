#pragma once

#include "Action.h"
#include "PlasmaMechanism.h"

/** One mechanism owner per FEProblem. Child Physics read this validated catalogue. */
class PlasmaMechanismAction : public Action
{
public:
  static InputParameters validParams();
  explicit PlasmaMechanismAction(const InputParameters & params);
  void act() override {}

  const Plasma::PlasmaMechanism & mechanism() const { return _mechanism; }

private:
  const Plasma::PlasmaMechanism _mechanism;
};
