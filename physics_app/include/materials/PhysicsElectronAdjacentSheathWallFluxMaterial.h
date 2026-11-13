#pragma once

#include "ESWallFluxMaterial.h"

/**
 * Historical Issue #395 name retained for archived recipe inputs.
 * This compatibility class has NO separate constitutive law.
 * New inputs should use ESWallFluxMaterial.
 */
class PhysicsElectronAdjacentSheathWallFluxMaterial : public ESWallFluxMaterial
{
public:
  using ESWallFluxMaterial::ESWallFluxMaterial;
};
