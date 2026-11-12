#pragma once

#include "Action.h"
#include "Chemistry.h"

/** One mechanism owner per FEProblem. Child Physics read this validated catalogue. */
class ChemistryAction : public Action
{
public:
  static InputParameters validParams();
  explicit ChemistryAction(const InputParameters & params);
  void act() override {}

  const Plasma::ChemistryData & data() const { return _data; }

private:
  const Plasma::ChemistryData _data;
};
