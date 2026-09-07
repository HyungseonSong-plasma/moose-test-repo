#include "QPXTotalCrossSection.h"

registerMooseObject("qpxApp", TotalCrossSection);

InputParameters
TotalCrossSection::validParams()
{
  InputParameters params = Material::validParams();
  params.addRequiredParam<VectorPostprocessorName>(
      "vpp",
      "The VectorPostprocessor providing per-reaction relative number-density weights (n_k/n_ref).");
  params.addRequiredParam<std::string>(
      "vpp_name", "The name of the vector within the VectorPostprocessor.");
  params.addRequiredParam<std::vector<unsigned int>>("collision_partner_index", "Index of collision partners.");
  params.addRequiredParam<MaterialPropertyName>("prop_name", "Total cross section values");
  params.addRequiredParam<std::string>(
      "reaction_lists",
      "Space-separated reaction IDs (e.g. LXCat process tags). Each ID must correspond to an AD material property "
      "named cross_section_<id>. Use optional species for the heavy-particle species per entry (same order).");
  params.addClassDescription("Total cross section.");
  return params;
}

TotalCrossSection::TotalCrossSection(const InputParameters & parameters)
  : Material(parameters),
    _x(getVectorPostprocessorValue("vpp", getParam<std::string>("vpp_name"))),
    _collision_partner_index(getParam<std::vector<unsigned int>>("collision_partner_index")),
    _total_cross_section(declareADProperty<Real>("prop_name"))
{
  std::vector<std::string> names;
  MooseUtils::tokenize(getParam<std::string>("reaction_lists"), names, 1, " ");

  if (_collision_partner_index.size() != names.size())
    mooseError("The size of collision_partner_index should be the same as that of the reaction_lists");

  for (const auto & name : names)
    _cross_sections.push_back(&getADMaterialProperty<Real>("cross_section_" + name));
}

void
TotalCrossSection::computeQpProperties()
{
  _total_cross_section[_qp] = 0.0;

  for (unsigned int k = 0; k < _collision_partner_index.size(); ++k) {
    unsigned int index = _collision_partner_index[k];
    _total_cross_section[_qp] += _x[index] * (*_cross_sections[k])[_qp].value();
  }
}
