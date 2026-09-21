# syntax=docker/dockerfile:1.7

ARG MOOSE_DEV_TAG=2026.06.16
FROM idaholab/moose-dev:${MOOSE_DEV_TAG}

SHELL ["/bin/bash", "-lc"]

ARG MOOSE_DEV_TAG=2026.06.16
ARG MOOSE_SHA=9f388366ccf38b9c34542ec5561198249fde0ac9
ARG CRANE_SHA=ba26970cf419dcac563a20ed7079d445bc6341c3
ARG SQUIRREL_SHA=16a26d504f3ee11161a86d4e3ebf3c0e5f2afbb1
ARG ZAPDOS_SHA=9eceffbc46048c3760bbfa9a7f1ca681ae35af1d

LABEL org.opencontainers.image.title="Physics build base" \
      org.opencontainers.image.description="Precompiled MOOSE/modules and Physics dependency build surface" \
      org.opencontainers.image.source="https://github.com/HyungseonSong-plasma/moose-test-repo" \
      io.physics.moose-dev.tag="${MOOSE_DEV_TAG}" \
      io.physics.moose.sha="${MOOSE_SHA}" \
      io.physics.crane.sha="${CRANE_SHA}" \
      io.physics.squirrel.sha="${SQUIRREL_SHA}" \
      io.physics.zapdos.sha="${ZAPDOS_SHA}"

COPY Makefile /opt/physics-build-base/Makefile

RUN set -euxo pipefail; \
    source /environment; \
    mkdir -p /opt/physics_vendor; \
    clone_at() { \
      local url="$1" dst="$2" sha="$3"; \
      mkdir -p "$dst"; \
      git -C "$dst" init; \
      git -C "$dst" remote add origin "$url"; \
      git -C "$dst" fetch --depth 1 origin "$sha"; \
      git -C "$dst" checkout --detach FETCH_HEAD; \
      test "$(git -C "$dst" rev-parse HEAD)" = "$sha"; \
    }; \
    clone_at https://github.com/idaholab/moose.git /opt/physics_vendor/moose "$MOOSE_SHA"; \
    clone_at https://github.com/lcpp-org/crane.git /opt/physics_vendor/crane "$CRANE_SHA"; \
    clone_at https://github.com/arfc/squirrel.git /opt/physics_vendor/squirrel "$SQUIRREL_SHA"; \
    clone_at https://github.com/shannon-lab/zapdos.git /opt/physics_vendor/zapdos "$ZAPDOS_SHA"

RUN set -euxo pipefail; \
    source /environment; \
    git config --global --add safe.directory /opt/physics_vendor/moose; \
    git config --global --add safe.directory /opt/physics_vendor/crane; \
    git config --global --add safe.directory /opt/physics_vendor/squirrel; \
    git config --global --add safe.directory /opt/physics_vendor/zapdos; \
    export MOOSE_DIR=/opt/physics_vendor/moose; \
    export CRANE_DIR=/opt/physics_vendor/crane; \
    export SQUIRREL_DIR=/opt/physics_vendor/squirrel; \
    export ZAPDOS_DIR=/opt/physics_vendor/zapdos; \
    export METHOD=opt; \
    make -f /opt/physics-build-base/Makefile -j2; \
    test -e /opt/physics_vendor/squirrel/lib/libsquirrel-opt.la; \
    test -e /opt/physics_vendor/crane/lib/libcrane-opt.la; \
    test -e /opt/physics_vendor/zapdos/lib/libzapdos-opt.la; \
    printf '%s\n' \
      "MOOSE_DEV_TAG=${MOOSE_DEV_TAG}" \
      "MOOSE_SHA=${MOOSE_SHA}" \
      "CRANE_SHA=${CRANE_SHA}" \
      "SQUIRREL_SHA=${SQUIRREL_SHA}" \
      "ZAPDOS_SHA=${ZAPDOS_SHA}" \
      > /opt/physics-build-base/BUILD_BASE_PROVENANCE.txt

WORKDIR /opt/physics-build-base
