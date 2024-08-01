# The structurizr lite only accept folder as an argument -- the folder
# _must_ has a file named workspace.json or workspace.dsl.

if [ -n "$1" ]; then
    IFS='.' read -a array <<< "$1"
    filename=${array[0]}
    extension=${array[1]}

    mkdir -p .tmp/${filename}

    cp $1 .tmp/${filename}/workspace.${extension}

    java \
        -Djdk.util.jar.enableMultiRelease=false \
        -jar /opt/structurizr-lite/build/libs/structurizr-lite.war \
        .tmp/${filename}
else
    echo "Usage: structurizr-lite.sh <path_to_workspace_dsl_or_json>"
    echo ""
    echo "Example: structurizr-lite.sh path/to/simple.dsl"
fi