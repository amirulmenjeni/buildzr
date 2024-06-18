#!/bin/bash

wget https://github.com/structurizr/cli/releases/download/v2024.03.03/structurizr-cli.zip

unzip structurizr-cli.zip -d /opt/structurizr-cli

rm structurizr-cli.zip

ln -s /opt/structurizr-cli/structurizr.sh /usr/bin/structurizr.sh