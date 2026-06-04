# sava-openjdk

A small, reusable set of **OpenJDK base images** whose purpose is to provide a
JDK that works for **building Gradle projects** and **running `jlink`** to
produce custom runtime images. The image installs a verified OpenJDK build
under `/opt/java` and exposes it via `JAVA_HOME` / `PATH`, so downstream images
can simply `FROM` it instead of re-downloading and checksum-verifying the JDK on
every build.

The single [`Dockerfile`](./Dockerfile) defines one shared `jdk` build stage
(downloads, verifies and extracts the JDK and stages the minimal glibc runtime
into `/rootfs-libs`) followed by two interchangeable final runtime targets that
each copy only `/opt/java` and `/rootfs-libs` from it. Both target the two
intended workloads — building Gradle projects and running `jlink`:

- **`debian`**
- **`alpine`**

Select a variant with `docker build --target <name>`.

- **GitHub Container Registry:** `ghcr.io/sava-software/sava-openjdk`
- **Docker Hub:** `jpe7s/sava-openjdk`

## Contents

| Property        | Value                              |
|-----------------|------------------------------------|
| Base            | `debian:trixie` (pinned by digest) |
| OpenJDK version | `26.0.1` (GA, from jdk.java.net)   |
| `JAVA_HOME`     | `/opt/java`                        |
| Architectures   | `linux/amd64`, `linux/arm64`       |

## Usage

```dockerfile
FROM ghcr.io/sava-software/sava-openjdk:26.0.1-debian-trixie
# java, javac, jlink, ... are already on PATH and JAVA_HOME is set
```

Quick sanity check:

```bash
docker run --rm ghcr.io/sava-software/sava-openjdk:26.0.1-debian-trixie java --version
```

## Building locally

```bash
# debian runtime, single architecture (host)
docker build --target debian -t sava-openjdk:local .

# alpine/jlink runtime
docker build --target alpine -t sava-openjdk:local-alpine .

# multi-architecture
docker buildx build --target debian --platform linux/amd64,linux/arm64 -t sava-openjdk:local .
```

If `--target` is omitted, the last stage in the `Dockerfile` (`alpine`) is built.

The expected sha256 checksum of the download is **not** baked into the build
any more; supply it per architecture so the download is verified (the CI publish
matrix passes these). Override the JDK version and pass the checksums at build
time:

```bash
docker build --target debian \
  --build-arg JAVA_VERSION=26.0.1 \
  --build-arg JDK_SHA256_X64=2f2802d57b5fc414f1ddf6648ba12cc9a6454cf67b32ac95407c018f2e6ab0b0 \
  --build-arg JDK_SHA256_AARCH64=12a3649b2f4a0c9f6491d220bdd04b4fff07cae502b435aaff46eac0e36f4df1 \
  -t sava-openjdk:local .
```

`install-jdk.sh` selects the checksum matching the build's `TARGETARCH`; you may
also pass a single `JDK_SHA256` to override both.

### Early Access (EA) builds

By default the image downloads a **GA** release. To build against an **Early
Access** release instead, set `JAVA_RELEASE_TYPE=ea` and supply the matching
`JAVA_VERSION` (major), `JAVA_BUILD` and the per-architecture sha256 checksums:

```bash
docker build \
  --build-arg JAVA_RELEASE_TYPE=ea \
  --build-arg JAVA_VERSION=27 \
  --build-arg JAVA_BUILD=24 \
  --build-arg JDK_SHA256_X64=eb8d0fac160a096fc406b794465b245a8b40cb1b04bbb4c5824393cde263a8b5 \
  --build-arg JDK_SHA256_AARCH64=832ef5a271052b9065f2b5b7a63ecdbbd0363edd74228736bab7227b45b21a66 \
  --target debian \
  -t sava-openjdk:local .
```

This corresponds to download URLs such as
`https://download.java.net/java/early_access/jdk27/24/GPL/openjdk-27-ea+24_linux-aarch64_bin.tar.gz`.

### Reusable install script

The download/verify/extract logic lives in
[`scripts/install-jdk.sh`](./scripts/install-jdk.sh) so it can be reused by
other Dockerfiles (or run directly in CI). It resolves the GA/EA download URL,
verifies the sha256 checksum and extracts the JDK into `JAVA_HOME`. Inputs are
provided via environment variables:

