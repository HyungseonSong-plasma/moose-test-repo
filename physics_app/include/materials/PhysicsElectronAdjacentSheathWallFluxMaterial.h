#pragma once

#include "ElectronWallFluxMaterial.h"

/**
 * Compatibility alias for historical Issue #395 inputs.
 * All wall flux physics is owned by ElectronWallFluxMaterial.C, not duplicated.
 * New inputs should set type = ElectronWallFluxMaterial.
 */
class PhysicsElectronAdjacentSheathWallFluxMaterial : public ElectronWallFluxMaterial
{
public:
  using ElectronWallFluxMaterial::ElectronWallFluxMaterial;
};
