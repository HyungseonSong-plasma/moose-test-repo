#include "PhysicsBoltzmannCrossSections.h"

#include <algorithm>
#include <cmath>
#include <sstream>
#include <stdexcept>

namespace PhysicsBoltzmann
{
namespace
{
std::string trim(const std::string & s)
{
  auto a = s.find_first_not_of(" \t\r\n");
  if (a == std::string::npos)
    return "";
  auto b = s.find_last_not_of(" \t\r\n");
  return s.substr(a, b - a + 1);
}

bool delimiter(const std::string & text)
{
  return text.size() >= 5 && text.find_first_not_of('-') == std::string::npos;
}

bool kindFor(const std::string & word, CollisionKind & kind)
{
  if (word == "ELASTIC") kind = CollisionKind::Elastic;
  else if (word == "EFFECTIVE" || word == "MOMENTUM") kind = CollisionKind::Effective;
  else if (word == "EXCITATION") kind = CollisionKind::Excitation;
  else if (word == "IONIZATION") kind = CollisionKind::Ionization;
  else if (word == "ATTACHMENT") kind = CollisionKind::Attachment;
  else if (word == "ROTATION") kind = CollisionKind::Rotation;
  else return false;
  return true;
}

double strictNumber(const std::string & word)
{
  if (word.empty())
    throw std::invalid_argument("Boltzmann cross sections: missing numeric parameter");
  std::size_t used = 0;
  double v;
  try { v = std::stod(word, &used); }
  catch (const std::exception &)
  { throw std::invalid_argument("Boltzmann cross sections: malformed numeric value"); }
  if (used != word.size() || !std::isfinite(v))
    throw std::invalid_argument("Boltzmann cross sections: non-finite or malformed numeric value");
  return v;
}

double firstParameter(const std::string & line)
{
  std::istringstream ss(line);
  std::string token;
  if (!(ss >> token))
    throw std::invalid_argument("Boltzmann cross sections: missing parameter line");
  return strictNumber(token);
}

void splitTarget(CollisionRecord & record, const std::string & line)
{
  const auto reversible = line.find("<->");
  const auto arrow = line.find("->");
  if (reversible != std::string::npos)
  {
    record.reversible = true;
    record.target = trim(line.substr(0, reversible));
    record.product = trim(line.substr(reversible + 3));
  }
  else if (arrow != std::string::npos)
  {
    record.target = trim(line.substr(0, arrow));
    record.product = trim(line.substr(arrow + 2));
  }
  else
    record.target = trim(line);
  if (record.target.empty() ||
      record.target.find_first_of(" \t") != std::string::npos ||
      (!record.product.empty() && record.product.find_first_of("\t") != std::string::npos))
    throw std::invalid_argument("Boltzmann cross sections: malformed collision target");
  if (record.reversible && record.product.empty())
    throw std::invalid_argument("Boltzmann cross sections: reversible process is missing upper state");
}

std::string nextNonempty(std::istream & input, std::size_t & line_no)
{
  std::string line;
  while (std::getline(input, line))
  {
    ++line_no;
    line = trim(line);
    if (!line.empty())
      return line;
  }
  throw std::invalid_argument("Boltzmann cross sections: unexpected end of collision block");
}
} // namespace

CollisionFile parseBolsigCrossSections(std::istream & input)
{
  CollisionFile out;
  std::string line;
  std::size_t line_no = 0;
  while (std::getline(input, line))
  {
    ++line_no;
    line = trim(line);
    if (line.empty())
      continue;
    CollisionKind kind;
    if (!kindFor(line, kind))
    {
      if (out.records.empty())
      {
        out.header.push_back(line);
        if (out.header.size() > 500)
          throw std::invalid_argument("Boltzmann cross sections: excessive file preamble");
        continue;
      }
      throw std::invalid_argument("Boltzmann cross sections: unexpected text after a collision block at line " +
                                  std::to_string(line_no));
    }
    if (out.records.size() >= 1000)
      throw std::invalid_argument("Boltzmann cross sections: excessive number of processes");

    CollisionRecord rec;
    rec.kind = kind;
    rec.source_line = line_no;
    splitTarget(rec, nextNonempty(input, line_no));
    if (kind != CollisionKind::Attachment)
    {
      // ROTATION follows a model-specific convention. Parse its metadata
      // but refuse its use for the M4 elastic+excitation projection.
      rec.parameter = firstParameter(nextNonempty(input, line_no));
      if (!std::isfinite(rec.parameter))
        throw std::invalid_argument("Boltzmann cross sections: invalid process parameter");
      if ((kind == CollisionKind::Elastic || kind == CollisionKind::Effective) &&
          !(rec.parameter > 0.0 && rec.parameter < 1.0))
        throw std::invalid_argument("Boltzmann cross sections: invalid elastic mass ratio");
      if ((kind == CollisionKind::Excitation || kind == CollisionKind::Ionization) &&
          !(rec.parameter > 0.0))
        throw std::invalid_argument("Boltzmann cross sections: invalid inelastic threshold");
    }
    bool open = false;
    while (std::getline(input, line))
    {
      ++line_no;
      line = trim(line);
      if (delimiter(line))
      {
        open = true;
        break;
      }
      if (!line.empty())
        rec.comments.push_back(line);
      if (rec.comments.size() > 1000)
        throw std::invalid_argument("Boltzmann cross sections: excessive process metadata");
    }
    if (!open)
      throw std::invalid_argument("Boltzmann cross sections: missing opening dashed delimiter");

    bool closed = false;
    while (std::getline(input, line))
    {
      ++line_no;
      line = trim(line);
      if (delimiter(line))
      {
        closed = true;
        break;
      }
      if (line.empty())
        continue;
      std::istringstream ss(line);
      std::string x, y, extra;
      if (!(ss >> x >> y) || (ss >> extra))
        throw std::invalid_argument("Boltzmann cross sections: expected exactly two numeric table columns");
      const double energy = strictNumber(x), sigma = strictNumber(y);
      if (energy < 0.0 || sigma < 0.0)
        throw std::invalid_argument("Boltzmann cross sections: negative energy or cross section");
      if (!rec.energy_eV.empty() && !(energy > rec.energy_eV.back()))
        throw std::invalid_argument("Boltzmann cross sections: energies must be strictly increasing");
      rec.energy_eV.push_back(energy);
      rec.cross_section_m2.push_back(sigma);
      if (rec.energy_eV.size() > 1000000)
        throw std::invalid_argument("Boltzmann cross sections: excessive cross-section rows");
    }
    if (!closed || rec.energy_eV.size() < 2)
      throw std::invalid_argument("Boltzmann cross sections: incomplete process table");
    out.records.push_back(std::move(rec));
  }
  if (out.records.empty())
    throw std::invalid_argument("Boltzmann cross sections: no recognized collision records");
  return out;
}

ImportedElasticExcitation prepareElasticExcitation(
    const CollisionFile & file,
    const std::map<std::string, double> & fractions,
    double max_energy_eV)
{
  if (!std::isfinite(max_energy_eV) || max_energy_eV <= 0.0 || fractions.empty())
    throw std::invalid_argument("Boltzmann cross sections: invalid projection inputs");

  // Validate the *whole* input before projecting any model state.
  for (const auto & rec : file.records)
  {
    if (rec.kind != CollisionKind::Elastic && rec.kind != CollisionKind::Excitation)
      throw std::invalid_argument("Boltzmann cross sections: unsupported EFFECTIVE/MOMENTUM, ionization, attachment or rotation channel");
    if (rec.reversible)
      throw std::invalid_argument("Boltzmann cross sections: superelastic reversible excitation is not implemented");
    if (rec.energy_eV.front() > 0.0 || rec.energy_eV.back() < max_energy_eV)
      throw std::invalid_argument("Boltzmann cross sections: source does not cover [0,max_energy_eV]; no silent extrapolation");
  }

  ImportedElasticExcitation result;
  std::map<std::string, std::size_t> elastic_counts;
  for (const auto & rec : file.records)
  {
    if (rec.kind == CollisionKind::Elastic)
    {
      auto it = fractions.find(rec.target);
      if (it == fractions.end())
        throw std::invalid_argument("Boltzmann cross sections: missing active target number fraction");
      if (++elastic_counts[rec.target] != 1)
        throw std::invalid_argument("Boltzmann cross sections: duplicate elastic target");
      result.targets.push_back({rec.target, it->second, rec.parameter,
                                rec.energy_eV, rec.cross_section_m2});
    }
  }
  for (const auto & [target, fraction] : fractions)
  {
    if (!std::isfinite(fraction) || fraction <= 0.0 ||
        elastic_counts.find(target) == elastic_counts.end())
      throw std::invalid_argument("Boltzmann cross sections: missing elastic target or invalid fraction");
  }
  double sum = 0.0;
  for (const auto & [target, fraction] : fractions)
  {
    (void)target;
    sum += fraction;
  }
  if (std::abs(sum - 1.0) > 1e-12)
    throw std::invalid_argument("Boltzmann cross sections: target fractions must sum to one");

  for (const auto & rec : file.records)
  {
    if (rec.kind == CollisionKind::Excitation)
    {
      if (elastic_counts.find(rec.target) == elastic_counts.end())
        throw std::invalid_argument("Boltzmann cross sections: excitation has no elastic target");
      if (rec.parameter >= max_energy_eV)
        throw std::invalid_argument("Boltzmann cross sections: excitation threshold exceeds energy domain");
      const std::string id = rec.target + ":excitation:" + std::to_string(result.channels.size() + 1);
      result.channels.push_back({id, rec.target, rec.parameter,
                                 rec.energy_eV, rec.cross_section_m2});
    }
  }
  return result;
}
} // namespace PhysicsBoltzmann
