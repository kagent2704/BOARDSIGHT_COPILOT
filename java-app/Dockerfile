FROM eclipse-temurin:21-jdk AS build

WORKDIR /build

COPY src/main/java ./src/main/java
COPY src/main/resources ./src/main/resources

RUN mkdir -p build/classes \
    && find src/main/java -name "*.java" -print > java_sources.txt \
    && javac -d build/classes @java_sources.txt \
    && cp -r src/main/resources/. build/classes/ \
    && printf "Manifest-Version: 1.0\nMain-Class: com.boardsight.web.BoardSightWebApp\n" > build/manifest.mf \
    && jar --create --file build/boardsight.jar --manifest build/manifest.mf -C build/classes .

FROM eclipse-temurin:21-jre

WORKDIR /workspace

ENV JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8"

COPY --from=build /build/build/boardsight.jar /opt/boardsight/boardsight.jar

EXPOSE 8080

CMD ["sh", "-c", "java -jar /opt/boardsight/boardsight.jar --port ${PORT:-8080}"]
