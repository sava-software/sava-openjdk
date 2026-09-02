# sava-openjdk

A small, reusable set of **OpenJDK images** whose purpose is to provide a
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

The images are published to both registries (identical tag sets):

- **GitHub Container Registry:** `ghcr.io/sava-software/sava-openjdk`
- **Docker Hub:** `jpe7s/sava-openjdk`

## Contents

Each published tag combines the OpenJDK version with the OS / OS version. The
currently published tags are:

| Release | Variant  | Tag                       |
|---------|----------|---------------------------|
| GA      | `debian` | `26.0.2.1-debian-trixie`  |
| GA      | `alpine` | `26.0.2.1-alpine-3.24`    |
| EA      | `debian` | `27-ea34-debian-trixie`   |
| EA      | `alpine` | `27-ea34-alpine-3.24`     |

Common properties across all tags:

| Property        | Value                                              |
|-----------------|----------------------------------------------------|
| Base            | `debian:trixie` / `alpine:3.24` (pinned by digest) |
| OpenJDK source  | jdk.java.net (GA `26.0.2.1`, EA `27-ea+34`)        |
| `JAVA_HOME`     | `/opt/java`                                        |
| Architectures   | `linux/amd64`, `linux/arm64`                       |

## Usage

Pull from either registry — the tag sets are identical:

```dockerfile
# GitHub Container Registry
FROM ghcr.io/sava-software/sava-openjdk:26.0.2.1-debian-trixie
# ...or Docker Hub
# FROM jpe7s/sava-openjdk:26.0.2.1-debian-trixie
# java, javac, jlink, ... are already on PATH and JAVA_HOME is set
```

## Building locally

Every JDK build arg is required (the `Dockerfile` declares them without
defaults); the values below are the GA entry of the CI publish matrix. The
sha256 checksum is supplied per architecture so the download is verified:
`install-jdk.sh` selects the one matching the build's `TARGETARCH`, and you may
pass a single `JDK_SHA256` to override both.

```bash
JDK_ARGS=(
  --build-arg JAVA_RELEASE_TYPE=ga
  --build-arg JAVA_VERSION=26.0.2.1
  --build-arg JAVA_BUILD=1
  --build-arg JAVA_VERSION_HASH=3b8e6c7ec6274148a7aa15e7e7dfb53c
  --build-arg JDK_SHA256_X64=a1489256029b389ce6ee52da0de1d01496c5df1776d6870241fe4823b998ea61
  --build-arg JDK_SHA256_AARCH64=b96b265a4a1a36c02454148891aa58ca63303cbc2d1b7979c33b4fe99e09117b
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
  --build-arg JAVA_VERSION=27 \
  --build-arg JAVA_BUILD=34 \
  --build-arg JDK_SHA256_X64=e82f0b585355fa9b8aa309711cb67afa0d87a6c4ddc5d583951a412e46512f08 \
  --build-arg JDK_SHA256_AARCH64=fd51c0306ecd1d15e2e9f9bf91c7b339c7194517de3d9a46eb9007a340cf046e \
  --target debian \
  -t sava-openjdk:local .
```

This corresponds to download URLs such as
`https://download.java.net/java/early_access/jdk27/34/GPL/openjdk-27-ea+34_linux-aarch64_bin.tar.gz`.

### Reusable installation script

The download/verify/extract logic lives in
[`scripts/install-jdk.sh`](./scripts/install-jdk.sh) so it can be reused by
other Dockerfiles (or run directly in CI). It resolves the GA/EA download URL,
verifies the sha256 checksum and extracts the JDK into `JAVA_HOME`. Inputs are
provided via environment variables:

| Variable            | Purpose                                                                             |
|---------------------|-------------------------------------------------------------------------------------|
| `JAVA_VERSION`      | JDK version. GA: full (e.g. `26.0.2.1`). EA: major (e.g. `27`). Required.          |
| `JAVA_BUILD`        | Build number (e.g. `1` for GA, `34` for EA). Required.                              |
| `JAVA_RELEASE_TYPE` | `ga` or `ea`. Required.                                                             |
| `JAVA_VERSION_HASH` | GA only: the version hash in the download URL. Required for `ga`.                   |
| `TARGETARCH`         | `amd64`/`arm64` or `x86_64`/`aarch64`. Required.                                    |
| `JDK_SHA256_X64`     | Expected sha256 of the x64 download. Required (unless `JDK_SHA256` is set).         |
| `JDK_SHA256_AARCH64` | Expected sha256 of the aarch64 download. Required (unless `JDK_SHA256` is set).     |
| `JDK_SHA256`         | Optional checksum override taking precedence over the per-arch values.             |
| `JAVA_HOME`          | Install directory. Required.                                                        |

To reuse it in another Dockerfile:

```dockerfile
# BuildKit populates TARGETARCH once it is declared; the script reads JAVA_HOME
# as the install directory.
ARG TARGETARCH
ENV JAVA_HOME=/opt/java
COPY scripts/install-jdk.sh /usr/local/bin/install-jdk.sh
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    JAVA_RELEASE_TYPE=ga JAVA_VERSION=26.0.2.1 JAVA_BUILD=1 \
    JAVA_VERSION_HASH=3b8e6c7ec6274148a7aa15e7e7dfb53c \
    JDK_SHA256_X64=a1489256029b389ce6ee52da0de1d01496c5df1776d6870241fe4823b998ea61 \
    JDK_SHA256_AARCH64=b96b265a4a1a36c02454148891aa58ca63303cbc2d1b7979c33b4fe99e09117b \
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

Each image tag combines the JDK version with the OS / OS version, producing the
four published tags listed in the [Contents](#contents) table. The same tag set
is pushed to both GHCR (`ghcr.io/sava-software/sava-openjdk`) and Docker Hub
(`jpe7s/sava-openjdk`).

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
