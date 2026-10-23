#include "PhysicsFVLogMassFractionTransport.h"

#include "FEProblemBase.h"
#include "RelationshipManager.h"
#include "metaphysicl/raw_type.h"

registerMooseObject("PhysicsApp", PhysicsFVLogMassFractionTimeDerivative);
registerMooseObject("PhysicsApp", PhysicsFVLogMassFractionAdvection);
registerMooseObject("PhysicsApp", PhysicsFVLogMixtureAveragedDiffusion);
registerMooseObject("PhysicsApp", PhysicsFVLogMassFractionElectrostaticDrift);
registerMooseObject("PhysicsApp", PhysicsFVLogHeavyMassElectromigrationCorrection);

InputParameters
PhysicsFVLogMassFractionTimeDerivative::validParams()
{
  auto params = FVElementalKernel::validParams();
  params.addClassDescription(
      "Conservative backward-Euler heavy-species balance using a physical "
      "mass-fraction AD functor reconstructed from a logarithmic nonlinear coordinate.");
  params.addRequiredParam<MooseFunctorName>(
      "rho", "Mixture density rho [kg/m^3], evaluable at current and old states.");
  params.addRequiredParam<MooseFunctorName>(
      "mass_fraction",
      "Physical species mass fraction Y_k reconstructed from the log coordinate(s).");
  params.set<MultiMooseEnum>("vector_tags") = "time";
  params.set<MultiMooseEnum>("matrix_tags") = "system time";
  return params;
}

PhysicsFVLogMassFractionTimeDerivative::PhysicsFVLogMassFractionTimeDerivative(
    const InputParameters & parameters)
  : FVElementalKernel(parameters),
    _rho(getFunctor<ADReal>("rho")),
    _mass_fraction(getFunctor<ADReal>("mass_fraction"))
{
}

ADReal
PhysicsFVLogMassFractionTimeDerivative::computeQpResidual()
{
  if (!_subproblem.isTransient())
    mooseError("PhysicsFVLogMassFractionTimeDerivative requires transient execution.");
  if (_dt <= 0.0)
    mooseError("PhysicsFVLogMassFractionTimeDerivative requires dt > 0.");

  const auto elem = makeElemArg(_current_elem);
  const auto state = determineState();

  const ADReal rho = _rho(elem, state);
  const ADReal rho_old = _rho(elem, Moose::oldState());
  const ADReal Y = _mass_fraction(elem, state);
  const ADReal Y_old = _mass_fraction(elem, Moose::oldState());

  return (rho * Y - rho_old * Y_old) / _dt;
}

InputParameters
PhysicsFVLogMassFractionAdvection::validParams()
{
  auto params = INSFVScalarFieldAdvection::validParams();
  params.addClassDescription(
      "Density-weighted finite-volume advection of a reconstructed heavy-species "
      "mass fraction for a logarithmic residual variable.");
  params.addRequiredParam<MooseFunctorName>("rho", "Mixture density rho [kg/m^3].");
  params.addRequiredParam<MooseFunctorName>(
      "mass_fraction", "Physical species mass fraction Y_k.");
  return params;
}

PhysicsFVLogMassFractionAdvection::PhysicsFVLogMassFractionAdvection(
    const InputParameters & parameters)
  : INSFVScalarFieldAdvection(parameters),
    _rho(getFunctor<ADReal>("rho")),
    _mass_fraction(getFunctor<ADReal>("mass_fraction"))
{
}

ADReal
PhysicsFVLogMassFractionAdvection::computeQpResidual()
{
  const auto state = determineState();
  const auto & limiter_time =
      _subproblem.isTransient()
          ? Moose::StateArg(1, Moose::SolutionIterationType::Time)
          : Moose::StateArg(1, Moose::SolutionIterationType::Nonlinear);

  ADRealVectorValue advection_velocity;

  if (_add_slip_model)
  {
    Moose::FaceArg face_arg;

    if (onBoundary(*_face_info))
      face_arg = singleSidedFaceArg();
    else
      face_arg =
          Moose::FaceArg{_face_info,
                         Moose::FV::LimiterType::CentralDifference,
                         true,
                         false,
                         nullptr,
                         &limiter_time};

    ADRealVectorValue slip_velocity;

    if (_dim >= 1)
      slip_velocity(0) = (*_u_slip)(face_arg, state);
    if (_dim >= 2)
      slip_velocity(1) = (*_v_slip)(face_arg, state);
    if (_dim >= 3)
      slip_velocity(2) = (*_w_slip)(face_arg, state);

    advection_velocity += slip_velocity;
  }

  const auto v = velocity();
  advection_velocity += v;

  const auto face_arg =
      makeFace(*_face_info,
               limiterType(_advected_interp_method),
               MetaPhysicL::raw_value(v) * _normal > 0,
               false,
               &limiter_time);

  const ADReal Y_face = _mass_fraction(face_arg, state);
  const ADReal rho_face = _rho(face_arg, state);

  return rho_face * (_normal * advection_velocity) * Y_face;
}

