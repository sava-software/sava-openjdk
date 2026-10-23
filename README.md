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

From release 27.0.2, each image is published once to every configured registry
with the same tag and digest:

- **GitHub Container Registry:** `ghcr.io/sava-software/sava-openjdk`
- **Docker Hub:** `jpe7s/sava-openjdk`

## Contents

Each release publishes one image per entry of the build matrix in
[`.github/workflows/publish.yml`](./.github/workflows/publish.yml): a GA and an EA
JDK build, each for the `debian` and `alpine` targets. Tags have the form
`<release>-jdk<jdk>-<os>`:

| Segment    | Value                                        | Examples                       |
|------------|----------------------------------------------|--------------------------------|
| `release`  | The sava-openjdk release version, `X.Y.Z`    | `27.0.2`                       |
| `jdk` (GA) | The full JDK version, with any update digits | `27`                           |
| `jdk` (EA) | `<major>-ea<build>`                          | `28-ea18`                      |
| `os`       | The base image's name and tag, joined by `-` | `debian-trixie`, `alpine-3.24` |

For example, release 27.0.2 (2026-10-06) published:

| JDK channel | Variant  | Tag                               |
|-------------|----------|-----------------------------------|
| GA          | `debian` | `27.0.2-jdk27-debian-trixie`      |
| GA          | `alpine` | `27.0.2-jdk27-alpine-3.24`        |
| EA          | `debian` | `27.0.2-jdk28-ea18-debian-trixie` |
| EA          | `alpine` | `27.0.2-jdk28-ea18-alpine-3.24`   |

