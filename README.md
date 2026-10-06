# sava-openjdk

A small, reusable set of **OpenJDK images** whose purpose is to provide a
JDK that works for **building Gradle projects** and **running `jlink`** to
produce custom runtime images. The image installs a verified OpenJDK build
under `/opt/java` and exposes it via `JAVA_HOME` / `PATH`, so downstream images
can simply `FROM` it instead of re-downloading and checksum-verifying the JDK on
every build.

The single [`Dockerfile`](./Dockerfile) defines one shared `jdk` build stage
(downloads, verifies and extracts the JDK, stages the glibc runtime and UTF-8 locale
into `/rootfs-libs` and the C++ runtime into `/rootfs-cxx-libs`) followed by two
interchangeable final runtime targets that each copy only `/opt/java` and
`/rootfs-libs` from it (`alpine` also copies `/rootfs-cxx-libs`). Both target
the two intended workloads — building Gradle projects and running `jlink`:

- **`debian`**
- **`alpine`**

Select a variant with `docker build --target <name>`.

The images are published to both registries (identical tag sets):

- **GitHub Container Registry:** `ghcr.io/sava-software/sava-openjdk`
- **Docker Hub:** `jpe7s/sava-openjdk`

## Contents

Each published tag combines the OpenJDK version with the OS / OS version. The
publish workflow produces these tags:

| Release | Variant  | Tag                     |
|---------|----------|-------------------------|
| GA      | `debian` | `27-debian-trixie`      |
| GA      | `alpine` | `27-alpine-3.24`        |
| EA      | `debian` | `28-ea18-debian-trixie` |
| EA      | `alpine` | `28-ea18-alpine-3.24`   |

Common properties across all tags:

| Property       | Value                                              |
|----------------|----------------------------------------------------|
| Base           | `debian:trixie` / `alpine:3.24` (pinned by digest) |
| OpenJDK source | jdk.java.net (GA `27`, EA `28-ea+18`)              |
| `JAVA_HOME`    | `/opt/java`                                        |
| Locale         | `LANG=C.UTF-8`                                     |
| Architectures  | `linux/amd64`, `linux/arm64`                       |

## Usage

Pull from either registry — the tag sets are identical:

```dockerfile
# GitHub Container Registry
FROM ghcr.io/sava-software/sava-openjdk:27-debian-trixie
# ...or Docker Hub
# FROM jpe7s/sava-openjdk:27-debian-trixie
# java, javac, jlink, ... are already on PATH and JAVA_HOME is set
```

## Gradle compatibility

