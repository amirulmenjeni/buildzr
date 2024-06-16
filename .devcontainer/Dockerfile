FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# openjdk-21-jdk will be needed for Structurizr's C4 DSL language server.
RUN apt update && \
    apt install --no-install-recommends -y \
        openjdk-21-jdk