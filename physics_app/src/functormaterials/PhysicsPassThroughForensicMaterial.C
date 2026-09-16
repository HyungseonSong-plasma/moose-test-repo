#include "PhysicsPassThroughForensicMaterial.h"

#include "FaceInfo.h"
#include "MooseFunctorArguments.h"

#include <atomic>
#include <fstream>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <type_traits>

registerMooseObject("PhysicsApp", PhysicsPassThroughForensicMaterial);

namespace
{
std::atomic<unsigned long long> forensic_event_sequence{0};
std::mutex forensic_write_mutex;

template <typename T>
std::string
idOrNA(const T * object)
{
  if (!object)
    return "NA";
  return std::to_string(object->id());
}
}

InputParameters
PhysicsPassThroughForensicMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription(
      "Returns a scalar functor unchanged while optionally recording exact invalid "
      "Functor arguments for governed diagnostics.");
  params.addRequiredParam<MooseFunctorName>("source", "Scalar source functor to pass through.");
  params.addRequiredParam<MooseFunctorName>(
      "property_name", "Name of the transparent pass-through functor property.");
  params.addParam<std::string>(
      "diagnostic_file",
      "",
      "Append-only diagnostic record path. Empty disables recording without changing the return value.");
  params.addParam<std::string>(
      "diagnostic_tag", "", "Short provenance tag written with every diagnostic record.");
  return params;
}

PhysicsPassThroughForensicMaterial::PhysicsPassThroughForensicMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _source(getFunctor<ADReal>("source")),
    _property_name(getParam<MooseFunctorName>("property_name")),
    _diagnostic_file(getParam<std::string>("diagnostic_file")),
    _diagnostic_tag(getParam<std::string>("diagnostic_tag"))
{
  addFunctorProperty<ADReal>(
      _property_name,
      [this](const auto & r, const auto & state) -> ADReal
      {
        // Exact-consumer contract: evaluate the wrapped source once, with the
        // framework-supplied (r, state), and return that exact ADReal unchanged.
        const ADReal value = _source(r, state);

        // Valid evaluations take the transparent fast path with no I/O.
        if (_diagnostic_file.empty() || value.value() >= 0.0)
          return value;

        const auto event = forensic_event_sequence.fetch_add(1) + 1;
        std::ostringstream record;
        record << std::setprecision(17)
               << "ISSUE236_OM_FORENSIC_V2"
               << " event=" << event
               << " tag=" << (_diagnostic_tag.empty() ? "NA" : _diagnostic_tag)
               << " material=" << name()
               << " property=" << _property_name
               << " source=" << _source.functorName()
               << " state=" << state.state
               << " iteration_type=" << static_cast<int>(state.iteration_type)
               << " consumed_value=" << value.value();

        using SpaceArg = std::decay_t<decltype(r)>;
        if constexpr (std::is_same_v<SpaceArg, Moose::ElemArg>)
        {
          record << " arg=ElemArg"
                 << " elem_id=" << idOrNA(r.elem);
        }
        else if constexpr (std::is_same_v<SpaceArg, Moose::FaceArg>)
        {
          record << " arg=FaceArg";
          if (!r.fi)
            record << " face_id=NA elem_id=NA neighbor_id=NA face_side_id=NA";
          else
            record << " face_id=" << r.fi->id()
                   << " elem_id=" << r.fi->elem().id()
                   << " neighbor_id=" << idOrNA(r.fi->neighborPtr())
                   << " face_side_id=" << idOrNA(r.face_side);
        }
        else
          record << " arg=Other";

        // Recording failure must never replace the production consumer's
        // existing hard error. Failure to persist this record is handled later
        // by the evidence gate, not by throwing from the observer.
        {
          std::lock_guard<std::mutex> lock(forensic_write_mutex);
          std::ofstream output(_diagnostic_file, std::ios::out | std::ios::app);
          if (output)
          {
            output << record.str() << '\n';
            output.flush();
          }
        }

        return value;
      });
}
