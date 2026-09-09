#!/usr/bin/env bash
# Runtime closure v3: dependency-driven ELF closure with precomputed loader cache.
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

bytes_of() {
  local path="$1"
  if [[ -e "$path" || -L "$path" ]]; then
    du -sb "$path" | awk '{print $1}'
  else
    echo 0
  fi
}

strip_debug_tree() {
  local root="$1"
  local file
  [[ -d "$root" ]] || return 0
  while IFS= read -r -d '' file; do
    if readelf -h "$file" >/dev/null 2>&1; then
      strip --strip-debug "$file"
    fi
  done < <(find "$root" -type f -print0)
}

# Canonical executable and bounded smoke input.
copy_path /opt/physics/physics-opt
copy_path /opt/physics/ci/smoke.i

# MOOSE resolves installed application data relative to the executable as
# PREFIX/share/<name>/data. Preserve that canonical installed layout and also
# retain the original in-tree location as a fallback for binaries compiled with
# absolute __FILE__ paths.
copy_tree_to /opt/physics_vendor/moose/framework/data /opt/share/moose/data
copy_tree_to /opt/physics_vendor/moose/framework/data /opt/physics_vendor/moose/framework/data

shopt -s nullglob
for module_data in /opt/physics_vendor/moose/modules/*/data; do
  module_name="$(basename "$(dirname "$module_data")")"
  copy_tree_to "$module_data" "/opt/share/${module_name}/data"
  copy_tree_to "$module_data" "$module_data"
done
shopt -u nullglob

for app_spec in \
  "physics:/opt/physics/data" \
  "crane:/opt/physics_vendor/crane/data" \
  "squirrel:/opt/physics_vendor/squirrel/data" \
  "zapdos:/opt/physics_vendor/zapdos/data"
do
  app_name="${app_spec%%:*}"
  app_data="${app_spec#*:}"
  copy_tree_to "$app_data" "/opt/share/${app_name}/data"
  copy_tree_to "$app_data" "$app_data"
done

# physics-opt is linked against the application and test shared libraries
# produced beside the canonical physics_app source tree. They are not installed
# into a system loader path during the source-build lane, so make their build
# layout explicit for dependency discovery. ldd will then report those local
# libraries together with their complete transitive MOOSE/PETSc dependencies.
test -e /opt/physics/lib/libphysics-opt.so.0
test -e /opt/physics/test/lib/libphysics_test-opt.so.0
export LD_LIBRARY_PATH="/opt/physics/test/lib:/opt/physics/lib:${LD_LIBRARY_PATH:-}"

# One ldd invocation on the final executable is sufficient for the ELF loader's
# complete transitive NEEDED closure.
ldd /opt/physics/physics-opt > "$LDD_OUTPUT"
if grep -Fq 'not found' "$LDD_OUTPUT"; then
  cat "$LDD_OUTPUT" >&2
  echo "Unresolved dynamic dependency in physics-opt" >&2
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
# the executable's static ELF dependency graph. Keep only the OpenMPI runtime
# surface; static archives and development headers are not copied wholesale.
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

# WP8 bounded optimization: the measured runtime copy of PETSc + libMesh carried
# ~404 MB of removable debug sections. Strip debug sections only from the copied
# closure. The build-base artifacts and canonical application binaries remain
# untouched. Dynamic symbols and executable code are preserved.
command -v readelf >/dev/null
command -v strip >/dev/null
petsc_before="$(bytes_of "$DEST/opt/petsc")"
libmesh_before="$(bytes_of "$DEST/opt/libmesh")"
strip_debug_tree "$DEST/opt/petsc"
strip_debug_tree "$DEST/opt/libmesh"
petsc_after="$(bytes_of "$DEST/opt/petsc")"
libmesh_after="$(bytes_of "$DEST/opt/libmesh")"
strip_saved="$((petsc_before + libmesh_before - petsc_after - libmesh_after))"

# Generate the dynamic-loader configuration and cache while build tooling is
# still available. The final scratch image contains neither ldconfig nor a shell,
# so the cache must be complete before the closure becomes the image rootfs.
sort -u "$LIBDIRS_FILE" > "$DEST/etc/ld.so.conf.d/physics-runtime.conf"
printf '%s\n' 'include /etc/ld.so.conf.d/*.conf' > "$DEST/etc/ld.so.conf"
command -v ldconfig >/dev/null
ldconfig -r "$DEST"
test -s "$DEST/etc/ld.so.cache"

# Hard acceptance guard: MOOSE core data must be available through the exact
# installed path Registry::determineDataFilePath() checks first.
test -r "$DEST/opt/share/moose/data/README.md"

{
  echo "RUNTIME_ROOT_BYTES=$(du -sb "$DEST" | awk '{print $1}')"
  echo "RUNTIME_FILE_COUNT=$(find "$DEST" -type f | wc -l | tr -d ' ')"
  echo "ELF_DEPENDENCY_COUNT=$(awk '/=> \/[^ ]+/ {print $3} /^[[:space:]]*\/[^ ]+/ {print $1}' "$LDD_OUTPUT" | sort -u | wc -l | tr -d ' ')"
  echo "RUNTIME_STRIP_MODE=--strip-debug"
  echo "RUNTIME_STRIP_TARGETS=/opt/petsc,/opt/libmesh"
  echo "PETSC_BEFORE_BYTES=$petsc_before"
  echo "PETSC_AFTER_BYTES=$petsc_after"
  echo "LIBMESH_BEFORE_BYTES=$libmesh_before"
  echo "LIBMESH_AFTER_BYTES=$libmesh_after"
  echo "RUNTIME_STRIP_SAVED_BYTES=$strip_saved"
  echo "RUNTIME_LD_CACHE_PRECOMPUTED=true"
} > "$DEST/opt/physics/RUNTIME_CLOSURE.txt"

cat "$DEST/opt/physics/RUNTIME_CLOSURE.txt"
