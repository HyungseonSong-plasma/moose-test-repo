#pragma once

#include "PlasmaInterface.h"
#include "Action.h"

#include <map>
#include <memory>
#include <optional>
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

// One explicitly declared mesh sideset and its electron boundary owner.
// Aliases such as wafer and inlet are labels, not inferred mesh names.
// A verbatim supported MOOSE BC declaration moved from an existing .i
// [BCs] block. Its name, type, variable, and material Functor links are
// retained, with the mesh boundary supplied by its enclosing JSON record.
struct BoundaryBCRecord
{
  std::string type;
  std::string variable;
  std::string wall_number_flux;
  std::string mean_energy;
};

struct BoundaryRecord
{
  // A single existing BC may own multiple mesh sidesets. Never split that
  // original operator into separate objects during JSON relocation.
  std::vector<std::string> mesh_boundaries;
  std::map<std::string, BoundaryBCRecord> bcs;
};

struct SpeciesRecord
{
  std::map<std::string, int> elements;
  int charge_number = 0;
  // Needed only for rate laws evaluated from heavy-species mass fractions.
  double molar_mass_kg_mol = 0.0;
  // Optional initial number density [1/m^3] for FEM/FV continuity. Presence
  // activates generated log-molar variable/IC; absence leaves legacy external
  // solver variable ownership. Strictly positive (log-state cannot encode zero).
  std::optional<double> initial_number_density;
  // Scenario-specific initial data, never the instantaneous solver state.
  // Missing is different from an explicitly zero concentration.
  std::optional<double> initial_vol_mass_fraction;
  std::optional<double> initial_inlet_mass_fraction;
  // A live Y_i(t,x) owner is mandatory for root ideal_gas: either a solver
  // mass-fraction variable, or a derived (constraint) Functor. These are
  // NOT sources of initial or inlet values.
  std::string mass_fraction_variable;
  std::string mass_fraction_functor;
};

// Validated executable rate law. Empty model means the reaction progress
// must be provided independently (e.g. an electron-impact lookup table).
struct RateRecord
{
  std::string model;
  std::string basis;
  double A_input = 0.0;
  double A_molar = 0.0;
  double T_ref = 300.0;
  double exponent = 0.0;
  double sticking = 0.0;
};

struct ReactionRecord
{
  std::string id;
  std::string equation;
  std::map<std::string, int> reactants;
  std::map<std::string, int> products;
  std::string progress;
  std::string domain = "volume";
  RateRecord rate;
  // Positive energy_loss_eV removes electron energy (one minus sign at RHS).
  // A functor is an alternative positive-loss magnitude in eV/event.
  double energy_loss_eV = 0;
  std::string energy_loss_functor;
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
  const std::map<std::string, SpeciesRecord> & speciesRecords() const { return _species; }
  const std::vector<ReactionRecord> & reactions() const { return _reactions; }
  bool hasSpeciesSource(const std::string & id) const;
  bool hasElectronEnergySource() const;
  const DDTransportRecord * ddTransport(const std::string & id) const;
  bool hasDDTransport() const { return !_dd_transport.empty(); }
  bool fluidElectronEnergyTransport() const { return _fluid_electron_energy_transport; }
  const NVTransportRecord * nvTransport() const;
  bool hasBoundaries() const { return _has_boundaries; }
  const std::map<std::string, BoundaryRecord> & boundaries() const
  {
    return _boundaries;
  }
  // Scenario-specific heavy-species composition is stored directly in speciesRecords().

private:
  std::map<std::string, SpeciesRecord> _species;
  std::vector<ReactionRecord> _reactions;
  std::map<std::string, DDTransportRecord> _dd_transport;
  bool _fluid_electron_energy_transport = false;
  std::unique_ptr<NVTransportRecord> _nv_transport;
  bool _has_boundaries = false;
  std::map<std::string, BoundaryRecord> _boundaries;
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

/** Root [Plasmas] Action; one validated mechanism owner shared by child Physics. */
class PlasmasAction : public Action
{
public:
  static InputParameters validParams();
  explicit PlasmasAction(const InputParameters & params);
  void act() override;

  bool gasStateEnabled() const { return isParamValid("pressure") && isParamValid("temperature"); }

  const Plasma::ChemistryData & data() const { return _data; }

private:
  const Plasma::ChemistryData _data;
};