Later releases can carry newer JDK builds and base images; the current tags are
listed on
[GHCR](https://github.com/sava-software/sava-openjdk/pkgs/container/sava-openjdk)
and [Docker Hub](https://hub.docker.com/r/jpe7s/sava-openjdk/tags).

These tags are never moved. There are no floating or `latest` tags.

Common properties of the release-versioned images:

| Property       | Value                                                               |
|----------------|---------------------------------------------------------------------|
| Base           | Debian or Alpine, pinned by digest; the tag's `os` segment names it |
| OpenJDK source | jdk.java.net; the tag's `jdk` segment names the build               |
| `JAVA_HOME`    | `/opt/java`                                                         |
| Locale         | `LANG=C.UTF-8`                                                      |
| Architectures  | `linux/amd64`, `linux/arm64`                                        |

## Usage

Pull a tag of the newest release (see [Contents](#contents)) from either registry:

```dockerfile
# GitHub Container Registry
FROM ghcr.io/sava-software/sava-openjdk:<tag>
# ...or Docker Hub
# FROM jpe7s/sava-openjdk:<tag>
# java, javac, jlink, ... are already on PATH and JAVA_HOME is set
```

For a digest pin, append `@sha256:<digest>` to the full `image:tag` reference,
using the published index digest. The tag records the release; the digest pins
the exact image.

A release that rebuilds the same JDK on the same base image tags changes only
the leading release version, which Dependabot and Renovate can follow in a literal
`FROM` line. A JDK update, a new EA build or major, a new Alpine minor or a new
Debian codename changes a later segment and needs a manual edit.

### Legacy tags

Every tag from before 27.0.2 remains pullable and will never be updated: those
releases published tags without a release version, such as `27-debian-trixie`,
and no release writes them any more. The table records the 14 legacy tags as
both registries held them on 2026-10-23, from an anonymous read of their index
digests and `org.opencontainers.image.revision` labels. Other sections refer to
this table instead of repeating it.

| Tags                                             | JDK        | Built by release                 | UTF-8 locale              | `alpine` C++ runtime | `alpine` `/lib/libc.so` |
|--------------------------------------------------|------------|----------------------------------|---------------------------|----------------------|-------------------------|
| `26.0.1-debian-trixie`, `26.0.1-alpine-3.23`     | `26.0.1`   | 0.1.2                            | No                        | No                   | Yes                     |
| `27-ea24-debian-trixie`, `27-ea24-alpine-3.23`   | `27-ea+24` | 0.1.2                            | No                        | No                   | Yes                     |
| `26.0.2.1-debian-trixie`, `26.0.2.1-alpine-3.24` | `26.0.2.1` | 0.1.3                            | No                        | No                   | Yes                     |
| `27-ea34-debian-trixie`, `27-ea34-alpine-3.24`   | `27-ea+34` | 0.1.3                            | No                        | No                   | Yes                     |
| `28-ea17-debian-trixie`, `28-ea17-alpine-3.24`   | `28-ea+17` | 27.0.0                           | No                        | Yes                  | No                      |
| `27-debian-trixie`, `27-alpine-3.24`             | `27`       | Docker Hub: 27.0.0; GHCR: 27.0.1 | Docker Hub: no; GHCR: yes | Yes                  | No                      |
| `28-ea18-debian-trixie`, `28-ea18-alpine-3.24`   | `28-ea+18` | 27.0.1                           | Yes                       | Yes                  | No                      |

"UTF-8 locale" means that `LANG=C.UTF-8` is set and `/rootfs-libs` carries the
`C.utf8` locale data. `27-debian-trixie` and `27-alpine-3.24` differ between the
registries because Docker Hub's tag immutability refused the 27.0.1 release's GA
images, which reached GHCR only, so do not assume that a legacy tag has the same
digest on both registries. Gradle support follows the JDK major (see
[Gradle compatibility](#gradle-compatibility)).

## Gradle compatibility

Gradle runs its build daemon on a JVM, and each Gradle release only supports
running on JDKs up to a certain version (see Gradle's
[compatibility matrix](https://docs.gradle.org/current/userguide/compatibility.html)).
On a newer JDK, Groovy DSL build scripts and build logic compiled for that JDK
(such as Java `buildSrc` classes) fail with
`Unsupported class file major version`, so use a Gradle release that supports
running on the image's JDK.

Gradle's matrix, and so this table, is keyed by the JDK major: the first number
after `jdk` in a tag, such as `27` in `27.0.2-jdk27-debian-trixie` and `28` in
`27.0.2-jdk28-ea18-debian-trixie`, or the leading number of a
[legacy tag](#legacy-tags).

| JDK major | Gradle supported to run on it                                                                  |
|-----------|------------------------------------------------------------------------------------------------|
| 26        | 9.4.0 and later                                                                                |
| 27        | 9.8.0 and later; not checked on the legacy EA tags `27-ea24-*` and `27-ea34-*`                 |
| 28        | None as of 2026-10-23: Gradle 9.8.2 and the 9.10.0 nightly of that date fail on JDK `28-ea+21` |

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
   start the daemon on it. For Temurin 25 that was a ~140 MB download taking
   ~440 MB on disk when measured on 2026-09-15 (Gradle keeps the archive next to
   the extracted JDK), so cache the directory in CI.
3. Compilation also uses the daemon JDK unless you configure a
   [Java toolchain](https://docs.gradle.org/current/userguide/toolchains.html).
   Gradle 9.0 and later auto-detect the image's JDK from `JAVA_HOME`; on Gradle
   8.13 and 8.14 add `org.gradle.java.installations.fromEnv=JAVA_HOME` to
   `gradle.properties`.

The `alpine` images also ship the C++ runtime (`libstdc++.so.6`,
`libgcc_s.so.1`, see `ROOTFS_CXX_LIBS` below) because Gradle's native
integration needs it on arm64. Without it Gradle warns "There is no native
integration with this operating environment", disables file system watching and
cannot download a daemon JDK ("Service 'SystemInfo' is not available"). Some
legacy `alpine` tags do not include it (see [Legacy tags](#legacy-tags)).

The release-versioned `alpine` images carry no `/lib/libc.so` symlink to musl
(`/lib/ld-musl-<arch>.so.1`); some legacy `alpine` tags do (see
[Legacy tags](#legacy-tags)). Gradle does not use it with the image's glibc JDK: its
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
their native libraries without debug sections, so that part would remove nothing:
`--strip-java-debug-attributes` gives a runtime image of the same size without
objcopy. This was checked on both architectures for JDK 27 and 28-ea+17 on
2026-09-27 and for 27.0.1.0.2 and 28-ea+21 on 2026-10-23. On JDK 27 (aarch64) a
9-module runtime shrinks from 49.1 MB to 45.5 MB either way, all of it in
`lib/modules`.

Both options drop line numbers from stack traces (`Unknown Source`) for every
module linked into the image, your own included; leave both off to keep them.
If you want `--strip-debug` anyway, install `binutils` in your own build stage;
it added about 33 MB on Debian and 19 MB on Alpine when measured on 2026-09-27.

## Building locally

Supply the JDK build args with `--build-arg`: the `Dockerfile` declares the
version args without defaults (`JAVA_VERSION_HASH` is only used for GA), and
`install-jdk.sh` refuses to run without a checksum for the build's architecture.
Take the values from the GA or EA channel's `debian` entry in the
[publish matrix](./.github/workflows/publish.yml), where each value is typed
once. The sha256 checksum is supplied per architecture so the download is
verified: `install-jdk.sh` selects the one matching the build's `TARGETARCH`, and
you may pass a single `JDK_SHA256` to override both.

```bash
# Replace each <key> with that value of the matrix's GA debian entry.
JDK_ARGS=(
  --build-arg JAVA_RELEASE_TYPE=ga
  --build-arg JAVA_VERSION=<java_version>
  --build-arg JAVA_BUILD=<java_build>
  --build-arg JAVA_VERSION_HASH=<java_version_hash>
  --build-arg JDK_SHA256_X64=<jdk_sha256_x64>
  --build-arg JDK_SHA256_AARCH64=<jdk_sha256_aarch64>
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
Access** release instead, set `JAVA_RELEASE_TYPE=ea` and take `JAVA_VERSION` (the
JDK major), `JAVA_BUILD` and the per-architecture sha256 checksums from the EA
channel's `debian` entry (`JAVA_VERSION_HASH` is only used for GA downloads):

```bash
# Replace each <key> with that value of the matrix's EA debian entry.
docker build \
  --build-arg JAVA_RELEASE_TYPE=ea \
  --build-arg JAVA_VERSION=<java_version> \
  --build-arg JAVA_BUILD=<java_build> \
  --build-arg JDK_SHA256_X64=<jdk_sha256_x64> \
  --build-arg JDK_SHA256_AARCH64=<jdk_sha256_aarch64> \
  --target debian \
  -t sava-openjdk:local .
```

The `JDK_URL` lines of [`scripts/install-jdk.sh`](./scripts/install-jdk.sh) show
the download URL layout of both channels.

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

The examples show formats; the values CI builds are in the publish matrix.

To reuse it in another Dockerfile, declare the JDK build args as the `jdk` stage of
this repository's `Dockerfile` does and pass them with `--build-arg`:

```dockerfile
ARG JAVA_RELEASE_TYPE
ARG JAVA_VERSION
ARG JAVA_BUILD
ARG JAVA_VERSION_HASH
ARG JDK_SHA256_X64
ARG JDK_SHA256_AARCH64
ARG JDK_SHA256
# BuildKit populates TARGETARCH once it is declared; the script reads JAVA_HOME
# as the install directory.
ARG TARGETARCH
ENV JAVA_HOME=/opt/java
COPY scripts/install-jdk.sh /usr/local/bin/install-jdk.sh
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
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

The UTF-8 default changes Java's default locale from `en-US` to territory-neutral
`en`. Every release-versioned image has it, and so do the legacy tags that
[Legacy tags](#legacy-tags) marks. For example, default currency formatting uses
`¤` instead of `$`, and `Currency.getInstance(Locale.getDefault())` throws
because the locale has no country.
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

Legacy tags without the UTF-8 locale (see [Legacy tags](#legacy-tags)) omit the
`C.utf8` data from `/rootfs-libs`. Merely setting `LANG` in a scratch image made
from that older bundle is insufficient; update its pinned base image and rebuild.
This does not repair data previously created using an incorrectly decoded
password.

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
matrix builds **both** a GA and an EA JDK build for **both** runtime targets
(`debian` and `alpine`) as multi-arch images and pushes them to
GHCR and, when configured, Docker Hub on version tag pushes (`X.Y.Z`). All JDK
build args (`JAVA_RELEASE_TYPE`, `JAVA_VERSION`, `JAVA_BUILD`,
`JAVA_VERSION_HASH`, and the per-architecture `JDK_SHA256_X64` /
`JDK_SHA256_AARCH64` checksums) come from the matrix, where each JDK value is
typed once on a channel's `debian` entry and aliased by its `alpine` entry.

Pull requests, manual workflow runs and pushes to `main` that change a build input
(the `Dockerfile`, `.dockerignore`, `scripts/`, `tests/`, the publish workflow or
`.github/scripts/`) execute the same validation matrix without registry login or
publication. It checks both architectures of every GA/EA and Debian/Alpine
image, including each exported scratch runtime. The 600-second timeout
applies to Docker operations run inside `scripts/test-utf8.py`; it does not bound the
workflow's preceding Buildx build of each validation image. Each validation job has
a 30-minute overall limit. Tag publication waits for every validation entry to pass,
but a failure at that point spends the release version. Before merging a release
pull request, check that its own validation run passed; that run also checks the
new version's tags, as derived from the inputs it built, against every configured
registry. A later change to a build input on `main` gets its own validation run;
check that it passed too. That run repeats the builds and tests with the new
inputs but not the registry check, which the publish job makes again before
pushing. If the newest of these runs is old enough that a JDK download may have
moved, run the workflow manually on `main` first.

The version comes from the `"."` entry of `.release-please-manifest.json` and must
be `X.Y.Z`; on a tag push it must equal the Git tag. Each matrix entry renders its
tag, `<version>-jdk<jdk>-<os>`, once for use in checks and publication, and logs it
as `Image tag:`. `jdk` is the entry's `java_version` for GA and
`<java_version>-ea<java_build>` for EA. `os` is the image name and tag from the
target stage's `FROM <name>:<tag>@sha256:<digest> AS <target>` line, so a base
image update that changes the tag, such as `alpine:3.25`, also changes the image
tags. A `FROM` line in another form, or an invalid tag, fails before
metadata-action can rewrite it.

Before the QEMU/Buildx setup, an unreleased version (including a release PR's
merge ref) lists its full image references and anonymously checks that every
configured registry lacks those tags. A collision or an unreadable registry
blocks validation. A PR, manual run or push to `main` for an already released
version says it publishes nothing and skips this registry check; its runtime
checks still run. Tag pushes list the references and defer the registry check to
the publish job.

For each entry, the publish job checks every configured registry again before any
build:

| Registry state                                                 | First attempt  | Re-run (attempt > 1)                        |
|----------------------------------------------------------------|----------------|---------------------------------------------|
| Absent from every configured registry                          | Build and push | Build and push                              |
| Present on every configured registry with the same digest      | Fail           | Skip the build and push                     |
| Docker Hub only                                                | Fail           | Copy that digest to GHCR without rebuilding |
| GHCR only while Docker Hub is configured, or differing digests | Fail           | Fail; maintainer intervention required      |
| Registry cannot be read                                        | Fail           | Fail                                        |

Without Docker Hub, GHCR is the only configured registry, so a tag present on
GHCR counts as published. When Docker Hub is configured, it is listed before GHCR
for a new push, but recovery does not depend on push order. After a build or
copy attempt, even a failed one, the workflow waits briefly for visibility and
requires every configured registry to report the expected digest. A re-run never
rebuilds an entry already present on Docker Hub and never automatically copies
towards Docker Hub or overwrites a GHCR tag. Entries are independent, so a
failure in one does not undo the others.

Use **Re-run failed jobs** to finish a partially published entry. For a tag that
is on GHCR but missing from a configured Docker Hub, a maintainer must first read
`org.opencontainers.image.revision` on that image. Only if it matches the release
commit may the maintainer copy the image.
Before copying, authenticate to Docker Hub with push rights to the destination
repository (`docker login docker.io`). Copy by digest with
`docker buildx imagetools create --tag
<dockerhub>:<tag> <ghcr>@sha256:<digest>`, then re-run the failed jobs. Release
Git tags are never moved or pushed twice; do not re-run the failed 27.0.1 release
workflow against its legacy tags.

The shared checker is [`.github/scripts/image-state.sh`](./.github/scripts/image-state.sh).
It uses anonymous pull tokens and manifest HEAD requests, distinguishes an absent
tag from a registry error, and records each registry's status and digest in the
log and step summary. Run its local stub tests with
`python3 .github/scripts/test-image-state.py`.

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

### Bumping the JDK or base images

1. Pick the builds: the GA build that [jdk.java.net](https://jdk.java.net/) lists
   for the GA major, and the newest build on the early-access download path.
   Verify each tarball against its `.sha256` file and check its native libraries
   for `.debug_*` sections. Record both checks in the commit body, with the date
   and with how you established that the EA build was the newest.
2. Edit the anchored values of the GA or EA channel's `debian` entry in the
   matrix: `java_version`, `java_version_hash` (GA only), `java_build`,
   `jdk_sha256_x64` and `jdk_sha256_aarch64`. The `alpine` entries alias them,
   and the workflow derives the tags' `jdk` and `os` segments.
3. To refresh the base images, update the three `FROM` digests in the
   `Dockerfile` (both Debian stages use the same one), resolving each digest from
   the tag on its line, or merge Dependabot's update if its digest is still
   current. A `FROM` tag change, such as `alpine:3.25`, changes the image tags'
   `os` segment with no other edit.
4. Build both targets as in [Building locally](#building-locally), run
   `scripts/test-utf8.py` on both architectures, and check the new JDK with
   Gradle.
5. Edit this README only when a JDK major without a row enters the matrix (add a
   [Gradle](#gradle-compatibility) row), when Gradle support for a listed major
   changes (update its row and date), or when a build ships debug sections
   (revise [jlink](#jlink)). Examples in this README and in script comments show
   formats and are not updated.
6. A commit that moves the GA entries to a new JDK major ends with a
   `Release-As` footer, as described above.

The push to `main` runs the validation matrix. Before merging the release pull
request, check its validation as described under [Publishing](#publishing).

### Required repository configuration

Settings → *Secrets and variables* → *Actions*:

| Type     | Name                 | Purpose                                                                                             |
|----------|----------------------|-----------------------------------------------------------------------------------------------------|
| Variable | `DOCKERHUB_USERNAME` | Docker Hub namespace; may be an organisation variable. If unset, only GHCR is published.            |
| Variable | `DOCKERHUB_IMAGE`    | Optional Docker Hub repo, with optional `docker.io/` prefix. Defaults to `<username>/sava-openjdk`. |
| Secret   | `DOCKERHUB_TOKEN`    | Docker Hub access token with write scope.                                                           |

GHCR authentication uses the built-in `GITHUB_TOKEN`; no extra secret needed.
Both configured repositories must already exist and be public so the validation
job can check them anonymously. Docker Hub tag immutability must stay enabled as
the backstop against overwrites. GHCR has no equivalent setting; the workflow
enforces the same rule there. When `DOCKERHUB_USERNAME` is unset, the checker warns
that only GHCR was checked and GHCR-only publication remains supported.
