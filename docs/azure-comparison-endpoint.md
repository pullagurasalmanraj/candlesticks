# Azure VM comparison endpoint verification

Verified over SSH and HTTPS on 2026-10-18. No services were restarted, source or
proxy configurations changed, research jobs executed, or database records changed.

## Observed deployment

- VM: `candlesticks-dev-vm`, DNS
  `candlesticks-india.southafricanorth.cloudapp.azure.com`, IP `102.133.160.89`.
- Checkout: `/home/azureuser/candlesticks`, branch `develop`, commit `78e0822`.
- Azure Repos origin:
  `git@ssh.dev.azure.com:v3/candlesticks-dev-grp/candlesticks-dev/candlesticks-dev`.
- `candlesticks-backend` runs `python app.py` through Docker Compose. There is
  no `gunicorn.service`; the response identifies Werkzeug/Flask.
- Backend code is bind-mounted from the VM's `backend/` to `/app/backend`.
- Deployed `app.py` imports `comparison_bp` and registers it.
- The deployed route is
  `@comparison_bp.route("/api/offline/compare-entry-geometry", methods=["POST"])`.
- Docker Nginx serves ports 80/443. Port 80 redirects to HTTPS. In the HTTPS
  server, `/api/` proxies to `$backend_upstream`, mapped to `http://backend:8000`.
  The API path is preserved, no method override is configured, and timeouts
  are 900 seconds. `nginx -T` reported valid configuration.

## Actual HTTP checks

An HTTPS POST with `{"__route_probe":true}` returned **400 JSON** naming the
unsupported probe field, with `rows_written: 0`. The exact same response came
from Flask directly at `http://127.0.0.1:8000` **on the VM**. The unknown field is
rejected before database access. This proves both deployed registration and
public reverse-proxy POST routing.

GET currently returns **404 JSON**, not the reported 405. OPTIONS returns 200
with `Allow: HEAD, OPTIONS, GET, POST`; this union can include catch-all routing
and does not mean the comparison handler supports GET. The POST response and
the actual route declaration establish the method support.

No redeployment is currently needed to enable POST. A browser address-bar visit
does not test POST. In Postman use POST, the exact **HTTPS** URL without an extra
trailing slash, Body → raw → JSON, and Content-Type `application/json`. If a 405
persists, turn off automatic redirects while testing and inspect Postman's
Console for the actual request method, URL, response headers and redirect chain.
Do not switch to GET to work around a POST-method problem.

## Restart this existing deployment, if reloading code is necessary

Run these commands **inside the Azure VM**:

```bash
cd /home/azureuser/candlesticks
docker compose config --quiet
docker compose restart backend
docker compose ps backend nginx
docker compose logs --tail=50 backend
```

Python edits under the VM's `backend/` need this process restart because they are
bind-mounted and Flask runs with debug/reloading disabled. No Nginx restart or
database-container restart is required for this Python route change. There is
no Gunicorn systemd service to restart. If Python dependencies changed, rebuild
and recreate **backend only** instead:

```bash
docker compose up -d --no-deps --build backend
```

These instructions do not run migrations, recalibration, labeling or ML jobs.

## Deploy only these comparison files from the existing Azure remote

This is optional: the verified VM already contains the endpoint. First push the
intended comparison changes to the Azure `develop` branch. On the VM, inspect
the diff before replacing the three application files:

```bash
cd /home/azureuser/candlesticks
git status --short
git fetch origin develop
git diff -- backend/app.py backend/routes/strategy_comparison.py backend/scripts/compare_entry_geometry.py
git diff HEAD origin/develop -- backend/app.py backend/routes/strategy_comparison.py backend/scripts/compare_entry_geometry.py
```

If these are the intended comparison-only changes and there are no VM-local
edits in those three files to preserve:

```bash
git restore --source=origin/develop --worktree -- backend/app.py backend/routes/strategy_comparison.py backend/scripts/compare_entry_geometry.py
docker compose config --quiet
docker compose restart backend
docker compose logs --tail=50 backend
```

This is a targeted working-tree deployment: it does not advance Git HEAD. The
selected files remain working-tree changes relative to the old commit when
remote content differs; use `git status` and the reviewed remote diff to track
that fact. It deliberately leaves production strategy/cost/gate modules and
VM-specific configuration alone.

The VM currently has local changes in `docker-compose.yml`, `nginx/default.conf`
and `backend/tokens.json`, plus `certbot/`. Preserve these. In particular, the VM
has its own HTTPS/certificate configuration; the local workspace's Compose file
is not an equivalent replacement. Avoid a blanket reset or stash/pop deployment.
The repository's `deploy.sh` targets `/mnt/d/candlesticks`, a different checkout
path, and rebuilds all services; it is not the restart procedure verified here.

## Verify after a restart without touching database records

From the VM or any Linux shell:

```bash
curl -i --request POST \
  'https://candlesticks-india.southafricanorth.cloudapp.azure.com/api/offline/compare-entry-geometry' \
  --header 'Content-Type: application/json' \
  --data '{"__route_probe":true}'
```

Expected: HTTP 400 with the specific unsupported-field message, not 405. Then
use the real request body to run the separate read-only research comparison:

```json
{
  "symbols": ["ITC", "TATASTEEL"],
  "timeframe": "5m",
  "exchange": "NSE",
  "from_date": "2025-10-23",
  "to_date": "2026-09-18"
}
```

The real request may return data/schema/availability statuses depending on the
**Azure** database. Earlier local-data findings do not establish Azure's data
coverage; no Azure data comparison was executed during this routing check.
