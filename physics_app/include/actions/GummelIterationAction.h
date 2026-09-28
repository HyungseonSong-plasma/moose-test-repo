#pragma once

#include "Action.h"

/**
 * Builds the electron <-> Poisson fixed-point coupling used by a Gummel
 * iteration.
 *
 * Preferred mode:
 *
 *   parent : orchestration-only or local heavy-particle physics
 *     |- electron MultiApp : solves n_e / mean_en and receives phi
 *     '- Poisson MultiApp  : solves phi and receives n_e
 *
 * The sibling MultiApps exchange their coupling fields directly with
 * MultiAppCopyTransfer. Optional parent-state mappings allow a heavy-particle
 * parent to provide gas/heavy state to either sibling and receive electron or
 * electrostatic state back. The Action does not construct any subsystem's
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
