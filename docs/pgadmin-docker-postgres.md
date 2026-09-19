# Connect pgAdmin to the Docker PostgreSQL database

The application writes candle data to the PostgreSQL container declared in
`docker-compose.yml`. The container listens on port `5432` inside Docker and is
published as port `5433` on the laptop.

## pgAdmin connection

Create a new server in pgAdmin with these values:

| pgAdmin field | Value |
| --- | --- |
| Name | `Candlesticks Docker` |
| Host name/address | `127.0.0.1` |
| Port | `5433` |
| Maintenance database | `candleticks` |
| Username | `postgres` |
| Password | The `POSTGRES_PASSWORD` value in `docker-compose.yml` |

The database name is currently spelled `candleticks` in the project. Keep that
spelling when connecting. Changing it would select a different database and
make the existing candle rows appear missing.

If an existing pgAdmin server uses port `5432`, it connects to a separate local
PostgreSQL instance. Edit that server to use `5433`, or register the Docker
database as a separate server. After connecting, refresh this path:

`Servers > Candlesticks Docker > Databases > candleticks > Schemas > public > Tables`

The application stores candles in:

- `public.intraday_candles`
- `public.daily_candles`

If both counts are zero, connect the Upstox broker in the application before
starting a candle download. A successful download should report a positive
`inserted` row count. A successful response with `inserted: 0` means the
provider returned no candles for the requested instrument and date range; it
does not mean rows were written to PostgreSQL.

## Verify the connection and candle rows

Open pgAdmin's Query Tool for `candleticks` and run:

```sql
SELECT
    current_database() AS database_name,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port;

SELECT
    COUNT(*) AS intraday_rows,
    MIN("timestamp") AS first_candle,
    MAX("timestamp") AS last_candle
FROM public.intraday_candles;

SELECT
    COUNT(*) AS daily_rows,
    MIN("timestamp") AS first_candle,
    MAX("timestamp") AS last_candle
FROM public.daily_candles;
```

You can run the same row-count check from the project directory when Docker is
running:

```powershell
docker compose exec -T postgres psql -U postgres -d candleticks -c "SELECT COUNT(*) AS intraday_rows, MIN(timestamp) AS first_candle, MAX(timestamp) AS last_candle FROM public.intraday_candles;"
docker compose exec -T postgres psql -U postgres -d candleticks -c "SELECT COUNT(*) AS daily_rows, MIN(timestamp) AS first_candle, MAX(timestamp) AS last_candle FROM public.daily_candles;"
```

## Docker Desktop startup issue

pgAdmin can connect to port `5433` only while the PostgreSQL container is
running. Check it with:

```powershell
docker compose ps postgres
```

If Docker Desktop reports an unexpected WSL networking error, quit Docker
Desktop, run `wsl --shutdown` in an Administrator PowerShell window, and start
Docker Desktop again. This restarts all running WSL distributions, so save work
in those distributions first. Then start the project database:

```powershell
docker compose up -d postgres
```

Confirm that the backend uses the Docker database with:

```powershell
docker compose exec -T backend printenv PGHOST PGPORT PGDATABASE PGUSER
```

The expected output is host `postgres`, internal port `5432`, database
`candleticks`, and user `postgres`. pgAdmin reaches that same container through
the laptop mapping `127.0.0.1:5433`.
