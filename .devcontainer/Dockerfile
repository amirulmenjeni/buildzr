FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

ARG USER_UID
RUN if [ -n "$USER_UID" ]; then usermod -u "${USER_UID}" vscode; fi

ENV DEBIAN_FRONTEND=noninteractive

# openjdk-21-jdk will be needed for Structurizr's C4 DSL language server.
RUN apt update && \
    apt install --no-install-recommends -y \
        openjdk-21-jdk \
        graphviz \
        pipx

COPY  deps/install_structurizr_cli.sh ./
RUN chmod +x install_structurizr_cli.sh
RUN ./install_structurizr_cli.sh

COPY deps/install_structurizr_lite.sh deps/structurizr-lite.sh ./
RUN chmod +x install_structurizr_lite.sh && \
    ./install_structurizr_lite.sh

USER vscode
ENV PATH="/root/.local/bin:$PATH"

# For building and versioning the package.
RUN pipx install hatch

# Required for the `buildzr/models/generate.sh` script, for generating `models.py`.
RUN pipx install datamodel-code-generator
RUN pipx install yq

RUN npm install -g @modelcontextprotocol/server-playwright
