#!/bin/sh
# Stage the minimal glibc runtime required by a jlink image into /rootfs-libs.
#
# Reusable across Dockerfiles (and CI): downstream sub-stages can then copy the
# runtime with a single, architecture independent `COPY --from=... /rootfs-libs /`.
#
# The triplet directory (e.g. x86_64-linux-gnu / aarch64-linux-gnu) and the ELF
# interpreter path (/lib64/ld-linux-x86-64.so.2 vs /lib/ld-linux-aarch64.so.1)
# are resolved at runtime from the JDK launcher, so the same script works on
# amd64 and arm64.
#
# Inputs are provided via environment variables:
#   JAVA_HOME    JDK install directory. Defaults to "/opt/java".
#   ROOTFS_LIBS  Output directory for the staged runtime. Defaults to
#                "/rootfs-libs".

set -eu

JAVA_HOME="${JAVA_HOME:-/opt/java}"
ROOTFS_LIBS="${ROOTFS_LIBS:-/rootfs-libs}"

JAVA_BIN="${JAVA_HOME}/bin/java"

triplet="$(dirname "$(ldd "${JAVA_BIN}" | awk '/libc\.so\.6/{print $3}')")"
interp="$(ldd "${JAVA_BIN}" | awk '/ld-linux/{print $1}')"

mkdir -p "${ROOTFS_LIBS}${triplet}" "${ROOTFS_LIBS}$(dirname "${interp}")" "${ROOTFS_LIBS}/etc"

for lib in libc.so.6 libm.so.6 libz.so.1 libdl.so.2 libpthread.so.0 librt.so.1 libnss_files.so.2; do
  cp -aL "${triplet}/${lib}" "${ROOTFS_LIBS}${triplet}/${lib}"
done

cp -aL "${interp}" "${ROOTFS_LIBS}${interp}"

printf 'passwd: files\ngroup: files\nhosts: files dns\n' > "${ROOTFS_LIBS}/etc/nsswitch.conf"
