#pragma once

#include <cstddef>
#include <map>
#include <string>
#include <vector>

class QPXReactionDatabase
{
public:
  enum class SpeciesKind
  {
    Heavy,
    Electron
  };

  enum class Domain
  {
    Volume,
    Surface
  };

  enum class RateModel
  {
    Constant,
    PowerLaw,
    ThermalSticking,
    DeferredChargedFlux
  };

  enum class RateBasis
  {
    Molar,
    Particle
  };

  struct Species
  {
    std::string name;
    std::string solver_id;
    double molar_mass = 0.0;
    int charge = 0;
    SpeciesKind kind = SpeciesKind::Heavy;
  };

  struct StoichTerm
  {
    std::size_t species_index = 0;
    double coefficient = 0.0;
  };

  struct Reaction
  {
    std::string name;
    Domain domain = Domain::Volume;
    RateModel model = RateModel::Constant;

    std::vector<StoichTerm> reactants;
    std::vector<StoichTerm> products;

    double A_input = 0.0;
    double A_molar = 0.0;
    RateBasis basis = RateBasis::Molar;
    double T_ref = 300.0;
    double exponent = 0.0;

    double sticking = 0.0;
    std::vector<double> extra;

    double reaction_order = 0.0;
  };

  explicit QPXReactionDatabase(const std::string & filename);

  const std::vector<Species> & species() const { return _species; }
  const std::vector<Reaction> & reactions() const { return _reactions; }

  std::size_t speciesIndex(const std::string & name) const;
  std::size_t reactionIndex(const std::string & name) const;

  const Species & species(const std::string & name) const;
  const Reaction & reaction(const std::string & name) const;

  double stoichCoefficient(const Reaction & reaction, std::size_t species_index) const;

  double heavyMassImbalance(const Reaction & reaction) const;
  double chargeImbalance(const Reaction & reaction) const;

  static constexpr double avogadro() { return 6.02214076e23; }

private:
  void load(const std::string & filename);
  void finalizeReaction(Reaction & reaction,
                        bool have_A,
                        bool have_basis,
                        bool have_sticking,
                        const std::string & filename,
                        unsigned int line_number);

  static std::string trim(const std::string & value);
  static SpeciesKind parseSpeciesKind(const std::string & value);
  static Domain parseDomain(const std::string & value);
  static RateModel parseRateModel(const std::string & value);
  static RateBasis parseRateBasis(const std::string & value);

  std::vector<Species> _species;
  std::vector<Reaction> _reactions;

  std::map<std::string, std::size_t> _species_index;
  std::map<std::string, std::size_t> _reaction_index;
};