Gradle runs its build daemon on a JVM, and each Gradle release only supports
running on JDKs up to a certain version (see Gradle's
[compatibility matrix](https://docs.gradle.org/current/userguide/compatibility.html)).
On a newer JDK, Groovy DSL build scripts and build logic compiled for that JDK
(such as Java `buildSrc` classes) fail with
`Unsupported class file major version`, so use a Gradle release that supports
running on the image's JDK:

| Image tags                      | JDK        | Gradle supported to run on it                                      |
|---------------------------------|------------|--------------------------------------------------------------------|
| `26.0.2.1-*` (previous release) | `26.0.2.1` | 9.4.0 and later                                                    |
| `27-*`                          | `27`       | 9.8.0 and later                                                    |
| `28-ea18-*`                     | `28-ea+18` | Not supported by Gradle 9.8.0 (checked 2026-10-06)                 |

With an older Gradle release, keep the daemon on a JDK it supports using
[daemon JVM criteria](https://docs.gradle.org/current/userguide/gradle_daemon.html#sec:daemon_jvm_criteria),
which Gradle 8.13 and later can download automatically:

1. On a JDK your Gradle release supports, with a toolchain resolver such as
   `org.gradle.toolchains.foojay-resolver-convention` (1.0.0 or later on
   Gradle 9) applied in the settings script, run
   `./gradlew updateDaemonJvm --jvm-version=<N>` for a Java version your Gradle
   release can run on (for example `25` on Gradle 9.1 and later), and commit the
   generated `gradle/gradle-daemon-jvm.properties`.
2. Builds in the image then download that JDK into `$GRADLE_USER_HOME/jdks` and
   start the daemon on it. For Temurin 25 that is a ~140 MB download taking
   ~440 MB on disk (Gradle keeps the archive next to the extracted JDK), so
   cache the directory in CI.
3. Compilation also uses the daemon JDK unless you configure a
   [Java toolchain](https://docs.gradle.org/current/userguide/toolchains.html).
   Gradle 9.0 and later auto-detect the image's JDK from `JAVA_HOME`; on Gradle
   8.13 and 8.14 add `org.gradle.java.installations.fromEnv=JAVA_HOME` to
   `gradle.properties`.

The `alpine` images also ship the C++ runtime (`libstdc++.so.6`,
`libgcc_s.so.1`, see `ROOTFS_CXX_LIBS` below) because Gradle's native
integration needs it on arm64. Without it Gradle warns "There is no native
integration with this operating environment", disables file system watching and
cannot download a daemon JDK ("Service 'SystemInfo' is not available"). Alpine
images published before this was added, such as `26.0.2.1-alpine-3.24` and
`27-ea34-alpine-3.24`, do not include it.

Those older Alpine images also carry a `/lib/libc.so` symlink to musl
(`/lib/ld-musl-<arch>.so.1`); `27-alpine-3.24`, `28-ea17-alpine-3.24` and later
Alpine images do not. Gradle does not use it with the image's glibc JDK: its
file-events library picks its musl build only when a file with `-musl-` in its
name is already mapped into the JVM that starts file watching, which happens
only if a derived image gets a musl-linked library loaded into that JVM. If
Gradle then fails with "Could not initialize native services", replace that
library with a glibc build, as `ROOTFS_CXX_LIBS` does for the C++ runtime, or
recreate the link with `ln -sf /lib/ld-musl-<arch>.so.1 /lib/libc.so`, which
lets musl load as a second C library in the JVM.

## jlink

The images do not include `objcopy` (binutils), so `jlink --strip-debug` and
`--strip-native-debug-symbols` fail with `Cannot run program "objcopy"`: on
Linux `--strip-debug` strips native debug symbols as well as Java debug
attributes, and the native part needs objcopy. The jdk.java.net builds ship
their native libraries without debug sections (checked for JDK 27 and 28-ea+17
on both architectures), so that part would remove nothing:
`--strip-java-debug-attributes` gives a runtime image of the same size without
objcopy. On JDK 27 (aarch64) a 9-module runtime shrinks from 49.1 MB to 45.5 MB
either way, all of it in `lib/modules`.

Both options drop line numbers from stack traces (`Unknown Source`) for every
module linked into the image, your own included; leave both off to keep them.
If you want `--strip-debug` anyway, install `binutils` in your own build stage;
it adds about 33 MB on Debian and 19 MB on Alpine.

## Building locally

Every JDK build arg is required (the `Dockerfile` declares them without
defaults); the values below are the GA entry of the CI publish matrix. The
sha256 checksum is supplied per architecture so the download is verified:
`install-jdk.sh` selects the one matching the build's `TARGETARCH`, and you may
pass a single `JDK_SHA256` to override both.

```bash
JDK_ARGS=(
  --build-arg JAVA_RELEASE_TYPE=ga
  --build-arg JAVA_VERSION=27
  --build-arg JAVA_BUILD=35
  --build-arg JAVA_VERSION_HASH=55ce5470a6294008af0057ff4626d0e5
  --build-arg JDK_SHA256_X64=95fc37eb3a18a27a26d5904c2d89d52bace8dafa9a078ca27f4747fbc4bf070b
  --build-arg JDK_SHA256_AARCH64=da4e9dde1fff90204739e969187bab4751bd59a2a1c479672e1a1810f7dd23ea
)

# debian runtime, single architecture (host)
docker build --target debian "${JDK_ARGS[@]}" -t sava-openjdk:local .

# alpine/jlink runtime
docker build --target alpine "${JDK_ARGS[@]}" -t sava-openjdk:local-alpine .

# multi-architecture
docker buildx build --target debian --platform linux/amd64,linux/arm64 "${JDK_ARGS[@]}" -t sava-openjdk:local .
```

If `--target` is omitted, the last stage in the `Dockerfile` (`alpine`) is built.

### Early Access (EA) builds

The examples above build a **GA** release. To build against an **Early
Access** release instead, set `JAVA_RELEASE_TYPE=ea` and supply the matching
`JAVA_VERSION` (major), `JAVA_BUILD` and the per-architecture sha256 checksums
(`JAVA_VERSION_HASH` is only used for GA downloads):

```bash
docker build \
  --build-arg JAVA_RELEASE_TYPE=ea \
  --build-arg JAVA_VERSION=28 \
  --build-arg JAVA_BUILD=18 \
  --build-arg JDK_SHA256_X64=9901071672629d07caff1d5d50db34cecabf36aa3336e9fad4dbed5e8876fa40 \
  --build-arg JDK_SHA256_AARCH64=2303bdc1f3afaebd79e81fbcf4d5ca707c9bc645170f0e3a328ba717f6916b9d \
  --target debian \
  -t sava-openjdk:local .
```

This corresponds to download URLs such as
`https://download.java.net/java/early_access/jdk28/18/GPL/openjdk-28-ea+18_linux-aarch64_bin.tar.gz`.

### Reusable installation script

The download/verify/extract logic lives in
[`scripts/install-jdk.sh`](./scripts/install-jdk.sh) so it can be reused by
other Dockerfiles (or run directly in CI). It resolves the GA/EA download URL,
verifies the sha256 checksum and extracts the JDK into `JAVA_HOME`. Inputs are
provided via environment variables:

| Variable             | Purpose                                                                           |
|----------------------|-----------------------------------------------------------------------------------|
| `JAVA_VERSION`       | JDK version. GA: full (e.g. `27` or `26.0.2.1`). EA: major (e.g. `28`). Required. |
| `JAVA_BUILD`         | Build number (e.g. `35` for GA, `18` for EA). Required.                           |
| `JAVA_RELEASE_TYPE`  | `ga` or `ea`. Required.                                                           |
| `JAVA_VERSION_HASH`  | GA only: the version hash in the download URL. Required for `ga`.                 |
| `TARGETARCH`         | `amd64`/`arm64` or `x86_64`/`aarch64`. Required.                                  |
| `JDK_SHA256_X64`     | Expected sha256 of the x64 download. Required (unless `JDK_SHA256` is set).       |
| `JDK_SHA256_AARCH64` | Expected sha256 of the aarch64 download. Required (unless `JDK_SHA256` is set).   |
| `JDK_SHA256`         | Optional checksum override taking precedence over the per-arch values.            |
| `JAVA_HOME`          | Install directory. Required.                                                      |

To reuse it in another Dockerfile:

```dockerfile
# BuildKit populates TARGETARCH once it is declared; the script reads JAVA_HOME
# as the install directory.
ARG TARGETARCH
ENV JAVA_HOME=/opt/java
COPY scripts/install-jdk.sh /usr/local/bin/install-jdk.sh
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    JAVA_RELEASE_TYPE=ga JAVA_VERSION=27 JAVA_BUILD=35 \
    JAVA_VERSION_HASH=55ce5470a6294008af0057ff4626d0e5 \
    JDK_SHA256_X64=95fc37eb3a18a27a26d5904c2d89d52bace8dafa9a078ca27f4747fbc4bf070b \
    JDK_SHA256_AARCH64=da4e9dde1fff90204739e969187bab4751bd59a2a1c479672e1a1810f7dd23ea \
    /usr/local/bin/install-jdk.sh
```

### Reusable rootfs-libs staging script

The logic that stages the glibc runtime required by a `jlink` image
lives in [`scripts/stage-rootfs-libs.sh`](./scripts/stage-rootfs-libs.sh) so it
can be reused by other Dockerfiles (or run directly in CI). It resolves the
architecture triplet and ELF interpreter from the JDK launcher, then copies the
shared libraries, `nsswitch.conf`, and the matching Debian `C.utf8` locale data
into an output directory that a slim runtime stage can `COPY` wholesale.
Missing locale data makes Java decode native strings such as environment
variables and console passwords as ASCII, even if `file.encoding` is UTF-8.
Inputs are provided via environment
variables:

| Variable          | Purpose                                                                                              |
|-------------------|------------------------------------------------------------------------------------------------------|
| `JAVA_HOME`       | JDK install directory. Defaults to `/opt/java`.                                                      |
| `ROOTFS_LIBS`     | Output directory for the staged runtime. Defaults to `/rootfs-libs`.                                 |
| `ROOTFS_CXX_LIBS` | Optional output directory for the C++ runtime (`libstdc++.so.6`, `libgcc_s.so.1`). Skipped if unset. |

The C++ runtime is kept out of `ROOTFS_LIBS` because the JDK does not need it.
The `jdk` stage writes it to `/rootfs-cxx-libs` and only the `alpine` target
copies it, for Gradle's native integration on arm64 (see
[Gradle compatibility](#gradle-compatibility)).

To reuse it in another Dockerfile:

```dockerfile
COPY scripts/stage-rootfs-libs.sh /usr/local/bin/stage-rootfs-libs.sh
RUN /usr/local/bin/stage-rootfs-libs.sh
```

The Debian and Alpine images select UTF-8 by default with `LANG=C.UTF-8` and
leave `LC_ALL` unset. Consumers can override `LANG` and supply the selected
locale's data. A consumer-supplied `LC_ALL` takes precedence over `LANG`.

Starting with release **27.0.1**, this changes Java's default locale from `en-US`
to territory-neutral `en`. The release republishes the existing `27-*` image tags
with this change, so consumers pulling those tags will adopt it on their next pull;
consumers pinning image digests control when they adopt it. For example, default
currency formatting uses `¤` instead of `$`, and
`Currency.getInstance(Locale.getDefault())` throws because the locale has no country.
Applications should select a locale explicitly for regional formatting. To retain
the previous US Java defaults while keeping native UTF-8 decoding, launch Java with
`-Duser.language=en -Duser.country=US`.

Downstream `FROM scratch` stages must select the locale themselves: `COPY`
transfers files, not the source image's environment. With a custom runtime
already built at `/app/runtime` in the `build` stage:

```dockerfile
FROM scratch
COPY --from=build /rootfs-libs/ /
# Copy the parent tree to preserve /tmp's mode 1777 for non-root processes.
COPY --from=build /rootfs/ /
COPY --from=build /app/runtime /opt/java
ENV LANG=C.UTF-8
ENTRYPOINT ["/opt/java/bin/java"]
```

Images from release **27.0.0 and earlier** omit the locale from `/rootfs-libs`.
Merely setting `LANG` in a scratch image made from that older bundle is insufficient;
update its pinned base image and rebuild. This does not repair data previously
created using an incorrectly decoded password.

### UTF-8 regression checks

After building an image locally, run:

```sh
python3 scripts/test-utf8.py sava-openjdk:local --platform linux/arm64
```

Use `linux/amd64` when testing that architecture. The checks require Python 3,
Docker Buildx, and native execution or emulation for the selected platform.
They test the base image and a derived scratch `jlink` runtime as UID/GID 10001,
asserting `/tmp` has mode 1777 and supports temporary-file creation, Java's native
encoding, and exact Unicode environment and console-password input through a real
terminal. They also check the default Java locale and the US-property override.
ASCII input remains a control; forcing `LANG=C`, alone or with `LC_ALL=C`, must
fail the native-encoding check. Test containers have networking disabled and use
only synthetic input. Probe failures report the image, platform, target, mode and
probe output, with synthetic input redacted. Temporary test images are removed after
the run; the supplied base image is retained.

## Publishing

Publishing is automated by
[`.github/workflows/publish.yml`](./.github/workflows/publish.yml). A build
matrix builds **both** a GA release and the latest EA release for **both**
runtime targets (`debian` and `alpine`) as multi-arch images and pushes them to
GHCR and Docker Hub on version tag pushes (`X.Y.Z`). All JDK build args
(`JAVA_RELEASE_TYPE`, `JAVA_VERSION`, `JAVA_BUILD`, `JAVA_VERSION_HASH`, and the
per-architecture `JDK_SHA256_X64` / `JDK_SHA256_AARCH64` checksums) are defined
explicitly per matrix entry.

Pull requests and manual workflow runs execute the same validation matrix without
registry login or publication. It checks both architectures of every GA/EA and
Debian/Alpine image, including each exported scratch runtime. The 600-second timeout
applies to Docker operations run inside `scripts/test-utf8.py`; it does not bound the
workflow's preceding Buildx build of each validation image. Each validation job has
a 30-minute overall limit. Tag publication waits for every validation entry to pass.
Use a pull request or manual run to exercise the gate in Actions before releasing.

Each image tag combines the JDK version with the OS / OS version, producing the
four tags listed in the [Contents](#contents) table. The same tag set
is pushed to both GHCR (`ghcr.io/sava-software/sava-openjdk`) and Docker Hub
(`jpe7s/sava-openjdk`).

Update the `java_version`/`java_build`/`java_version_hash` (GA only)/`jdk_tag`
and the `jdk_sha256_x64`/`jdk_sha256_aarch64` values in the workflow matrix when
bumping the GA or EA release.

Releases (the `X.Y.Z` tags) are numbered after the JDK line of the GA images:
the major version is the GA JDK major, so `27.0.0` and its successors publish
JDK 27 GA images. release-please (`always-bump-patch`) only bumps the patch, so
the commit that moves the GA matrix entries to a new JDK major must end with a
`Release-As: <major>.0.0` footer (for example `Release-As: 28.0.0`).

The publishing job consumes the shared composite actions from
[`sava-software/sava-build`](https://github.com/sava-software/sava-build)
(`docker-setup` for QEMU + Buildx + registry login, and `docker-build-image`
for `metadata-action` + `build-push-action`), referenced here as `…@main`.
The validation job uses pinned QEMU and Buildx actions directly because it needs
no registry login.

### Required repository configuration

Settings → *Secrets and variables* → *Actions*:

| Type     | Name                 | Purpose                                                           |
|----------|----------------------|-------------------------------------------------------------------|
| Variable | `DOCKERHUB_USERNAME` | Docker Hub namespace. If unset, only GHCR is published.           |
| Variable | `DOCKERHUB_IMAGE`    | Optional full Docker Hub repo. Defaults to `<user>/sava-openjdk`. |
| Secret   | `DOCKERHUB_TOKEN`    | Docker Hub access token with write scope.                         |

GHCR authentication uses the built-in `GITHUB_TOKEN`; no extra secret needed.
