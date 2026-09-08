#pragma once

#include <cstddef>
#include <string>
#include <vector>

/**
 * Lightweight whitespace-delimited 1D lookup table.
 *
 * The first selected column is the monotonic coordinate. Additional selected
 * columns are stored as dependent values. This helper has no MOOSE dependency
 * and can be unit-tested independently.
 */
class PhysicsLookupTable1D
{
public:
  PhysicsLookupTable1D() = default;

  PhysicsLookupTable1D(const std::string & filename,
                       std::size_t coordinate_column,
                       const std::vector<std::size_t> & value_columns);

  void load(const std::string & filename,
            std::size_t coordinate_column,
            const std::vector<std::size_t> & value_columns);

  const std::vector<double> & coordinate() const { return _coordinate; }
  const std::vector<double> & values(std::size_t value_index) const;

  std::size_t valueCount() const { return _values.size(); }
  std::size_t size() const { return _coordinate.size(); }

  std::size_t lowerBracket(double x) const;

private:
  static std::string trim(const std::string & input);

  std::vector<double> _coordinate;
  std::vector<std::vector<double>> _values;
};
