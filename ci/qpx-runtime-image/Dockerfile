# syntax=docker/dockerfile:1.7

FROM scratch AS closure
COPY runtime-root/ /

FROM rockylinux/rockylinux:8.10

SHELL ["/bin/bash", "-lc"]

ARG BUILD_BASE_REF
ARG REPOSITORY_SHA
ARG QPX_SOURCE_MANIFEST_SHA256
ARG MOOSE_SHA=9f388366ccf38b9c34542ec5561198249fde0ac9
ARG CRANE_SHA=ba26970cf419dcac563a20ed7079d445bc6341c3
ARG SQUIRREL_SHA=16a26d504f3ee11161a86d4e3ebf3c0e5f2afbb1
ARG ZAPDOS_SHA=9eceffbc46048c3760bbfa9a7f1ca681ae35af1d

LABEL org.opencontainers.image.title="QPX runtime" \
      org.opencontainers.image.description="Prebuilt QPX/MOOSE runtime for bounded CI validation" \
      org.opencontainers.image.source="https://github.com/HyungseonSong-plasma/moose-test-repo" \
      org.opencontainers.image.revision="${REPOSITORY_SHA}" \
      io.qpx.source.owner="moose-test-repo/qpx_app" \
      io.qpx.source.manifest-sha256="${QPX_SOURCE_MANIFEST_SHA256}" \
      io.qpx.build-base.ref="${BUILD_BASE_REF}" \
      io.qpx.moose.sha="${MOOSE_SHA}" \
      io.qpx.crane.sha="${CRANE_SHA}" \
      io.qpx.squirrel.sha="${SQUIRREL_SHA}" \
      io.qpx.zapdos.sha="${ZAPDOS_SHA}"

COPY --from=closure /opt/ /opt/
COPY --from=closure /usr/ /usr/
COPY --from=closure /lib64/ /usr/lib64/
COPY --from=closure /lib/ /usr/lib/
COPY --from=closure /etc/ld.so.conf.d/qpx-runtime.conf /etc/ld.so.conf.d/qpx-runtime.conf

RUN set -euxo pipefail; \
    test -s /etc/ld.so.conf.d/qpx-runtime.conf; \
    test -r /opt/share/moose/data/README.md; \
    ldconfig; \
    test -x /opt/qpx/qpx-opt; \
    /opt/qpx/qpx-opt --check-input -i /opt/qpx/ci/smoke.i

ENV PATH="/opt/openmpi/bin:${PATH}" \
    OMPI_ALLOW_RUN_AS_ROOT=1 \
    OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1

WORKDIR /work
ENTRYPOINT ["/opt/qpx/qpx-opt"]
