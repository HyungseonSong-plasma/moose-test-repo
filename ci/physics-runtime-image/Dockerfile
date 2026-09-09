# syntax=docker/dockerfile:1.7

FROM scratch

ARG BUILD_BASE_REF
ARG REPOSITORY_SHA
ARG PHYSICS_SOURCE_MANIFEST_SHA256
ARG MOOSE_SHA=9f388366ccf38b9c34542ec5561198249fde0ac9
ARG CRANE_SHA=ba26970cf419dcac563a20ed7079d445bc6341c3
ARG SQUIRREL_SHA=16a26d504f3ee11161a86d4e3ebf3c0e5f2afbb1
ARG ZAPDOS_SHA=9eceffbc46048c3760bbfa9a7f1ca681ae35af1d

LABEL org.opencontainers.image.title="Physics runtime" \
      org.opencontainers.image.description="Prebuilt Physics/MOOSE runtime for bounded CI validation" \
      org.opencontainers.image.source="https://github.com/HyungseonSong-plasma/moose-test-repo" \
      org.opencontainers.image.revision="${REPOSITORY_SHA}" \
      io.physics.source.owner="moose-test-repo/physics_app" \
      io.physics.source.manifest-sha256="${PHYSICS_SOURCE_MANIFEST_SHA256}" \
      io.physics.build-base.ref="${BUILD_BASE_REF}" \
      io.physics.moose.sha="${MOOSE_SHA}" \
      io.physics.crane.sha="${CRANE_SHA}" \
      io.physics.squirrel.sha="${SQUIRREL_SHA}" \
      io.physics.zapdos.sha="${ZAPDOS_SHA}" \
      io.physics.runtime.base="scratch" \
      io.physics.runtime.strip="petsc-libmesh-debug"

# runtime-root is already a complete dependency-driven root filesystem. Keep
# every absolute path unchanged so the ELF interpreter and precomputed loader
# cache remain valid without a distribution base image.
COPY runtime-root/ /

ENV PATH="/opt/openmpi/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    OMPI_ALLOW_RUN_AS_ROOT=1 \
    OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1

WORKDIR /work
ENTRYPOINT ["/opt/physics/physics-opt"]
