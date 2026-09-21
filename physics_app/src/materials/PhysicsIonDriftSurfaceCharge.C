#include "PhysicsIonDriftSurfaceCharge.h"

registerADMooseObject("PhysicsApp", PhysicsIonDriftSurfaceCharge);

InputParameters
PhysicsIonDriftSurfaceCharge::validParams()
{
  InputParameters params = ADMaterial::validParams();
  params.addRequiredCoupledVar("coupled_variable0",
                               "All of the charged species that interact with this boundary.");
  params.addRequiredCoupledVar("coupled_variable1",
                               "All of the mobility of charged species that interact with this boundary.");
  params.addParam<std::string>("field_property_name",
                               "field_solver_interface_property",
                               "Name of the solver interface material property.");
  params.addClassDescription("");
  return params;
}

PhysicsIonDriftSurfaceCharge::PhysicsIonDriftSurfaceCharge(const InputParameters & parameters)
  : ADMaterial(parameters),
  _sigma(declareADProperty<Real>("surface_ion")),
  _sigma_old(getMaterialPropertyOld<Real>("surface_ion")),
  _electric_field(
      getADMaterialProperty<RealVectorValue>(getParam<std::string>("field_property_name"))),
  _a(0.5)
{

  _num_species = coupledComponents("coupled_variable0");

  unsigned int _num_mobility = coupledComponents("coupled_variable1");
  if (_num_species != _num_mobility)
    mooseError("Species number and mobility number are not the same!");

  // Resize the vectors to store _num_species pointers
  _species.resize(_num_species);
  _mu.resize(_num_species);
  _sgn.resize(_num_species);

  for (unsigned int i = 0; i < _num_species; ++i)
  {
    _species[i] = &adCoupledValue("coupled_variable0", i);
    _mu[i] = &coupledValue("coupled_variable1", i);
    _sgn[i] = &getMaterialProperty<Real>("sgn" + (*getVar("coupled_variable0", i)).name());
  }

  // Precalculate constant values
  _q_times_NA = PHYSICS_CONSTANTS::e * PHYSICS_CONSTANTS::N_A;
}

void
PhysicsIonDriftSurfaceCharge::initQpStatefulProperties()
{
  _sigma[_qp] = 0;
}

void
PhysicsIonDriftSurfaceCharge::computeQpProperties()
{
  if (_material_data_type == Moose::FACE_MATERIAL_DATA || boundaryRestricted())
  {
    using std::exp;
    
    ADReal charge_flux = 0.0;

    for (unsigned int i = 0; i < _num_species; ++i)
    {
      if (_normals[_qp] * (*_sgn[i])[_qp] * _electric_field[_qp] > 0.0)
      {
        _a = 1.0;
      }
      else
      {
        _a = 0.0;
      }

      charge_flux += _a * (*_sgn[i])[_qp] * (*_mu[i])[_qp] * _electric_field[_qp] 
                     * exp((*_species[i])[_qp]) * _normals[_qp];
    }

    _sigma[_qp] = _sigma_old[_qp] + charge_flux * _q_times_NA * _dt;
  }
  else
    _sigma[_qp] = 0.;
}
