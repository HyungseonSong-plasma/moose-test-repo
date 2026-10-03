ARG BUILD_BASE_REF
FROM ${BUILD_BASE_REF}

ARG REPOSITORY_SHA
ARG PHYSICS_SOURCE_MANIFEST_SHA256
ARG BUILD_BASE_REF

LABEL org.opencontainers.image.title="Physics JIT runtime" \
      org.opencontainers.image.description="Prebuilt Physics runtime retaining the build/JIT toolchain for AD FParser" \
      org.opencontainers.image.revision="${REPOSITORY_SHA}" \
      io.physics.source.owner="moose-test-repo/physics_app" \
      io.physics.source.manifest-sha256="${PHYSICS_SOURCE_MANIFEST_SHA256}" \
      io.physics.build-base.ref="${BUILD_BASE_REF}" \
      io.physics.jit.compiler.available="true"

RUN rm -rf /opt/physics
COPY physics_app /opt/physics

RUN /bin/bash -lc 'set -euxo pipefail; \
    source /environment; \
    export MOOSE_DIR=/opt/physics_vendor/moose; \
    export CRANE_DIR=/opt/physics_vendor/crane; \
    export SQUIRREL_DIR=/opt/physics_vendor/squirrel; \
    export ZAPDOS_DIR=/opt/physics_vendor/zapdos; \
    export METHOD=opt; \
    cd /opt/physics; \
    make -j4; \
    test -x physics-opt; \
    test -e lib/libphysics-opt.so.0; \
    test -e test/lib/libphysics_test-opt.so.0; \
    ./physics-opt --check-input -i ci/smoke.i'

ENV MOOSE_DIR=/opt/physics_vendor/moose \
    CRANE_DIR=/opt/physics_vendor/crane \
    SQUIRREL_DIR=/opt/physics_vendor/squirrel \
    ZAPDOS_DIR=/opt/physics_vendor/zapdos \
    METHOD=opt \
    LD_LIBRARY_PATH="/opt/physics/test/lib:/opt/physics/lib" \
    PATH="/opt/openmpi/bin:${PATH}"

COPY ci/physics-jit-runtime-image/entrypoint.sh /usr/local/bin/physics-jit-runtime-entrypoint
RUN chmod 0755 /usr/local/bin/physics-jit-runtime-entrypoint

WORKDIR /work
ENTRYPOINT ["/usr/local/bin/physics-jit-runtime-entrypoint"]
