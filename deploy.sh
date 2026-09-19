#!/bin/bash
service="docker"
set -euo pipefail

cd /mnt/d/candlesticks

if ! systemctl is-active "$service"
then
	systemctl start "$service"

echo "$service is started..."
else
echo "$service is already running"
fi

if ! git pull 
then
echo "ERROR: git pull failed deployement aborted"
exit 1
fi

if ! docker compose build 
then 
echo "ERROR: docker build failed deployment aborted"
exit 1
fi

docker compose up -d
sleep 10
docker compose ps

docker compose logs --tail 30 backend

echo "deployment completed successfully"
