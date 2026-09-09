FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

ARG USER_UID
RUN if [ -n "$USER_UID" ]; then usermod -u "${USER_UID}" vscode; fi

ENV DEBIAN_FRONTEND=noninteractive

# openjdk-21-jdk will be needed for Structurizr's C4 DSL language server.
RUN apt update && \
    apt install --no-install-recommends -y \
        openjdk-21-jdk \
        graphviz

COPY  deps/install_structurizr_cli.sh ./
RUN chmod +x install_structurizr_cli.sh
RUN ./install_structurizr_cli.sh

COPY deps/install_structurizr_lite.sh deps/structurizr-lite.sh ./
RUN chmod +x install_structurizr_lite.sh && \
    ./install_structurizr_lite.sh

COPY deps/structurizr-onpremises.sh /usr/local/bin/structurizr-onpremises.sh
RUN chmod +x /usr/local/bin/structurizr-onpremises.sh

# Install uv system-wide so the devcontainer and CI use the same tool.
RUN curl -LsSf https://astral.sh/uv/install.sh | \
    env UV_INSTALL_DIR=/usr/local/bin sh -s -- --version 0.12.11

USER vscode
ENV PATH="/home/vscode/.local/bin:$PATH"

# uv manages the project environment and CLI tools consistently with CI.

# For building and versioning the package.
RUN uv tool install hatch==1.18.0

# Required for the `buildzr/models/generate.sh` script, for generating `models.py`.
RUN uv tool install datamodel-code-generator==0.26.2
RUN uv tool install yq==3.4.3