| Variable            | Purpose                                                                             |
|---------------------|-------------------------------------------------------------------------------------|
| `JAVA_VERSION`      | JDK version. GA: full (e.g. `26.0.1`). EA: major (e.g. `27`). Defaults to `26.0.1`. |
| `JAVA_BUILD`        | Build number (e.g. `8` for GA, `24` for EA). Defaults to `8`.                       |
| `JAVA_RELEASE_TYPE` | `ga` (default) or `ea`.                                                             |
| `JAVA_VERSION_HASH` | GA only: the version hash in the download URL. Defaults to the GA build.            |
| `TARGETARCH`         | `amd64`/`arm64` or `x86_64`/`aarch64`. Defaults to `uname -m`.                      |
| `JDK_SHA256_X64`     | Expected sha256 of the x64 download. Required (unless `JDK_SHA256` is set).         |
| `JDK_SHA256_AARCH64` | Expected sha256 of the aarch64 download. Required (unless `JDK_SHA256` is set).     |
| `JDK_SHA256`         | Optional checksum override taking precedence over the per-arch values.             |
| `JAVA_HOME`          | Install directory. Defaults to `/opt/java`.                                         |

To reuse it in another Dockerfile:

```dockerfile
COPY scripts/install-jdk.sh /usr/local/bin/install-jdk.sh
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    JAVA_VERSION=26.0.1 JAVA_BUILD=8 \
    JDK_SHA256_X64=2f2802d57b5fc414f1ddf6648ba12cc9a6454cf67b32ac95407c018f2e6ab0b0 \
    JDK_SHA256_AARCH64=12a3649b2f4a0c9f6491d220bdd04b4fff07cae502b435aaff46eac0e36f4df1 \
    /usr/local/bin/install-jdk.sh
```

### Reusable rootfs-libs staging script

The logic that stages the minimal glibc runtime required by a `jlink` image
lives in [`scripts/stage-rootfs-libs.sh`](./scripts/stage-rootfs-libs.sh) so it
can be reused by other Dockerfiles (or run directly in CI). It resolves the
architecture triplet and ELF interpreter from the JDK launcher, then copies the
minimal shared libraries and a `nsswitch.conf` into an output directory that a
slim runtime stage can `COPY` wholesale. Inputs are provided via environment
variables:

| Variable      | Purpose                                                              |
|---------------|----------------------------------------------------------------------|
| `JAVA_HOME`   | JDK install directory. Defaults to `/opt/java`.                      |
| `ROOTFS_LIBS` | Output directory for the staged runtime. Defaults to `/rootfs-libs`. |

To reuse it in another Dockerfile:

```dockerfile
COPY scripts/stage-rootfs-libs.sh /usr/local/bin/stage-rootfs-libs.sh
RUN /usr/local/bin/stage-rootfs-libs.sh
```

## Publishing

Publishing is automated by
[`.github/workflows/publish.yml`](./.github/workflows/publish.yml). A build
matrix builds **both** a GA release and the latest EA release for **both**
runtime targets (`debian` and `alpine`) as multi-arch images and pushes them to
GHCR and Docker Hub on version tag pushes (`X.Y.Z`). All JDK build args
(`JAVA_RELEASE_TYPE`, `JAVA_VERSION`, `JAVA_BUILD`, `JAVA_VERSION_HASH`, and the
per-architecture `JDK_SHA256_X64` / `JDK_SHA256_AARCH64` checksums) are defined
explicitly per matrix entry.

Each image tag combines the JDK version with the OS / OS version, so the four
published tags are:

| Release | Target   | Tag                  |
|---------|----------|----------------------|
| GA      | `debian` | `26.0.1-debian-trixie` |
| GA      | `alpine` | `26.0.1-alpine-3.23`   |
| EA      | `debian` | `27-ea24-debian-trixie` |
| EA      | `alpine` | `27-ea24-alpine-3.23`   |

Update the `java_version`/`java_build`/`jdk_tag` and the
`jdk_sha256_x64`/`jdk_sha256_aarch64` values in the workflow matrix when bumping
the GA or EA release.

The workflow consumes the shared composite actions from
[`sava-software/sava-build`](https://github.com/sava-software/sava-build)
(`docker-setup` for QEMU + Buildx + registry login, and `docker-build-image`
for `metadata-action` + `build-push-action`). This keeps the pinned SHAs for the
third-party Docker actions in a single place (the `sava-build` repo); they are
referenced here as `…@main`.

### Required repository configuration

Settings → *Secrets and variables* → *Actions*:

| Type     | Name                 | Purpose                                                           |
|----------|----------------------|-------------------------------------------------------------------|
| Variable | `DOCKERHUB_USERNAME` | Docker Hub namespace. If unset, only GHCR is published.           |
| Variable | `DOCKERHUB_IMAGE`    | Optional full Docker Hub repo. Defaults to `<user>/sava-openjdk`. |
| Secret   | `DOCKERHUB_TOKEN`    | Docker Hub access token with write scope.                         |

GHCR authentication uses the built-in `GITHUB_TOKEN`; no extra secret needed.
