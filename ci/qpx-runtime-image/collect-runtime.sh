#!/usr/bin/env bash
# Runtime closure v2: installed data layout + dependency-driven ELF closure.
set -euo pipefail

DEST="${1:-/runtime-root}"
mkdir -p \
  "$DEST/opt" \
  "$DEST/usr" \
  "$DEST/lib" \
  "$DEST/lib64" \
  "$DEST/etc/ld.so.conf.d"

LIBDIRS_FILE="$(mktemp)"
LDD_OUTPUT="$(mktemp)"
trap 'rm -f "$LIBDIRS_FILE" "$LDD_OUTPUT"' EXIT

copy_path() {
  local src="$1"
  local rel
  if [[ -e "$src" || -L "$src" ]]; then
    rel="${src#/}"
    mkdir -p "$DEST/$(dirname "$rel")"
    cp -a "$src" "$DEST/$rel"
  fi
}

copy_resolved() {
  local src="$1"
  local rel
  if [[ -e "$src" ]]; then
    rel="${src#/}"
    mkdir -p "$DEST/$(dirname "$rel")"
    cp -aL "$src" "$DEST/$rel"
  fi
}

copy_tree_to() {
  local src="$1"
  local dst="$2"
  local full_dst="$DEST$dst"
  if [[ -d "$src" ]]; then
    mkdir -p "$(dirname "$full_dst")"
    rm -rf "$full_dst"
    cp -a "$src" "$full_dst"
  fi
}

record_libdir() {
  local path="$1"
  dirname "$path" >> "$LIBDIRS_FILE"
}

# Canonical executable and bounded smoke input.
copy_path /opt/qpx/qpx-opt
copy_path /opt/qpx/ci/smoke.i

# MOOSE resolves installed application data relative to the executable as
# PREFIX/share/<name>/data. Preserve that canonical installed layout and also
# retain the original in-tree location as a fallback for binaries compiled with
# absolute __FILE__ paths.
copy_tree_to /opt/qpx_vendor/moose/framework/data /opt/share/moose/data
copy_tree_to /opt/qpx_vendor/moose/framework/data /opt/qpx_vendor/moose/framework/data

shopt -s nullglob
for module_data in /opt/qpx_vendor/moose/modules/*/data; do
  module_name="$(basename "$(dirname "$module_data")")"
  copy_tree_to "$module_data" "/opt/share/${module_name}/data"
  copy_tree_to "$module_data" "$module_data"
done
shopt -u nullglob

for app_spec in \
  "qpx:/opt/qpx/data" \
  "crane:/opt/qpx_vendor/crane/data" \
  "squirrel:/opt/qpx_vendor/squirrel/data" \
  "zapdos:/opt/qpx_vendor/zapdos/data"
do
  app_name="${app_spec%%:*}"
  app_data="${app_spec#*:}"
  copy_tree_to "$app_data" "/opt/share/${app_name}/data"
  copy_tree_to "$app_data" "$app_data"
done

# qpx-opt is linked against the application and test shared libraries produced
# beside the canonical qpx_app source tree. They are not installed into a
# system loader path during the source-build lane, so make their build layout
# explicit for dependency discovery. ldd will then report those QPX-local
# libraries together with their complete transitive MOOSE/PETSc dependencies.
test -e /opt/qpx/lib/libqpx-opt.so.0
test -e /opt/qpx/test/lib/libqpx_test-opt.so.0
export LD_LIBRARY_PATH="/opt/qpx/test/lib:/opt/qpx/lib:${LD_LIBRARY_PATH:-}"

# One ldd invocation on the final executable is sufficient for the ELF loader's
# complete transitive NEEDED closure. The previous implementation ran ldd over
# every vendor shared object and spent ~95 seconds collecting a much larger,
# mostly unused closure.
ldd /opt/qpx/qpx-opt > "$LDD_OUTPUT"
if grep -Fq 'not found' "$LDD_OUTPUT"; then
  cat "$LDD_OUTPUT" >&2
  echo "Unresolved dynamic dependency in qpx-opt" >&2
  exit 1
fi

while IFS= read -r dependency; do
  [[ -n "$dependency" ]] || continue
  copy_resolved "$dependency"
  record_libdir "$dependency"
done < <(
  awk '
    /=> \/[^ ]+/ { print $3 }
    /^[[:space:]]*\/[^ ]+/ { print $1 }
  ' "$LDD_OUTPUT" | sort -u
)

# OpenMPI loads MCA components dynamically, so they are intentionally outside
# qpx-opt's static ELF dependency graph. Keep only the OpenMPI runtime surface;
# compiler-independent data and shared components are retained, while static
# archives and development headers are not copied wholesale.
for runtime_path in \
  /opt/openmpi/bin \
  /opt/openmpi/share/openmpi \
  /opt/openmpi/etc \
  /opt/openmpi/libexec
do
  copy_path "$runtime_path"
done

if [[ -d /opt/openmpi/lib ]]; then
  while IFS= read -r -d '' lib; do
    copy_path "$lib"
    record_libdir "$lib"
  done < <(find /opt/openmpi/lib \( -type f -o -type l \) \( -name '*.so' -o -name '*.so.*' \) -print0)
fi
printf '%s\n' /opt/openmpi/lib >> "$LIBDIRS_FILE"

# Generate loader search metadata while build tooling is available. The final
# image needs only ldconfig and does not need findutils.
sort -u "$LIBDIRS_FILE" > "$DEST/etc/ld.so.conf.d/qpx-runtime.conf"

# Hard acceptance guard: MOOSE core data must be available through the exact
# installed path Registry::determineDataFilePath() checks first.
test -r "$DEST/opt/share/moose/data/README.md"

{
  echo "RUNTIME_ROOT_BYTES=$(du -sb "$DEST" | awk '{print $1}')"
  echo "RUNTIME_FILE_COUNT=$(find "$DEST" -type f | wc -l | tr -d ' ')"
  echo "ELF_DEPENDENCY_COUNT=$(awk '/=> \/[^ ]+/ {print $3} /^[[:space:]]*\/[^ ]+/ {print $1}' "$LDD_OUTPUT" | sort -u | wc -l | tr -d ' ')"
} > "$DEST/opt/qpx/RUNTIME_CLOSURE.txt"

cat "$DEST/opt/qpx/RUNTIME_CLOSURE.txt"
