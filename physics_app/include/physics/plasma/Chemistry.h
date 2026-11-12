#pragma once

#include "PlasmaInterface.h"

#include <map>
#include <memory>
#include <string>
#include <vector>

namespace Plasma
{

struct DDTransportRecord
{
  std::string model;
  double mobility = 0.0;
  double diffusivity = 0.0;
  std::string table_file;
  std::string coordinate;
  std::string table_units;
  std::string pressure;
  std::string gas_temperature;
  std::string bounds_policy = "error";

  bool equals(const DDTransportRecord & rhs) const;
};

struct NVTransportRecord
{
  std::string transport_data_file;
  std::string temperature;
  std::string pressure;
  std::string electron_temperature;
  std::string electron_number_density;
  std::vector<std::string> species;
  std::vector<std::string> mass_fractions;

  bool equals(const NVTransportRecord & rhs) const;
};

struct SpeciesRecord
{
  std::map<std::string, int> elements;
  int charge_number = 0;
};

struct ReactionRecord
{
  std::string id;
  std::string equation;
  std::map<std::string, int> reactants;
  std::map<std::string, int> products;
  std::string progress;
  // A negative signed energy change removes energy from the electron equation.
  // A functor is an alternative *signed* energy change in eV/event.
  double electron_energy_change_eV = 0;
  std::string electron_energy_change_functor;
  bool contributes_electron_energy = false;

  int net(const std::string & species) const;
};

/** Immutable validated, shared plasma species and chemistry input contract. */
class ChemistryData
{
public:
  ChemistryData() = default;
  explicit ChemistryData(const std::vector<std::string> & files);

  const SpeciesRecord & species(const std::string & id) const;
  const std::vector<ReactionRecord> & reactions() const { return _reactions; }
  bool hasSpeciesSource(const std::string & id) const;
  bool hasElectronEnergySource() const;
  const DDTransportRecord * ddTransport(const std::string & id) const;
  const NVTransportRecord * nvTransport() const;

private:
  std::map<std::string, SpeciesRecord> _species;
  std::vector<ReactionRecord> _reactions;
  std::map<std::string, DDTransportRecord> _dd_transport;
  std::unique_ptr<NVTransportRecord> _nv_transport;
};

// Chemistry owns the Physics source projector and the validated JSON data model.
class Chemistry : public PlasmaInterface
{
public:
  static InputParameters validParams();
  explicit Chemistry(const InputParameters & parameters);

private:
  void checkIntegrity() const override;
  void addFunctorMaterials() override;
};

} // namespace Plasma
