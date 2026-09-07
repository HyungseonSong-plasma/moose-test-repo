#include "QPXElectronWallFluxMaterial.h"
#include "QPX.h"
#include "QPXElectronWallPhysics.h"

#include <cmath>

registerMooseObject("qpxApp", QPXElectronWallFluxMaterial);

InputParameters
QPXElectronWallFluxMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Provides a verification-stage absorbing electron wall number flux from "
      "mean electron energy and electron number density.");

  params.addRequiredParam<MooseFunctorName>(
      "electron_density", "Electron number density n_e [1/m^3].");

  params.addRequiredParam<MooseFunctorName>(
      "mean_energy", "Mean electron energy [eV].");

  params.addParam<Real>(
      "sticking",
      1.0,
      "Electron wall absorption probability used in this verification stage.");

  return params;
}

QPXElectronWallFluxMaterial::QPXElectronWallFluxMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _mean_energy(getFunctor<ADReal>("mean_energy")),
    _sticking(getParam<Real>("sticking"))
{
  if (_sticking < 0.0 || _sticking > 1.0)
    paramError("sticking", "Electron sticking must be in [0,1].");

  addFunctorProperty<ADReal>(
      "electron_mean_speed",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal eps_bar = _mean_energy(r, state);

        if (eps_bar.value() <= 0.0)
          mooseError("QPXElectronWallFluxMaterial requires mean_energy > 0 eV.");

        return QPXElectronWallPhysics::meanSpeed(eps_bar);
      });

  addFunctorProperty<ADReal>(
      "electron_wall_number_flux",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal eps_bar = _mean_energy(r, state);

        return QPXElectronWallPhysics::absorbingNumberFlux(
            _electron_density(r, state), eps_bar, _sticking);
      });
}
