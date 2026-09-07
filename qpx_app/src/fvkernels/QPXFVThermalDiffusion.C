#include "QPXFVThermalDiffusion.h"

registerMooseObject("qpxApp", QPXFVThermalDiffusion);

InputParameters
QPXFVThermalDiffusion::validParams()
{
  InputParameters params = FVFluxKernel::validParams();

  params.addClassDescription(
      "Heavy-species thermal diffusion flux: -D_T grad(T)/T.");

  params.addRequiredParam<MooseFunctorName>(
      "temperature",
      "Heavy-gas temperature T [K].");

  params.addRequiredParam<MooseFunctorName>(
      "thermal_diffusion_coefficient",
      "Multicomponent thermal diffusion coefficient D_T [kg/(m s)].");

  params.addParam<bool>(
      "include_thermal_diffusion",
      true,
      "Enable the thermal-diffusion contribution.");

  return params;
}

QPXFVThermalDiffusion::QPXFVThermalDiffusion(
    const InputParameters & parameters)
  : FVFluxKernel(parameters),
    _temperature(getFunctor<ADReal>("temperature")),
    _thermal_diffusion_coefficient(
        getFunctor<ADReal>("thermal_diffusion_coefficient")),
    _include_thermal_diffusion(
        getParam<bool>("include_thermal_diffusion"))
{
}

ADReal
QPXFVThermalDiffusion::computeQpResidual()
{
  using namespace Moose::FV;

  if (!_include_thermal_diffusion)
    return 0.0;

  const auto state = determineState();

  ADReal T_face;
  ADReal DT_face;
  ADReal dTdn;

  if (_var.isInternalFace(*_face_info))
  {
    // ------------------------------------------------------------------------
    // Temperature at face
    // ------------------------------------------------------------------------

    const ADReal T_elem =
        _temperature(elemArg(), state);

    const ADReal T_neighbor =
        _temperature(neighborArg(), state);

    interpolate(InterpMethod::Average,
                T_face,
                T_elem,
                T_neighbor,
                *_face_info,
                true);


    // ------------------------------------------------------------------------
    // Thermal diffusion coefficient at face
    // ------------------------------------------------------------------------

    const ADReal DT_elem =
        _thermal_diffusion_coefficient(elemArg(), state);

    const ADReal DT_neighbor =
        _thermal_diffusion_coefficient(neighborArg(), state);

    interpolate(InterpMethod::Average,
                DT_face,
                DT_elem,
                DT_neighbor,
                *_face_info,
                true);


    // ------------------------------------------------------------------------
    // grad(T) at face
    // ------------------------------------------------------------------------

    const auto grad_T_elem =
        _temperature.gradient(elemArg(), state);

    const auto grad_T_neighbor =
        _temperature.gradient(neighborArg(), state);

    ADRealVectorValue grad_T_face;

    interpolate(InterpMethod::Average,
                grad_T_face,
                grad_T_elem,
                grad_T_neighbor,
                *_face_info,
                true);

    dTdn = grad_T_face * normal();
  }
  else
  {
    const auto face = singleSidedFaceArg();

    T_face = _temperature(face, state);

    DT_face =
        _thermal_diffusion_coefficient(face, state);

    // Use adjacent-element gradient at the boundary
    const auto grad_T =
        _temperature.gradient(elemArg(), state);

    dTdn = grad_T * normal();
  }

  // --------------------------------------------------------------------------
  // Thermal diffusive mass flux normal to the face
  //
  //   j_T . n = -D_T/T * grad(T).n
  // --------------------------------------------------------------------------

  return -DT_face * dTdn / T_face;
}