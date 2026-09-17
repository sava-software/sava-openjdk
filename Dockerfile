# syntax=docker/dockerfile:1

# Single Dockerfile with a shared OpenJDK build stage and two interchangeable
# final runtime targets. Select which one to build with `--target`, and supply
# the required JDK build args (see "Building locally" in README.md for the
# JDK_ARGS array):
#
#   docker build --target debian "${JDK_ARGS[@]}" -t sava-openjdk:debian .   # debian:trixie runtime
#   docker build --target alpine "${JDK_ARGS[@]}" -t sava-openjdk:alpine .   # alpine + jlink runtime
#
# Without `--target`, the last stage (alpine) is built. The shared `jdk` stage
# (below) downloads, verifies and extracts the JDK and stages the minimal glibc
# runtime into /rootfs-libs (plus the C++ runtime into /rootfs-cxx-libs, which
# only alpine copies); the final stages copy only those artifacts so the
# published images carry no build tooling.

# https://www.debian.org/releases/
FROM debian:trixie@sha256:f324c7ff54321e8d9c588493a20244965938ce0aa50bbd1022d38010e9ffc4b1 AS jdk

# Build args are intentionally declared without defaults; the values for the
# currently published builds live in the CI publish matrix
# (.github/workflows/publish.yml). Supply each of them with --build-arg.
ARG JAVA_VERSION
ARG JAVA_BUILD
# Release channel: "ga" (General Availability) or "ea" (Early Access).
ARG JAVA_RELEASE_TYPE
# Only used for GA releases; EA download URLs do not include a version hash.
ARG JAVA_VERSION_HASH
ARG TARGETARCH
# Expected sha256 checksums of the JDK download, supplied per architecture by
# the caller (e.g. the CI publish matrix); install-jdk.sh selects the one
# matching TARGETARCH. JDK_SHA256 is an optional override for both.
ARG JDK_SHA256_X64=""
ARG JDK_SHA256_AARCH64=""
ARG JDK_SHA256=""

ENV JAVA_HOME=/opt/java

COPY scripts/install-jdk.sh /usr/local/bin/install-jdk.sh

RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    /usr/local/bin/install-jdk.sh

COPY scripts/stage-rootfs-libs.sh /usr/local/bin/stage-rootfs-libs.sh

# /rootfs-cxx-libs is only copied into the alpine runtime (see below).
RUN ROOTFS_CXX_LIBS=/rootfs-cxx-libs /usr/local/bin/stage-rootfs-libs.sh

# --- final: debian runtime ---
FROM debian:trixie@sha256:f324c7ff54321e8d9c588493a20244965938ce0aa50bbd1022d38010e9ffc4b1 AS debian

ENV JAVA_HOME=/opt/java
ENV PATH="${JAVA_HOME}/bin:${PATH}"

COPY --from=jdk /opt/java /opt/java
# glibc C runtime required by the (glibc) JDK launcher and libjvm, staged by the
# jdk stage at architecture correct paths. The debian base already provides
# glibc at its absolute paths, so the staged copy stays under /rootfs-libs for
# downstream jlink runtime stages to copy wholesale
# (e.g. `COPY --from=<this image> /rootfs-libs/ /`).
COPY --from=jdk /rootfs-libs/ /rootfs-libs/

RUN mkdir -p /rootfs/tmp && chmod 1777 /rootfs/tmp

CMD [ "java", "--version" ]

# --- final: alpine runtime ---
FROM alpine:3.24@sha256:e7c4abb69531cb09e2a2bbb56fad3367ab694865c49df898c1c683185cc4376c AS alpine

ENV JAVA_HOME=/opt/java
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# binutils provides "objcopy", required by jlink's --strip-debug to remove native debug symbols.
#RUN apk add --no-cache binutils

COPY --from=jdk /opt/java /opt/java
# glibc C runtime required by the (glibc) JDK launcher and libjvm, staged by the
# jdk stage at architecture correct paths. Keep it under /rootfs-libs and then
# symlink every staged file to its corresponding absolute path under / so the
# ELF interpreter and libraries are reachable (e.g. /lib64/ld-linux-x86-64.so.2)
# while the originals remain isolated in /rootfs-libs.
#
# /rootfs-cxx-libs adds the C++ runtime (libstdc++.so.6, libgcc_s.so.1)
# the same way. The JDK does not need it, but Gradle's native integration does:
# its linux-aarch64 libnative-platform.so links both, and without them Gradle
# runs with native services disabled ("There is no native integration with this
# operating environment") and cannot auto-provision a daemon JVM ("Service
# 'SystemInfo' is not available").
COPY --from=jdk /rootfs-libs/ /rootfs-libs/
COPY --from=jdk /rootfs-cxx-libs/ /rootfs-cxx-libs/
RUN set -eux; \
    for root in /rootfs-libs /rootfs-cxx-libs; do \
      cd "${root}"; \
      find . \( -type f -o -type l \) | while IFS= read -r f; do \
        rel="${f#./}"; \
        mkdir -p "/$(dirname "${rel}")"; \
        ln -sf "${root}/${rel}" "/${rel}"; \
      done; \
    done

# Gradle detects the Alpine OS as musl and loads its musl native file-events
# library (.../<arch>-linux-musl/libgradle-fileevents.so), which links the
# unversioned "libc.so". Alpine only ships the SONAME (libc.musl-<arch>.so.1),
# so provide a "libc.so" symlink to musl libc; without it Gradle fails to
# initialise its native services under the (glibc) JDK.
RUN set -eux; for musl in /lib/ld-musl-*.so.1; do ln -sf "${musl}" /lib/libc.so; done

RUN mkdir -p /rootfs/tmp && chmod 1777 /rootfs/tmp

CMD [ "java", "--version" ]
