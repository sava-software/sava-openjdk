#!/bin/sh
# Download, verify and install an OpenJDK build.
#
# Reusable across Dockerfiles (and CI): it encapsulates the logic for resolving
# the correct download URL for a GA or EA OpenJDK release, verifying its sha256
# checksum and extracting it into an install directory.
#
# Inputs are provided via environment variables. All are required (no defaults
# are baked in here); callers (Dockerfiles, CI) must supply them explicitly:
#   JAVA_VERSION       JDK version. GA: full version (e.g. "26.0.1").
#                      EA: major version (e.g. "27").
#   JAVA_BUILD         Build number (e.g. "8" for GA, "24" for EA).
#   JAVA_RELEASE_TYPE  "ga" or "ea".
#   JAVA_VERSION_HASH  GA only: the version hash in the download URL.
#   TARGETARCH         Docker target arch ("amd64"/"arm64") or "uname -m"
#                      values ("x86_64"/"aarch64").
#   JDK_SHA256_X64     Expected sha256 of the x64 download. Required unless
#                      JDK_SHA256 is supplied.
#   JDK_SHA256_AARCH64 Expected sha256 of the aarch64 download. Required unless
#                      JDK_SHA256 is supplied.
#   JDK_SHA256         Optional sha256 override that takes precedence over the
#                      per-architecture JDK_SHA256_X64/JDK_SHA256_AARCH64 values.
#   JAVA_HOME          Install directory.
#
# Example EA download URL:
#   https://download.java.net/java/early_access/jdk27/24/GPL/openjdk-27-ea+24_linux-aarch64_bin.tar.gz

set -eu

# These three are documented as optional (one of JDK_SHA256 or the per-arch
# pair must be supplied); allow them to be unset without tripping `set -u`.
JDK_SHA256="${JDK_SHA256:-}"
JDK_SHA256_X64="${JDK_SHA256_X64:-}"
JDK_SHA256_AARCH64="${JDK_SHA256_AARCH64:-}"

case "${TARGETARCH}" in
  amd64|x86_64) JDK_ARCH="x64" ;;
  arm64|aarch64) JDK_ARCH="aarch64" ;;
  *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;;
esac

# The expected checksums are supplied by the caller (e.g. the CI publish
# matrix). JDK_SHA256 overrides the per-architecture value when set.
if [ -z "${JDK_SHA256}" ]; then
  case "${JDK_ARCH}" in
    x64) JDK_SHA256="${JDK_SHA256_X64}" ;;
    aarch64) JDK_SHA256="${JDK_SHA256_AARCH64}" ;;
  esac
fi

# https://jdk.java.net/26/
if [ "${JAVA_RELEASE_TYPE}" = "ea" ]; then
  JDK_URL="https://download.java.net/java/early_access/jdk${JAVA_VERSION}/${JAVA_BUILD}/GPL/openjdk-${JAVA_VERSION}-ea+${JAVA_BUILD}_linux-${JDK_ARCH}_bin.tar.gz"
elif [ "${JAVA_RELEASE_TYPE}" = "ga" ]; then
  JDK_URL="https://download.java.net/java/GA/jdk${JAVA_VERSION}/${JAVA_VERSION_HASH}/${JAVA_BUILD}/GPL/openjdk-${JAVA_VERSION}_linux-${JDK_ARCH}_bin.tar.gz"
else
  echo "Unsupported JAVA_RELEASE_TYPE: ${JAVA_RELEASE_TYPE} (expected 'ga' or 'ea')" >&2
  exit 1
fi

if [ -z "${JDK_SHA256}" ]; then
  echo "No sha256 provided for ${JAVA_RELEASE_TYPE} jdk${JAVA_VERSION} (${JDK_ARCH}); set JDK_SHA256 or JDK_SHA256_X64/JDK_SHA256_AARCH64" >&2
  exit 1
fi

TMP_TARBALL="$(mktemp /tmp/openjdk.XXXXXX.tar.gz)"
trap 'rm -f "${TMP_TARBALL}"' EXIT

wget -q -O "${TMP_TARBALL}" "${JDK_URL}"
echo "${JDK_SHA256}  ${TMP_TARBALL}" | sha256sum -c -
mkdir -p "${JAVA_HOME}"
tar -xzf "${TMP_TARBALL}" -C "${JAVA_HOME}" --strip-components=1
