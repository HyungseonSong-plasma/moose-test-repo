#pragma once

#include "FunctorMaterial.h"

#include <map>
#include <string>
#include <vector>

/**
 * Data-driven heavy-species transport-coefficient material.
 *
 * Species constants and collision-integral tables are read from a text database.
 * The C++ implementation is independent of the number and names of active species.
 *
 * For each active species i, this object exposes:
 *
 *   D_T_i [kg/(m s)] such that
 *       j_i^T = -D_T_i * grad(T) / T
 *
 *   kT_i [-]
 *       dimensionless heavy-species thermal-diffusion ratio.
 *
 *   D_mix_i [m^2/s]
 *       COMSOL-style mixture-averaged diffusion coefficient computed from
 *       the same canonical binary collision data used by the thermal path.
 *
 * The active species list and matching mass-fraction functors are supplied by the
 * input file. Neutral and ion-neutral collision data are supplied by
 * transport_data_file. Charged-charged collision integrals are evaluated at
 * runtime with a Mutation++-equivalent Debye-Huckel model using T, Te, and ne.
 */
class PhysicsThermalDiffusionMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsThermalDiffusionMaterial(const InputParameters & parameters);

protected:
  using Vec = std::vector<ADReal>;
  using Mat = std::vector<Vec>;

  struct SpeciesInfo
  {
    Real molar_mass = 0.0;       // kg/mol
    std::string transport_alias; // collision-data species key
  };

  struct CollisionTable
  {
    Real Bstar = 0.0;
    Real Cstar = 0.0;
    std::vector<Real> T;
    std::vector<Real> Q11;
    std::vector<Real> Q22;
  };

  struct CollisionData
  {
    ADReal Q11 = 0.0;
    ADReal Q22 = 0.0;
    ADReal Bstar = 0.0;
    ADReal Cstar = 0.0;
  };

  enum class CoulombBranch
  {
    ATTRACTIVE,
    REPULSIVE
  };

  struct Result
  {
    Vec kT;
    Vec D_T;
    Vec V_unit_gradT;
    Vec D_mix;
  };

  void loadTransportDatabase(const FileName & filename);

  Result evaluate(const ADReal & T,
                  const ADReal & p,
                  const ADReal & Te,
                  const ADReal & ne,
                  const Vec & Y) const;
  
  /**
   * Evaluate only the mixture-averaged diffusion coefficient D_mix for one species.
   *
   * This path intentionally avoids the Chapman-Enskog, thermal-diffusion-ratio,
   * Stefan-Maxwell, and D_T calculations required by the full evaluate() path.
   */
  ADReal evaluateDmix(const std::size_t species_i,
                      const ADReal & T,
                      const ADReal & p,
                      const ADReal & Te,
                      const ADReal & ne,
                      const Vec & Y) const;
                      
  Vec solveSystem(Mat A, Vec b) const;

  static ADReal positiveFloor(const ADReal & value, Real floor);

  ADReal interpolateCollisionIntegral(const ADReal & T,
                                      const std::vector<Real> & grid,
                                      const std::vector<Real> & values) const;

  const CollisionTable & collisionTable(const std::string & alias_a,
                                        const std::string & alias_b) const;

  CollisionData collisionData(const ADReal & T,
                              const ADReal & Te,
                              const ADReal & ne,
                              const std::string & alias_a,
                              const std::string & alias_b) const;

  CollisionData debyeHuckelCollisionData(const ADReal & T,
                                         const ADReal & Te,
                                         const ADReal & ne,
                                         CoulombBranch branch) const;

  static int aliasCharge(const std::string & alias);
  static bool isChargedChargedPair(const std::string & alias_a,
                                   const std::string & alias_b);

  static std::string pairKey(std::string a, std::string b);
  static std::string trim(const std::string & s);

  const Moose::Functor<ADReal> & _temperature;
  const Moose::Functor<ADReal> & _pressure;

  const Moose::Functor<ADReal> * _electron_temperature = nullptr;
  const Moose::Functor<ADReal> * _electron_number_density = nullptr;
  bool _has_charged_charged_pairs = false;

  FileName _transport_data_file;

  std::vector<std::string> _species_names;
  std::vector<MooseFunctorName> _mass_fraction_names;
  std::vector<const Moose::Functor<ADReal> *> _mass_fractions;

  std::vector<MooseFunctorName> _D_T_names;
  std::vector<MooseFunctorName> _kT_names;
  std::vector<MooseFunctorName> _D_mix_names;

  std::map<std::string, SpeciesInfo> _species_database;
  std::map<std::string, CollisionTable> _collision_database;

  std::vector<Real> _molar_masses;
  std::vector<std::string> _transport_aliases;
};
