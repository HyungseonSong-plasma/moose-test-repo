# syntax=docker/dockerfile:1.7

# Keep the exported closure in a scratch stage so runtime files are copied into
# their final locations exactly once. This avoids the previous 1.1 GB temporary
# COPY layer followed by a second copy-and-delete layer.
FROM scratch AS closure
COPY runtime-root/ /

FROM rockylinux/rockylinux:8.10

SHELL ["/bin/bash", "-lc"]

ARG BUILD_BASE_REF
ARG MOOSE_SHA=9f388366ccf38b9c34542ec5561198249fde0ac9
ARG CRANE_SHA=ba26970cf419dcac563a20ed7079d445bc6341c3
ARG SQUIRREL_SHA=16a26d504f3ee11161a86d4e3ebf3c0e5f2afbb1
ARG ZAPDOS_SHA=9eceffbc46048c3760bbfa9a7f1ca681ae35af1d
ARG QPX_SOURCE_SHA256=4f9973c9e8e2dc07be5b485338cc0e921578e0dc754bca90c499d0071f199e03

LABEL org.opencontainers.image.title="QPX runtime" \
      org.opencontainers.image.description="Prebuilt QPX/MOOSE runtime for bounded CI validation" \
      org.opencontainers.image.source="https://github.com/HyungseonSong-plasma/moose-test-repo" \
      io.qpx.build-base.ref="${BUILD_BASE_REF}" \
      io.qpx.moose.sha="${MOOSE_SHA}" \
      io.qpx.crane.sha="${CRANE_SHA}" \
      io.qpx.squirrel.sha="${SQUIRREL_SHA}" \
      io.qpx.zapdos.sha="${ZAPDOS_SHA}" \
      io.qpx.source.sha256="${QPX_SOURCE_SHA256}"

# Rocky uses /lib and /lib64 symlinks into /usr, so merge those closure trees
# directly into their canonical targets instead of copying over the symlinks.
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
