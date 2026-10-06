# Changelog

## [27.0.1](https://github.com/sava-software/sava-openjdk/compare/27.0.0...27.0.1) (2026-10-06)


### ⚠ BREAKING CHANGES

* **docker:** UTF-8 defaults change Java's default locale from en-US to en. Select a regional locale explicitly, or use -Duser.language=en -Duser.country=US to retain US Java defaults with native UTF-8 decoding.

### Features

* **docker:** refresh Debian base and update JDK 28 EA to build 18 ([92ecbf1](https://github.com/sava-software/sava-openjdk/commit/92ecbf1a8da6e54fdbd5dad9c61b95603c162b38))


### Bug Fixes

* **docker:** preserve scratch tmp permissions and strengthen runtime checks ([92c0277](https://github.com/sava-software/sava-openjdk/commit/92c02778238812f7ad097e44da221f5367d1839b))
* **docker:** preserve UTF-8 in base and scratch runtimes ([82b4c85](https://github.com/sava-software/sava-openjdk/commit/82b4c85602456ac4d85d8f20e6fd321a13b21d42))

## [27.0.0](https://github.com/sava-software/sava-openjdk/compare/0.1.3...27.0.0) (2026-09-27)


### ⚠ BREAKING CHANGES

* **docker:** alpine images no longer contain /lib/libc.so. A derived image that relies on it can load a glibc build of the musl-linked library instead, or recreate the link with `ln -sf /lib/ld-musl-<arch>.so.1 /lib/libc.so`.

### Features

* **docker:** bump OpenJDK EA to 28-ea+17, refresh base images ([207f335](https://github.com/sava-software/sava-openjdk/commit/207f335b5047ec82a188ca3333ec1e3f21b9af85))
* **docker:** bump OpenJDK to 27 GA and 28-ea+15 ([21fbdfa](https://github.com/sava-software/sava-openjdk/commit/21fbdfa95d638016394d86bbf5e97a7bb892e39e))


### Bug Fixes

* **docker:** drop the /lib/libc.so musl symlink from the alpine image ([31fc466](https://github.com/sava-software/sava-openjdk/commit/31fc46641390d5ad8b62856d7a8e30a7bab016c5))
* **docker:** stage the C++ runtime in the alpine image for Gradle on arm64 ([31de2ec](https://github.com/sava-software/sava-openjdk/commit/31de2ecd62cfdb3f5600f194e71cebcd23d3957a))

## [0.1.3](https://github.com/sava-software/sava-openjdk/compare/0.1.2...0.1.3) (2026-09-02)


### Features

* **docker:** bump OpenJDK to 26.0.2.1 GA and 27-ea+34, refresh base images ([9dd413f](https://github.com/sava-software/sava-openjdk/commit/9dd413fd276d067ffd091042fbb5b9292167e259))

## [0.1.2](https://github.com/sava-software/sava-openjdk/compare/0.1.1...0.1.2) (2026-06-05)


### Features

* **docker:** add Apache 2.0 license and ensure tmpfs directory setup ([0fc8ac9](https://github.com/sava-software/sava-openjdk/commit/0fc8ac9e163f999bddab14b54ed3349b9a7769d8))

## [0.1.1](https://github.com/sava-software/sava-openjdk/compare/0.1.0...0.1.1) (2026-06-04)


### Features

* **docker:** add reusable OpenJDK base images with CI automation ([9449fda](https://github.com/sava-software/sava-openjdk/commit/9449fda8fdf4d06aa5491cf8cfd71a7417c2df66))
