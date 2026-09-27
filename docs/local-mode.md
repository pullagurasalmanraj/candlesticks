# Local mode after the Azure trial

The application does not require Azure-specific code. HTTP API routing and the
market-data WebSocket URL are derived from the browser location. Only the OAuth
redirect URI and runtime environment need to change.

## Switch to localhost

1. In the Upstox developer console, change the authorized redirect URI to:

   ```text
   http://localhost/
   ```

   The trailing slash is required because the backend OAuth callback is `/`.

2. From the repository root on Windows, run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\switch-environment.ps1 -Target local -Restart
   ```

   The script preserves credentials already stored in the ignored root `.env`
   file. It updates only the environment-dependent redirect and Redis URLs.

3. Open the application and reconnect Upstox:

   ```text
   http://localhost/auth/login
   ```

4. Connect local RedisInsight directly, without an SSH tunnel:

   ```text
   Host: 127.0.0.1
   Port: 6380
   Username: default
   Password: linux123
   Database: 0
   TLS: Off
   ```

## Verify local mode

```powershell
docker compose ps
docker compose exec -T backend python -c "import os; print(os.getenv('UPSTOX_REDIRECT_URI'))"
docker compose exec -T redis redis-cli -a linux123 -n 0 --scan
```

The redirect check should print `http://localhost/`. After Upstox authorization,
Redis should contain `upstox:tokens`, `active_subscriptions`, and
`ticks:stream:status`.

The browser uses `ws://localhost:9000` during direct local development. When
served through an HTTPS deployment, it automatically uses `wss://<host>/ws/`.

## Switch back to Azure while it is available

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\switch-environment.ps1 -Target azure -Restart
```

The Upstox developer-console redirect URI must also be changed back to:

```text
https://candlesticks-india.southafricanorth.cloudapp.azure.com/
```

## Important

- Do not commit `.env`; it contains credentials and remains ignored by Git.
- Stop the SSH tunnel when Azure is no longer used. Local RedisInsight connects
  directly to port `6380`.
- Export any Azure-only PostgreSQL or Redis data before deleting the VM. Docker
  volumes on the Azure VM are not automatically copied to the local computer.
