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
        const ADReal value = _source(r, state);

        // Numerically transparent fast path. Only an already-invalid value
        // enters the forensic branch; no valid evaluation performs I/O.
        if (_diagnostic_file.empty() || value.value() >= 0.0)
          return value;

        const auto event = forensic_event_sequence.fetch_add(1) + 1;
        std::ostringstream record;
        record << std::setprecision(17)
               << "ISSUE236_OM_FORENSIC_V1"
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
            record << " face_id=NA elem_id=NA neighbor_id=NA face_side_id=NA"
                   << " cell_ref_id=NA cell_ref=NA";
          else
          {
            record << " face_id=" << r.fi->id()
                   << " elem_id=" << r.fi->elem().id()
                   << " neighbor_id=" << idOrNA(r.fi->neighborPtr())
                   << " face_side_id=" << idOrNA(r.face_side);

            // A cell reference is diagnostic context only; the exact consumed
            // face value is `value` above.  Re-evaluate only a side that is
            // unambiguous, so diagnostics cannot create a new block-restriction
            // failure on the opposite side of an internal face.
            const libMesh::Elem * reference_side = r.face_side;
            if (!reference_side && !r.fi->neighborPtr())
              reference_side = &r.fi->elem();

            if (reference_side)
            {
              const Moose::ElemArg cell_arg{reference_side, r.correct_skewness};
              const ADReal cell_ref = _source(cell_arg, state);
              record << " cell_ref_id=" << reference_side->id()
                     << " cell_ref=" << cell_ref.value();
            }
            else
              record << " cell_ref_id=NA cell_ref=NA";
          }
        }
        else
          record << " arg=Other";

        // Missing diagnostics make evidence invalid, but I/O failure must not
        // replace the production material's existing hard error.
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
