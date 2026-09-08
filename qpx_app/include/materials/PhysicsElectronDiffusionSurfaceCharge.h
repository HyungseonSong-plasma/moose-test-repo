#pragma once

#include "ADMaterial.h"
#include "DerivativeMaterialPropertyNameInterface.h"
#include "MooseUtils.h"
#include "Physics.h"

/**
 *  Adds a surface charge material property based on the rate of change of the total charged
 *  flux to a boundary. (NOTE: this material is meant to be boundary-restricted.)
 */
class PhysicsElectronDiffusionSurfaceCharge : public ADMaterial, public DerivativeMaterialPropertyNameInterface
{
public:
  static InputParameters validParams();
  PhysicsElectronDiffusionSurfaceCharge(const InputParameters & parameters);

protected:
  virtual void computeQpProperties() override;
  virtual void initQpStatefulProperties() override;

  /// Surface charge value
  ADMaterialProperty<Real> & _sigma;
  /// Surface charge value during previous time step
  const MaterialProperty<Real> & _sigma_old;
  const ADVariableValue & _mean_en;
  const ADVariableValue & _e;
  /// The electric field provided as a material property
  const MaterialProperty<Real> & _mass;
  /// Elementary charge times Avogadro's number
  Real _q_times_NA;
};