InputParameters
PhysicsFVLogMixtureAveragedDiffusion::validParams()
{
  auto params = FVFluxKernel::validParams();

  params.addClassDescription(
      "Mixture-averaged heavy-species diffusion using a physical mass-fraction "
      "AD functor reconstructed from logarithmic nonlinear coordinates.");

  params.addRequiredParam<MooseFunctorName>("rho", "Mixture density [kg/m^3].");
  params.addRequiredParam<MooseFunctorName>(
      "mass_fraction", "Physical species mass fraction Y_k.");
  params.addRequiredParam<MooseFunctorName>(
      "diffusivity", "Mixture-averaged species diffusion coefficient D_km [m^2/s].");
  params.addRequiredParam<MooseFunctorName>(
      "mean_molar_mass", "Mixture mean molar mass Mn [kg/mol].");

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

PhysicsFVLogMixtureAveragedDiffusion::PhysicsFVLogMixtureAveragedDiffusion(
    const InputParameters & parameters)
  : FVFluxKernel(parameters),
    _rho(getFunctor<ADReal>("rho")),
    _mass_fraction(getFunctor<ADReal>("mass_fraction")),
    _diffusivity(getFunctor<ADReal>("diffusivity")),
    _mean_molar_mass(getFunctor<ADReal>("mean_molar_mass")),
    _coeff_interp_method(
        Moose::FV::selectInterpolationMethod(getParam<MooseEnum>("coeff_interp_method"))),
    _include_molar_mass_gradient(getParam<bool>("include_molar_mass_gradient"))
{
}

ADReal
PhysicsFVLogMixtureAveragedDiffusion::computeQpResidual()
{
  using namespace Moose::FV;

  const auto state = determineState();

  ADReal coeff;
  ADReal Y_face;
  ADReal dYdn;
  ADReal Mn_face;
  ADReal dMndn;

  if (_var.isInternalFace(*_face_info))
  {
    const ADReal rho_elem = _rho(elemArg(), state);
    const ADReal rho_neighbor = _rho(neighborArg(), state);
    const ADReal D_elem = _diffusivity(elemArg(), state);
    const ADReal D_neighbor = _diffusivity(neighborArg(), state);

    const ADReal coeff_elem = rho_elem * D_elem;
    const ADReal coeff_neighbor = rho_neighbor * D_neighbor;

    if (!coeff_elem.value() && !coeff_neighbor.value())
      return 0.0;

    interpolate(_coeff_interp_method,
                coeff,
                coeff_elem,
                coeff_neighbor,
                *_face_info,
                true);

    const ADReal Y_elem = _mass_fraction(elemArg(), state);
    const ADReal Y_neighbor = _mass_fraction(neighborArg(), state);

    interpolate(InterpMethod::Average,
                Y_face,
                Y_elem,
                Y_neighbor,
                *_face_info,
                true);

    dYdn = (Y_neighbor - Y_elem) / _face_info->dCNMag();

    const ADReal Mn_elem = _mean_molar_mass(elemArg(), state);
    const ADReal Mn_neighbor = _mean_molar_mass(neighborArg(), state);

    interpolate(InterpMethod::Average,
                Mn_face,
                Mn_elem,
                Mn_neighbor,
                *_face_info,
                true);

    const auto grad_Mn_elem = _mean_molar_mass.gradient(elemArg(), state);
    const auto grad_Mn_neighbor = _mean_molar_mass.gradient(neighborArg(), state);

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

    coeff = _rho(face, state) * _diffusivity(face, state);
    Y_face = _mass_fraction(face, state);
    dYdn = _mass_fraction.gradient(face, state) * normal();

    Mn_face = _mean_molar_mass(face, state);
    dMndn = _mean_molar_mass.gradient(face, state) * normal();
  }

  if (_include_molar_mass_gradient)
    return -coeff * (dYdn + (Y_face / Mn_face) * dMndn);

  return -coeff * dYdn;
}

InputParameters
PhysicsFVLogMassFractionElectrostaticDrift::validParams()
{
  auto params = FVFluxKernel::validParams();

  params.addClassDescription(
      "Electrostatic heavy-species drift using a reconstructed physical mass fraction.");

  params.addRequiredParam<MooseFunctorName>(
      "mass_fraction", "Physical species mass fraction Y_k.");
  params.addRequiredParam<MooseFunctorName>("potential", "Electrostatic potential phi [V].");
  params.addRequiredParam<MooseFunctorName>(
      "mobility", "Positive species mobility magnitude [m^2/(V s)].");
  params.addRequiredParam<MooseFunctorName>(
      "carrier",
      "Multiplicative carrier/conversion functor; use rho for a heavy mass-fraction equation.");
  params.addRequiredParam<Real>("charge_number", "Signed charge number z.");

  params += Moose::FV::advectedInterpolationParameter();

  params.addRelationshipManager(
      "ElementSideNeighborLayers",
      Moose::RelationshipManagerType::GEOMETRIC |
          Moose::RelationshipManagerType::ALGEBRAIC |
          Moose::RelationshipManagerType::COUPLING,
      [](const InputParameters & obj_params, InputParameters & rm_params)
      { FVRelationshipManagerInterface::setRMParamsAdvection(obj_params, rm_params, 2); });

  return params;
}

PhysicsFVLogMassFractionElectrostaticDrift::PhysicsFVLogMassFractionElectrostaticDrift(
    const InputParameters & parameters)
  : FVFluxKernel(parameters),
    _mass_fraction(getFunctor<ADReal>("mass_fraction")),
    _potential(getFunctor<ADReal>("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
    _carrier(getFunctor<ADReal>("carrier")),
    _charge_number(getParam<Real>("charge_number"))
{
  if (_charge_number == 0.0)
    paramError("charge_number", "Electrostatic drift requires nonzero charge_number.");

  const bool need_more_ghosting =
      Moose::FV::setInterpolationMethod(*this, _advected_interp_method, "advected_interp_method");

  if (need_more_ghosting && _tid == 0)
    getCheckedPointerParam<FEProblemBase *>("_fe_problem_base")
        ->setErrorOnJacobianNonzeroReallocation(false);
}

ADReal
PhysicsFVLogMassFractionElectrostaticDrift::computeQpResidual()
{
  const auto state = determineState();
  const auto & limiter_time =
      _subproblem.isTransient()
          ? Moose::StateArg(1, Moose::SolutionIterationType::Time)
          : Moose::StateArg(1, Moose::SolutionIterationType::Nonlinear);

  const auto centered_face =
      makeFace(*_face_info,
               Moose::FV::LimiterType::CentralDifference,
               true,
               false,
               &limiter_time);

  const ADRealVectorValue electric_field = -_potential.gradient(centered_face, state);
  const ADReal mobility_face = _mobility(centered_face, state);
  const ADReal carrier_face = _carrier(centered_face, state);

  const ADReal drift_normal =
      _charge_number * mobility_face * (electric_field * _normal);

  const bool elem_is_upwind = MetaPhysicL::raw_value(drift_normal) >= 0.0;

  const auto transported_face =
      makeFace(*_face_info,
               Moose::FV::limiterType(_advected_interp_method),
               elem_is_upwind,
               false,
               &limiter_time);

  const ADReal Y_face = _mass_fraction(transported_face, state);

  return carrier_face * Y_face * drift_normal;
}

InputParameters
PhysicsFVLogHeavyMassElectromigrationCorrection::validParams()
{
  auto params = FVFluxKernel::validParams();

  params.addClassDescription(
      "Conservative zero-net-heavy-mass electromigration correction for a "
      "log-coordinate residual row.");

  params.addRequiredParam<MooseFunctorName>("potential", "Electrostatic potential phi [V].");
  params.addRequiredParam<MooseFunctorName>("rho", "Heavy-mixture density rho [kg/m^3].");
  params.addRequiredParam<MooseFunctorName>(
      "mass_fraction",
      "Physical mass fraction Y_k for the species owning this residual row.");

  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "ion_mass_fractions",
      "Physical charged-heavy mass-fraction functors.");
  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "ion_mobilities",
      "Positive charged-heavy mobility functors [m^2/(V s)].");
  params.addRequiredParam<std::vector<Real>>(
      "ion_charges",
      "Signed charge numbers z_i corresponding to ion_mass_fractions.");

  params += Moose::FV::advectedInterpolationParameter();

  params.addRelationshipManager(
      "ElementSideNeighborLayers",
      Moose::RelationshipManagerType::GEOMETRIC |
          Moose::RelationshipManagerType::ALGEBRAIC |
          Moose::RelationshipManagerType::COUPLING,
      [](const InputParameters & obj_params, InputParameters & rm_params)
      { FVRelationshipManagerInterface::setRMParamsAdvection(obj_params, rm_params, 2); });

  return params;
}

PhysicsFVLogHeavyMassElectromigrationCorrection::
    PhysicsFVLogHeavyMassElectromigrationCorrection(const InputParameters & parameters)
  : FVFluxKernel(parameters),
    _potential(getFunctor<ADReal>("potential")),
    _rho(getFunctor<ADReal>("rho")),
    _species_mass_fraction(getFunctor<ADReal>("mass_fraction")),
    _ion_mass_fraction_names(
        getParam<std::vector<MooseFunctorName>>("ion_mass_fractions")),
    _ion_mobility_names(
        getParam<std::vector<MooseFunctorName>>("ion_mobilities")),
    _ion_charges(getParam<std::vector<Real>>("ion_charges"))
{
  const auto n = _ion_mass_fraction_names.size();

  if (n == 0)
    paramError("ion_mass_fractions", "At least one charged-heavy species is required.");

  if (_ion_mobility_names.size() != n || _ion_charges.size() != n)
    mooseError(
        "PhysicsFVLogHeavyMassElectromigrationCorrection: ion_mass_fractions, "
        "ion_mobilities, and ion_charges must have the same length.");

  _ion_mass_fractions.reserve(n);
  _ion_mobilities.reserve(n);

  for (std::size_t i = 0; i < n; ++i)
  {
    if (_ion_charges[i] == 0.0)
      mooseError(
          "PhysicsFVLogHeavyMassElectromigrationCorrection: ion_charges must be nonzero.");

    _ion_mass_fractions.push_back(
        &getFunctorByName<ADReal>(_ion_mass_fraction_names[i]));
    _ion_mobilities.push_back(
        &getFunctorByName<ADReal>(_ion_mobility_names[i]));
  }

  const bool need_more_ghosting =
      Moose::FV::setInterpolationMethod(*this, _advected_interp_method, "advected_interp_method");

  if (need_more_ghosting && _tid == 0)
    getCheckedPointerParam<FEProblemBase *>("_fe_problem_base")
        ->setErrorOnJacobianNonzeroReallocation(false);
}

ADReal
PhysicsFVLogHeavyMassElectromigrationCorrection::computeQpResidual()
{
  const auto state = determineState();
  const auto & limiter_time =
      _subproblem.isTransient()
          ? Moose::StateArg(1, Moose::SolutionIterationType::Time)
          : Moose::StateArg(1, Moose::SolutionIterationType::Nonlinear);

  const auto centered_face =
      makeFace(*_face_info,
               Moose::FV::LimiterType::CentralDifference,
               true,
               false,
               &limiter_time);

  const ADRealVectorValue electric_field = -_potential.gradient(centered_face, state);
  const ADReal rho_face = _rho(centered_face, state);

  ADReal direct_mass_flux_normal = 0.0;

  for (std::size_t i = 0; i < _ion_mass_fractions.size(); ++i)
  {
    const ADReal mobility_face = (*_ion_mobilities[i])(centered_face, state);

    const ADReal drift_normal =
        _ion_charges[i] * mobility_face * (electric_field * _normal);

    const bool elem_is_upwind = MetaPhysicL::raw_value(drift_normal) >= 0.0;

    const auto ion_face =
        makeFace(*_face_info,
                 Moose::FV::limiterType(_advected_interp_method),
                 elem_is_upwind,
                 false,
                 &limiter_time);

    const ADReal ion_Y_face = (*_ion_mass_fractions[i])(ion_face, state);

    direct_mass_flux_normal += rho_face * ion_Y_face * drift_normal;
  }

  const ADReal correction_mass_flux_normal = -direct_mass_flux_normal;

  const bool elem_is_upwind =
      MetaPhysicL::raw_value(correction_mass_flux_normal) >= 0.0;

  const auto species_face =
      makeFace(*_face_info,
               Moose::FV::limiterType(_advected_interp_method),
               elem_is_upwind,
               false,
               &limiter_time);

  const ADReal species_Y_face = _species_mass_fraction(species_face, state);

  return species_Y_face * correction_mass_flux_normal;
}
