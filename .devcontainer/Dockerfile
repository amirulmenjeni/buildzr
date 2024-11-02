FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

ENV DEBIAN_FRONTEND=noninteractive

# openjdk-21-jdk will be needed for Structurizr's C4 DSL language server.
RUN apt update && \
    apt install --no-install-recommends -y \
        openjdk-21-jdk \
        graphviz \
        python3-hatchling

COPY  deps/install_structurizr_cli.sh .
RUN chmod +x install_structurizr_cli.sh
RUN ./install_structurizr_cli.sh

COPY deps/install_structurizr_lite.sh deps/structurizr-lite.sh .
RUN chmod +x install_structurizr_lite.sh && \
    ./install_structurizr_lite.sh