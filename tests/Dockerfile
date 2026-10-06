ARG BASE_IMAGE=sava-openjdk:local
FROM ${BASE_IMAGE} AS prepared
COPY Utf8Probe.java /probe/Utf8Probe.java
RUN javac -d /probe/classes /probe/Utf8Probe.java && \
    jlink --add-modules java.base --strip-java-debug-attributes \
      --no-header-files --no-man-pages --output /probe/runtime

# Check the published image's inherited locale defaults.
FROM ${BASE_IMAGE} AS direct
COPY --from=prepared /probe/classes /probe/classes
ENTRYPOINT ["/opt/java/bin/java", "-cp", "/probe/classes", "Utf8Probe"]

# COPY exports files, not the base image's environment defaults.
FROM scratch AS scratch-runtime
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
COPY --from=prepared /rootfs-libs/ /
COPY --from=prepared /rootfs/tmp/ /tmp/
COPY --from=prepared /probe/runtime/ /opt/java/
COPY --from=prepared /probe/classes /probe/classes
ENTRYPOINT ["/opt/java/bin/java", "-cp", "/probe/classes", "Utf8Probe"]
