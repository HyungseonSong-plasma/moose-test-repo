#pragma once

#include "ESWallFluxMaterial.h"

/**
 * Compatibility name introduced in Issue #402. The only sheath-limited
 * electron wall law lives in ESWallFluxMaterial.C.
 *
 * New input files should set type = ESWallFluxMaterial.
 */
class ElectronWallFluxMaterial : public ESWallFluxMaterial
{
public:
  using ESWallFluxMaterial::ESWallFluxMaterial;
};
