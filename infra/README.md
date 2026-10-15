# Entorno local de base de datos

```bash
docker compose -f infra/docker-compose.yml up -d
uv run python -m parcel_intel.adapters.postgis.migrate up
```

**Importante al levantar un volumen nuevo (primer `up` o tras `down -v`):** la imagen `postgis/postgis` reinicia el servidor una vez internamente mientras crea las extensiones PostGIS. `pg_isready` puede devolver éxito durante ese reinicio, *antes* de que las extensiones estén listas — esperar explícitamente a que `SELECT postgis_version();` funcione, no solo a `pg_isready`, antes de aplicar migraciones:

```bash
until docker compose -f infra/docker-compose.yml exec -T db psql -U parcel_intel -d parcel_intel -c "SELECT postgis_version();" >/dev/null 2>&1; do sleep 1; done
```

Variables de entorno (valores por defecto entre paréntesis): `POSTGRES_DB` (`parcel_intel`), `POSTGRES_USER` (`parcel_intel`), `POSTGRES_PASSWORD` (`parcel_intel`), `POSTGRES_PORT` (`5432`), `POSTGRES_HOST` (`localhost`, usado por el cliente Python, no por Compose).

Parar y borrar todo (incluidos los datos):

```bash
docker compose -f infra/docker-compose.yml down -v
```
