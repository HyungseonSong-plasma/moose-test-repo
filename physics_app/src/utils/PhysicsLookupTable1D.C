#include "PhysicsLookupTable1D.h"

#include <algorithm>
#include <fstream>
#include <sstream>
#include <stdexcept>

PhysicsLookupTable1D::PhysicsLookupTable1D(const std::string & filename,
                                           std::size_t coordinate_column,
                                           const std::vector<std::size_t> & value_columns)
{
  load(filename, coordinate_column, value_columns);
}

std::string
PhysicsLookupTable1D::trim(const std::string & input)
{
  const auto first = input.find_first_not_of(" \t\r\n");
  if (first == std::string::npos)
    return "";

  const auto last = input.find_last_not_of(" \t\r\n");
  return input.substr(first, last - first + 1);
}

void
PhysicsLookupTable1D::load(const std::string & filename,
                           std::size_t coordinate_column,
                           const std::vector<std::size_t> & value_columns)
{
  if (coordinate_column == 0)
    throw std::runtime_error("PhysicsLookupTable1D uses 1-based column indices.");

  if (value_columns.empty())
    throw std::runtime_error("PhysicsLookupTable1D requires at least one value column.");

  for (const auto column : value_columns)
    if (column == 0)
      throw std::runtime_error("PhysicsLookupTable1D uses 1-based column indices.");

  std::ifstream in(filename);
  if (!in.good())
    throw std::runtime_error("PhysicsLookupTable1D could not open '" + filename + "'.");

  _coordinate.clear();
  _values.assign(value_columns.size(), {});

  std::string line;
  unsigned int line_number = 0;

  while (std::getline(in, line))
  {
    ++line_number;

    const auto hash = line.find('#');
    if (hash != std::string::npos)
      line.erase(hash);

    line = trim(line);
    if (line.empty())
      continue;

    std::istringstream iss(line);
    std::vector<double> row;
    double value = 0.0;

    while (iss >> value)
      row.push_back(value);

    std::size_t required_column = coordinate_column;
    for (const auto column : value_columns)
      required_column = std::max(required_column, column);

    if (row.size() < required_column)
    {
      std::ostringstream oss;
      oss << "PhysicsLookupTable1D malformed row in '" << filename << "' at line "
          << line_number << ": expected at least " << required_column
          << " numeric columns, found " << row.size() << ".";
      throw std::runtime_error(oss.str());
    }

    _coordinate.push_back(row[coordinate_column - 1]);

    for (std::size_t j = 0; j < value_columns.size(); ++j)
      _values[j].push_back(row[value_columns[j] - 1]);
  }

  if (_coordinate.size() < 2)
    throw std::runtime_error("PhysicsLookupTable1D requires at least two rows.");

  for (std::size_t i = 1; i < _coordinate.size(); ++i)
    if (!(_coordinate[i] > _coordinate[i - 1]))
      throw std::runtime_error(
          "PhysicsLookupTable1D coordinate must be strictly increasing.");

  for (const auto & values : _values)
    if (values.size() != _coordinate.size())
      throw std::runtime_error("PhysicsLookupTable1D internal table-size mismatch.");
}

const std::vector<double> &
PhysicsLookupTable1D::values(std::size_t value_index) const
{
  if (value_index >= _values.size())
    throw std::out_of_range("PhysicsLookupTable1D value column index out of range.");

  return _values[value_index];
}

std::size_t
PhysicsLookupTable1D::lowerBracket(double x) const
{
  if (_coordinate.size() < 2)
    throw std::runtime_error("PhysicsLookupTable1D is not initialized.");

  if (x <= _coordinate.front())
    return 0;

  if (x >= _coordinate.back())
    return _coordinate.size() - 2;

  const auto upper = std::upper_bound(_coordinate.begin(), _coordinate.end(), x);
  return static_cast<std::size_t>(upper - _coordinate.begin() - 1);
}
