#pragma once

#include "ADMaterial.h"
#include "SplineInterpolation.h"

/*
 *  Material properties of electrons and universal constants
 */
class QPXElectronTransportCoefficients : public ADMaterial
{
public:
  QPXElectronTransportCoefficients(const InputParameters & parameters);

  static InputParameters validParams();

protected:
  virtual void computeQpProperties() override;

  /// Spline Interpolation fuction for electron mobility coefficient
  SplineInterpolation _mu_interpolation;
  /// Spline Interpolation fuction for diffusion mobility coefficient
  SplineInterpolation _diff_interpolation;

  /// True if interpolating transport coefficients as a function of the mean energy
  const bool _interp_trans_coeffs;
  /// True if ramping the non-linearity of coming from the electron energy dependence of the transport coefficients
  const bool _ramp_trans_coeffs;
  /// Scaling units for the potential (V or kV)
  const std::string _potential_units;
  /// Scaling value for the potential
  Real _voltage_scaling;

  /// Time units
  const Real _time_units;

  /// Coupled background gas temperature variable
  const VariableValue & _T_gas;
  /// Coupled background gas pressure variable
  const VariableValue & _p_gas;
  /// True if molar density is used
  const bool _use_moles;

  /// User defined electron mobility coefficient
  const Real _user_muem;
  /// User defined electron diffusion coefficient
  const Real _user_diffem;
  /// True is electron transport coefficients are pressure dependent
  const bool _pressure_dependent;

  /// AD electron mobility coefficient
  ADMaterialProperty<Real> & _muem;
  /// AD electron diffusion coefficient
  ADMaterialProperty<Real> & _diffem;
  /// AD electron energy mobility coefficient
  ADMaterialProperty<Real> & _mumean_en;
  /// AD electron energy diffusion coefficient
  ADMaterialProperty<Real> & _diffmean_en;
  /// Mass of electrons
  MaterialProperty<Real> & _massem;

  /// Charge sign of electrons
  MaterialProperty<Real> & _sgnem;
  /// Charge sign of electron energy density
  MaterialProperty<Real> & _sgnmean_en;

  /// Coupled electron density
  const ADVariableValue & _em;
  /// Coupled electron energy density
  const ADVariableValue & _mean_en;

  /// True is property_file containing a single header line
  const bool _header;
};
