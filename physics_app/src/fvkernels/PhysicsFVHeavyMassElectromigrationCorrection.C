#include "PhysicsFVHeavyMassElectromigrationCorrection.h"

#include "FEProblemBase.h"
#include "RelationshipManager.h"
#include "metaphysicl/raw_type.h"

registerMooseObject("PhysicsApp", PhysicsFVHeavyMassElectromigrationCorrection);

InputParameters
PhysicsFVHeavyMassElectromigrationCorrection::validParams()
{
  auto params = FVFluxKernel::validParams();

  params.addClassDescription(
      "Adds the conservative heavy mass-average electromigration correction "
      "to one heavy-species mass-fraction equation.");

  params.addRequiredParam<MooseFunctorName>(
      "potential",
      "Electrostatic potential phi [V].");

  params.addRequiredParam<MooseFunctorName>(
      "rho",
      "Heavy-mixture mass density rho [kg/m^3].");

  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "ion_mass_fractions",
      "Charged-heavy mass-fraction functors used to reconstruct the "
      "provisional direct migration mass flux.");

  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "ion_mobilities",
      "Positive charged-heavy mobility functors [m^2/(V s)], in the same "
      "order as ion_mass_fractions.");

  params.addRequiredParam<std::vector<Real>>(
      "ion_charges",
      "Signed charge numbers z_i, in the same order as ion_mass_fractions.");

  params += Moose::FV::advectedInterpolationParameter();

  params.addRelationshipManager(
      "ElementSideNeighborLayers",
      Moose::RelationshipManagerType::GEOMETRIC |
          Moose::RelationshipManagerType::ALGEBRAIC |
          Moose::RelationshipManagerType::COUPLING,
      [](const InputParameters & obj_params, InputParameters & rm_params)
      {
        FVRelationshipManagerInterface::setRMParamsAdvection(
            obj_params, rm_params, 2);
      });

  return params;
}

PhysicsFVHeavyMassElectromigrationCorrection::
    PhysicsFVHeavyMassElectromigrationCorrection(
        const InputParameters & parameters)
  : FVFluxKernel(parameters),
    _potential(getFunctor<ADReal>("potential")),
    _rho(getFunctor<ADReal>("rho")),
    _ion_mass_fraction_names(
        getParam<std::vector<MooseFunctorName>>("ion_mass_fractions")),
    _ion_mobility_names(
        getParam<std::vector<MooseFunctorName>>("ion_mobilities")),
    _ion_charges(getParam<std::vector<Real>>("ion_charges"))
{
  const auto n = _ion_mass_fraction_names.size();

  if (n == 0)
    paramError(
        "ion_mass_fractions",
        "At least one charged-heavy species is required.");

  if (_ion_mobility_names.size() != n || _ion_charges.size() != n)
    mooseError(
        "PhysicsFVHeavyMassElectromigrationCorrection: ion_mass_fractions, "
        "ion_mobilities, and ion_charges must have the same length.");

  _ion_mass_fractions.reserve(n);
  _ion_mobilities.reserve(n);

  for (std::size_t i = 0; i < n; ++i)
  {
    if (_ion_charges[i] == 0.0)
      mooseError(
          "PhysicsFVHeavyMassElectromigrationCorrection: ion_charges must be "
          "nonzero for every listed charged-heavy species.");

    _ion_mass_fractions.push_back(
        &getFunctorByName<ADReal>(_ion_mass_fraction_names[i]));

    _ion_mobilities.push_back(
        &getFunctorByName<ADReal>(_ion_mobility_names[i]));
  }

  const bool need_more_ghosting =
      Moose::FV::setInterpolationMethod(
          *this, _advected_interp_method, "advected_interp_method");

  if (need_more_ghosting && _tid == 0)
    getCheckedPointerParam<FEProblemBase *>("_fe_problem_base")
        ->setErrorOnJacobianNonzeroReallocation(false);
}

ADReal
PhysicsFVHeavyMassElectromigrationCorrection::computeQpResidual()
{
  const auto state = determineState();

  const auto & limiter_time =
      _subproblem.isTransient()
          ? Moose::StateArg(1, Moose::SolutionIterationType::Time)
          : Moose::StateArg(1, Moose::SolutionIterationType::Nonlinear);

  // Use the same centered electrostatic/carrier evaluation as
  // PhysicsFVElectrostaticDrift.
  const auto centered_face =
      makeFace(*_face_info,
               Moose::FV::LimiterType::CentralDifference,
               true,
               false,
               &limiter_time);

  const ADRealVectorValue electric_field =
      -_potential.gradient(centered_face, state);

  const ADReal rho_face = _rho(centered_face, state);

  // Reconstruct the exact provisional direct charged-heavy mass flux normal
  // used by the individual electrostatic-drift kernels.
  ADReal direct_mass_flux_normal = 0.0;

  for (std::size_t i = 0; i < _ion_mass_fractions.size(); ++i)
  {
    const ADReal mobility_face =
        (*_ion_mobilities[i])(centered_face, state);

    const ADReal drift_normal =
        _ion_charges[i] *
        mobility_face *
        (electric_field * _normal);

    const bool elem_is_upwind =
        MetaPhysicL::raw_value(drift_normal) >= 0.0;

    const auto ion_face =
        makeFace(*_face_info,
                 Moose::FV::limiterType(_advected_interp_method),
                 elem_is_upwind,
                 false,
                 &limiter_time);

    const ADReal ion_mass_fraction_face =
        (*_ion_mass_fractions[i])(ion_face, state);

    direct_mass_flux_normal +=
        rho_face *
        ion_mass_fraction_face *
        drift_normal;
  }

  // The correction is the negative of the provisional total charged-heavy
  // migration mass flux. All heavy species see the same correction direction.
  const ADReal correction_mass_flux_normal =
      -direct_mass_flux_normal;

  const bool elem_is_correction_upwind =
      MetaPhysicL::raw_value(correction_mass_flux_normal) >= 0.0;

  const auto correction_face =
      makeFace(*_face_info,
               Moose::FV::limiterType(_advected_interp_method),
               elem_is_correction_upwind,
               false,
               &limiter_time);

  const ADReal species_mass_fraction_face =
      _var(correction_face, state);

  return species_mass_fraction_face *
         correction_mass_flux_normal;
}
