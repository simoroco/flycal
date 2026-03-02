#!/usr/bin/env bash
set -e

echo "=== FlyCal — Flight Calendar Comparator ==="
echo "Starting build and deployment..."

docker compose up --build -d

echo "Waiting for the application to be ready..."
for i in $(seq 1 30); do
    if curl -ks https://localhost:4444 > /dev/null 2>&1; then
        echo "✓ FlyCal is running at https://localhost:4444"
        exit 0
    fi
    sleep 2
done

echo "⚠ Application did not respond within 60 seconds. Check logs with: docker compose logs -f"
exit 1
