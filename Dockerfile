# syntax=docker/dockerfile:1

# Single Dockerfile with a shared OpenJDK build stage and two interchangeable
# final runtime targets. Select which one to build with `--target`:
#
#   docker build --target debian -t sava-openjdk:debian .   # debian:trixie runtime
#   docker build --target alpine -t sava-openjdk:alpine .    # alpine + jlink runtime
#
# Without `--target`, the last stage (alpine) is built. The shared `jdk` stage
# (below) downloads, verifies and extracts the JDK and stages the minimal glibc
# runtime into /rootfs-libs; both final stages copy only those artifacts so the
# published images carry no build tooling.

# https://www.debian.org/releases/
FROM debian:trixie@sha256:4ae67669760b807c19f23902a3fd7c121a6a70cf2ae709035674b23e712e4d62 AS jdk

# Build args are intentionally declared without defaults; the default values
# (the currently published GA build) live in scripts/install-jdk.sh so they can
# be shared across stages. Override any of these with --build-arg.
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

RUN /usr/local/bin/stage-rootfs-libs.sh

# --- final: debian runtime ---
FROM debian:trixie@sha256:4ae67669760b807c19f23902a3fd7c121a6a70cf2ae709035674b23e712e4d62 AS debian

ENV JAVA_HOME=/opt/java
ENV PATH="${JAVA_HOME}/bin:${PATH}"

COPY --from=jdk /opt/java /opt/java
# glibc C runtime required by the (glibc) JDK launcher and libjvm, staged by the
# jdk stage at architecture correct paths. Copy it to / so the ELF interpreter
# and libraries land at their absolute paths (e.g. /lib64/ld-linux-x86-64.so.2).
COPY --from=jdk /rootfs-libs/ /rootfs-libs/

CMD [ "java", "--version" ]

# --- final: alpine runtime ---
FROM alpine:3.23@sha256:5b10f432ef3da1b8d4c7eb6c487f2f5a8f096bc91145e68878dd4a5019afde11 AS alpine

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
COPY --from=jdk /rootfs-libs/ /rootfs-libs/
RUN set -eux; \
    cd /rootfs-libs; \
    find . \( -type f -o -type l \) | while IFS= read -r f; do \
      rel="${f#./}"; \
      mkdir -p "/$(dirname "${rel}")"; \
      ln -sf "/rootfs-libs/${rel}" "/${rel}"; \
    done

# Gradle detects the Alpine OS as musl and loads its musl native file-events
# library (.../<arch>-linux-musl/libgradle-fileevents.so), which links the
# unversioned "libc.so". Alpine only ships the SONAME (libc.musl-<arch>.so.1),
# so provide a "libc.so" symlink to musl libc; without it Gradle fails to
# initialise its native services under the (glibc) JDK.
RUN set -eux; for musl in /lib/ld-musl-*.so.1; do ln -sf "${musl}" /lib/libc.so; done

CMD [ "java", "--version" ]
