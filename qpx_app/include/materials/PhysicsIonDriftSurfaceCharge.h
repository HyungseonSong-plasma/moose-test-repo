#pragma once

#include "ADMaterial.h"
#include "DerivativeMaterialPropertyNameInterface.h"
#include "MooseUtils.h"
#include "Physics.h"

/**
 *  Adds a surface charge material property based on the rate of change of the total charged
 *  flux to a boundary. (NOTE: this material is meant to be boundary-restricted.)
 */
class PhysicsIonDriftSurfaceCharge : public ADMaterial, public DerivativeMaterialPropertyNameInterface
{
public:
  static InputParameters validParams();
  PhysicsIonDriftSurfaceCharge(const InputParameters & parameters);

protected:
  virtual void computeQpProperties() override;
  virtual void initQpStatefulProperties() override;

  /// Surface charge value
  ADMaterialProperty<Real> & _sigma;
  /// Surface charge value during previous time step
  const MaterialProperty<Real> & _sigma_old;
  /// The electric field provided as a material property
  const ADMaterialProperty<RealVectorValue> & _electric_field;

  /// Number of charged species
  unsigned int _num_species;
  /// Charged species variables
  std::vector<const ADVariableValue *> _species;
  /// Mobility coefficient
  std::vector<const VariableValue *> _mu;
  /// Charge sign of the coupled species
  std::vector<const MaterialProperty<Real> *> _sgn;
  /// Elementary charge times Avogadro's number
  Real _q_times_NA;
  Real _a;
};
