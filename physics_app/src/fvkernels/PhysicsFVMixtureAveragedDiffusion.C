#include "PhysicsFVMixtureAveragedDiffusion.h"

registerMooseObject("PhysicsApp", PhysicsFVMixtureAveragedDiffusion);

InputParameters
PhysicsFVMixtureAveragedDiffusion::validParams()
{
  InputParameters params = FVFluxKernel::validParams();

  params.addClassDescription(
      "Computes the mixture-averaged heavy-species diffusion flux.");

  params.addRequiredParam<MooseFunctorName>(
      "rho",
      "Mixture density [kg/m^3].");

  params.addRequiredParam<MooseFunctorName>(
      "diffusivity",
      "Mixture-averaged species diffusion coefficient D_km [m^2/s].");

  params.addRequiredParam<MooseFunctorName>(
      "mean_molar_mass",
      "Mixture mean molar mass Mn [kg/mol].");
  
  params.addParam<MooseEnum>(
      "coeff_interp_method",
      MooseEnum("average harmonic", "average"),
      "Interpolation method for rho*D at internal faces.");
  
   params.addParam<bool>(
      "include_molar_mass_gradient",
      true,
      "Include the mean-molar-mass-gradient correction term.");

  return params;
}

PhysicsFVMixtureAveragedDiffusion::PhysicsFVMixtureAveragedDiffusion(
    const InputParameters & parameters)
  : FVFluxKernel(parameters),
    _rho(getFunctor<ADReal>("rho")),
    _diffusivity(getFunctor<ADReal>("diffusivity")),
    _mean_molar_mass(getFunctor<ADReal>("mean_molar_mass")),
    _coeff_interp_method(
        Moose::FV::selectInterpolationMethod(
            getParam<MooseEnum>("coeff_interp_method"))),
    _include_molar_mass_gradient(
        getParam<bool>("include_molar_mass_gradient"))
{
}

ADReal
PhysicsFVMixtureAveragedDiffusion::computeQpResidual()
{
  using namespace Moose::FV;

  const auto state = determineState();

  const auto dwdn = gradUDotNormal(state, false);
  
  ADReal coeff;
  ADReal w_face;
  ADReal Mn_face;
  ADReal dMndn;

  // rho * D at internal face
  if (_var.isInternalFace(*_face_info))
  {
    // ------------------------------------------------------------
    // Interpolate rho * D
    // ------------------------------------------------------------

    const ADReal rho_elem = _rho(elemArg(), state);
    const ADReal rho_neighbor = _rho(neighborArg(), state);

    const ADReal D_elem = _diffusivity(elemArg(), state);
    const ADReal D_neighbor = _diffusivity(neighborArg(), state);

    const ADReal coeff_elem = rho_elem * D_elem;
    const ADReal coeff_neighbor = rho_neighbor * D_neighbor;

    if (!coeff_elem.value() && !coeff_neighbor.value())
      return 0;

    interpolate(_coeff_interp_method,
                coeff,
                coeff_elem,
                coeff_neighbor,
                *_face_info,
                true);

    // ------------------------------------------------------------
    // Interpolate species mass fraction w_k
    // ------------------------------------------------------------
    
    const ADReal w_elem = _var(elemArg(), state);
    const ADReal w_neighbor = _var(neighborArg(), state);

    interpolate(InterpMethod::Average,
                w_face,
                w_elem,
                w_neighbor,
                *_face_info,
                true);

    // ------------------------------------------------------------
    // Interpolate mean molar mass Mn
    // ------------------------------------------------------------

    const ADReal Mn_elem =
        _mean_molar_mass(elemArg(), state);

    const ADReal Mn_neighbor =
        _mean_molar_mass(neighborArg(), state);

    interpolate(InterpMethod::Average,
                Mn_face,
                Mn_elem,
                Mn_neighbor,
                *_face_info,
                true);

    // ------------------------------------------------------------
    // Face-normal gradient of Mn
    //
    // We need:
    //
    //   grad(Mn) . n
    //
    // ------------------------------------------------------------

    const auto elem_arg = elemArg();
    const auto neighbor_arg = neighborArg();

    const auto grad_Mn_elem =
        _mean_molar_mass.gradient(elem_arg, state);

    const auto grad_Mn_neighbor =
        _mean_molar_mass.gradient(neighbor_arg, state);

    ADRealVectorValue grad_Mn_face;

    interpolate(InterpMethod::Average,
                grad_Mn_face,
                grad_Mn_elem,
                grad_Mn_neighbor,
                *_face_info,
                true);

    dMndn = grad_Mn_face * normal();
  }
  else
  {
    const auto face = singleSidedFaceArg();

    coeff =
        _rho(face, state) *
        _diffusivity(face, state);

    w_face = _var(face, state);
    Mn_face = _mean_molar_mass(face, state);

    const auto grad_Mn =
        _mean_molar_mass.gradient(face, state);

    dMndn = grad_Mn * normal();
  }
  
  if (_include_molar_mass_gradient)
    return -1.0 *
        coeff *
        (dwdn + (w_face / Mn_face) * dMndn);
  
  return -1.0 * coeff * dwdn;
}