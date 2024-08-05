#!/bin/bash

wget https://github.com/structurizr/lite/archive/refs/tags/v2024.07.02.zip
wget https://github.com/structurizr/lite/releases/download/v2024.07.02/structurizr-lite.war

unzip v2024.07.02 -d /opt/structurizr-lite
mkdir -p /opt/structurizr-lite/build/libs
mv structurizr-lite.war /opt/structurizr-lite/build/libs
mv structurizr-lite.sh /opt/structurizr-lite

chmod +x /opt/structurizr-lite/structurizr-lite.sh
ln -s /opt/structurizr-lite/structurizr-lite.sh /usr/bin/structurizr-lite.sh && \
rm v2024.07.02.zip