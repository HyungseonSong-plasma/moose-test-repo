#pragma once

#include "ADMaterial.h"
#include "LinearInterpolation.h"
#include "MooseUtils.h"
#include "QPX.h"

/*
 *  Cross section for one species.
 */
class QPXInverseCrossSection : public ADMaterial
{
public:
  QPXInverseCrossSection(const InputParameters & parameters);

  static InputParameters validParams();

protected:
  virtual void computeQpProperties() override;

  /// True if interpolating transport coefficients as a function of the mean energy
  const bool _interp_cross_section;
  /// AD cross section
  ADMaterialProperty<Real> & _cross_section;
  const Real _cross_section_units;
  /// User defined cross section
  const Real _user_cross_section;
  const Real _threshold_energy;
  const Real _g1_g2;
  const Real _max_energy;
  /// Linear Interpolation fuction for cross-section
  LinearInterpolation _cross_section_interpolation;
};
