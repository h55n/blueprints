FROM eclipse-temurin:25-jre-jammy@sha256:6a11121e5419a1eb4def2bba2f74a4c1b560395b9c26b52e37485d2bf58f7958
RUN apt-get update && apt-get install -y --no-install-recommends python3 curl ca-certificates git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN curl --fail --location --retry 2 https://github.com/kestra-io/kestra/releases/download/v2.0.4/kestra-2.0.4 -o kestra.jar \
 && echo '88ee8d44c3d4a234c9d04689e72b8ba903ae8f9f2c6ae5f94bad89f3bcd68513  kestra.jar' | sha256sum -c - \
 && curl --fail --location --retry 2 https://github.com/lycheeverse/lychee/releases/download/lychee-v0.24.2/lychee-x86_64-unknown-linux-musl.tar.gz -o lychee.tar.gz \
 && echo '73657a111819a30c47c08352896796f23d64e4eb2b3ed39b6d32149241566fc5  lychee.tar.gz' | sha256sum -c - \
 && tar -xzf lychee.tar.gz \
 && install lychee-x86_64-unknown-linux-musl/lychee /usr/local/bin/lychee \
 && rm -rf lychee.tar.gz lychee-x86_64-unknown-linux-musl \
 && mkdir plugins \
 && java -Xmx512m -jar kestra.jar plugins install --locally -p /app/plugins io.kestra.plugin:plugin-git:4.1.0 io.kestra.plugin:plugin-script-shell:1.11.0
COPY proof/config.yml /app/config.yml
ENTRYPOINT ["java", "-Xmx1g", "-jar", "/app/kestra.jar", "server", "local", "--no-tutorials", "--worker-thread=2", "-p", "/app/plugins", "-c", "/app/config.yml"]
