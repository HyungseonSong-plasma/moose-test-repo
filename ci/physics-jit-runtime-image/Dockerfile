ARG BUILD_BASE_REF
FROM ${BUILD_BASE_REF}

ARG REPOSITORY_SHA
ARG PHYSICS_SOURCE_MANIFEST_SHA256

LABEL org.opencontainers.image.title="Physics JIT runtime" \
      org.opencontainers.image.description="Prebuilt Physics runtime retaining the build/JIT toolchain for AD FParser" \
      org.opencontainers.image.revision="${REPOSITORY_SHA}" \
      io.physics.source.owner="moose-test-repo/physics_app" \
      io.physics.source.manifest-sha256="${PHYSICS_SOURCE_MANIFEST_SHA256}" \
      io.physics.build-base.ref="${BUILD_BASE_REF}" \
      io.physics.jit.compiler.available="true"

RUN rm -rf /opt/physics
COPY physics_app /opt/physics

ENV MOOSE_DIR=/opt/physics_vendor/moose \
    CRANE_DIR=/opt/physics_vendor/crane \
    SQUIRREL_DIR=/opt/physics_vendor/squirrel \
    ZAPDOS_DIR=/opt/physics_vendor/zapdos \
    METHOD=opt \
    PATH="/opt/openmpi/bin:${PATH}"

WORKDIR /work
ENTRYPOINT ["/opt/physics/physics-opt"]
