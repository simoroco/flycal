#!/usr/bin/env bash
set -e

echo "=== FlyCal — Flight Calendar Comparator ==="
echo "Starting deployment..."

# Ensure data directory exists
mkdir -p ./data

# Pull latest image and start
docker compose pull
docker compose up -d

# Detect local IP
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || ipconfig getifaddr en0 2>/dev/null || echo "localhost")

echo "Waiting for the application to be ready..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:4444/api/health 2>/dev/null | grep -q '"ok"'; then
        echo ""
        echo "================================================"
        echo "  FlyCal is running!"
        echo ""
        echo "  Local:   http://localhost:4444"
        echo "  Network: http://${LOCAL_IP}:4444"
        echo "  API:     http://localhost:4444/api/docs"
        echo "================================================"
        echo ""
        echo "Logs:   docker compose logs -f"
        echo "Stop:   docker compose down"
        echo "Update: docker compose pull && docker compose up -d"
        exit 0
    fi
    printf "."
    sleep 2
done

echo ""
echo "Application did not respond within 60 seconds."
echo "Check logs with: docker compose logs -f"
exit 1
