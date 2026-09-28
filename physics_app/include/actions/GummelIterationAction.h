#pragma once

#include "Action.h"

/**
 * Builds the electron <-> Poisson fixed-point coupling used by a Gummel
 * iteration.
 *
 * Preferred mode:
 *
 *   parent
 *     |- electron MultiApp : solves n_e / mean_en and receives phi
 *     '- Poisson MultiApp  : solves phi and receives n_e
 *
 * The sibling MultiApps exchange their coupling fields directly with
 * MultiAppCopyTransfer.  The Action does not construct either subsystem's
 * equations; each input file owns its local physics.
 *
 * Legacy mode, where the current application owns the electron equations and
 * only Poisson is a MultiApp, remains supported when electron_input_file is
 * omitted.
 */
class GummelIterationAction : public Action
{
public:
  static InputParameters validParams();
  GummelIterationAction(const InputParameters & parameters);

  void act() override;

private:
  bool usesElectronSubApp() const;
  void checkVariableMaps() const;
};
