#!/usr/bin/env bash

# Structurizr On-Premises runner script
# Documentation: https://docs.structurizr.com/onpremises

CONTAINER_NAME="structurizr-onpremises"
DATA_DIR="${HOME}/.structurizr-onpremises"

show_help() {
    echo "Usage: structurizr-onpremises.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start     Start Structurizr On-Premises (default)"
    echo "  stop      Stop the running container"
    echo "  status    Show container status"
    echo "  logs      Show container logs"
    echo "  help      Show this help message"
    echo ""
    echo "Structurizr On-Premises will be available at http://localhost:8080"
    echo "Data is persisted in: ${DATA_DIR}"
}

start_container() {
    # Create data directory if it doesn't exist
    mkdir -p "${DATA_DIR}"

    # Check if container is already running
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Structurizr On-Premises is already running at http://localhost:8080"
        return 0
    fi

    # Remove stopped container if it exists
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        docker rm "${CONTAINER_NAME}" > /dev/null
    fi

    echo "Starting Structurizr On-Premises..."
    docker run -d \
        --name "${CONTAINER_NAME}" \
        -p 8080:8080 \
        -v "${DATA_DIR}:/usr/local/structurizr" \
        structurizr/onpremises

    if [ $? -eq 0 ]; then
        echo "Structurizr On-Premises started successfully!"
        echo "Access it at: http://localhost:8080"
        echo ""
        echo "Default credentials: structurizr / password"
        echo "Data directory: ${DATA_DIR}"
    else
        echo "Failed to start Structurizr On-Premises"
        return 1
    fi
}

stop_container() {
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Stopping Structurizr On-Premises..."
        docker stop "${CONTAINER_NAME}" > /dev/null
        docker rm "${CONTAINER_NAME}" > /dev/null
        echo "Stopped."
    else
        echo "Structurizr On-Premises is not running."
    fi
}

show_status() {
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Structurizr On-Premises is running"
        docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Status}}\t{{.Ports}}"
    else
        echo "Structurizr On-Premises is not running"
    fi
}

show_logs() {
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        docker logs -f "${CONTAINER_NAME}"
    else
        echo "No container found. Start it first with: structurizr-onpremises.sh start"
    fi
}

# Main
case "${1:-start}" in
    start)
        start_container
        ;;
    stop)
        stop_container
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
