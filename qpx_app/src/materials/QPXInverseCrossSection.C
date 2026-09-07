#include "QPXInverseCrossSection.h"

registerMooseObject("qpxApp", QPXInverseCrossSection);

InputParameters
QPXInverseCrossSection::validParams()
{
  InputParameters params = Material::validParams();
  params.addRequiredParam<bool>("interp_cross_section",
                                "Whether to interpolate transport "
                                "cross section as a function of the mean "
                                "energy. If false, cross section are constant.");
  params.addRequiredParam<std::string>("prop_name", "reaction type");
  params.addParam<Real>("cross_section_units", 1, "default cross section units m^2");
  params.addRequiredParam<FileName>(
      "file", "The file containing interpolation tables for cross sections.");
  params.addParam<Real>("user_cross_section", 0, "The user cross-section.");
  params.addRequiredParam<Real>("threshold_energy", "Minimum energy to excited state");
  params.addRequiredParam<Real>("statistical_weight",
      "The statistical weight is determined by the total angular momentum quantum number (J) of the state");
  params.addRequiredParam<Real>("max_energy",
      "maximum energy grid");
  params.addClassDescription("Cross section for one species.");
  return params;
}

QPXInverseCrossSection::QPXInverseCrossSection(const InputParameters & parameters)
  : Material(parameters),
    _interp_cross_section("interp_cross_section"),
    _cross_section(declareADProperty<Real>("cross_section_" + getParam<std::string>("prop_name"))),
    _cross_section_units(getParam<Real>("cross_section_units")),
    _user_cross_section(getParam<Real>("user_cross_section")),
    _threshold_energy(getParam<Real>("threshold_energy")),
    _g1_g2(getParam<Real>("statistical_weight")),
    _max_energy(getParam<Real>("max_energy"))
{
  std::vector<Real> actual_mean_energy;
  std::vector<Real> cross_section;

  std::string file_name = getParam<FileName>("file");
  MooseUtils::checkFileReadable(file_name);
  const char * charPath = file_name.c_str();
  std::ifstream myfile(charPath);
  Real value;

  if (myfile.is_open())
  {
    while (myfile >> value)
    {
      actual_mean_energy.push_back(value);
      myfile >> value;
      cross_section.push_back(value * _cross_section_units);
    }
    myfile.close();
  }

  else
    mooseError("Unable to open file");

  _cross_section_interpolation.setData(actual_mean_energy, cross_section);
}

void
QPXInverseCrossSection::computeQpProperties()
{
  if (_interp_cross_section)
  {
    Real energy = _q_point[_qp](0);
    Real shifted_energy = energy + _threshold_energy;

    if (shifted_energy > _max_energy) {
      _cross_section[_qp].value() = 0.0;
      _cross_section[_qp].derivatives() = 0.0;
    }
    else {
      Real interpolated_sigma = _cross_section_interpolation.sample(shifted_energy);
      Real interpolated_deriv = _cross_section_interpolation.sampleDerivative(shifted_energy);
      _cross_section[_qp].value() = _g1_g2 * shifted_energy / energy * interpolated_sigma;

      _cross_section[_qp].derivatives() = _g1_g2 *
                                (-_threshold_energy/energy/energy * interpolated_sigma
                                 + shifted_energy * interpolated_deriv);
    }
  }
  else
  {
    _cross_section[_qp].value() = _user_cross_section * _cross_section_units;
    _cross_section[_qp].derivatives() = 0.0;
  }
}
