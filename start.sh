#!/usr/bin/env bash
set -e

echo "=== FlyCal — Flight Calendar Comparator ==="
echo "Starting build and deployment..."

# Ensure data directory exists
mkdir -p ./data

# Build and start
docker compose up --build -d

echo "Waiting for the application to be ready..."
for i in $(seq 1 30); do
    if curl -ks https://localhost:4444/api/health 2>/dev/null | grep -q '"ok"'; then
        echo ""
        echo "================================================"
        echo "  FlyCal is running at https://localhost:4444"
        echo "  API docs: https://localhost:4444/api/docs"
        echo "================================================"
        echo ""
        echo "Accept the self-signed certificate in your browser."
        echo "Logs: docker compose logs -f"
        exit 0
    fi
    printf "."
    sleep 2
done

echo ""
echo "Application did not respond within 60 seconds."
echo "Check logs with: docker compose logs -f"
exit 1
