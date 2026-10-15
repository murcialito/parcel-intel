# 0003 — Esquema PostGIS y migraciones para `parcel` y `building`

## Historia

Como motor de Parcel Intel que necesita persistir las entidades de dominio ya existentes, quiero un esquema PostGIS versionado por migraciones — con un entorno local reproducible para desarrollarlo y testearlo — que almacene `parcel` y `building` fielmente a su forma en `domain/`, para que las historias siguientes (Sentinel-2, PNOA, reglas, informe) tengan dónde leer y escribir sin que cada una improvise su propio esquema.

## Contexto

`docs/vision.md` describe diez entidades del modelo de datos (`parcel`, `building`, `observation`, `layer_feature`, `norm`, `provision`, `rule`, `bulletin_entry`, `finding`, `report`), pero hoy **solo existen entidades de dominio reales** para `parcel` y `building` (más `Geometry` y `Provenance` como tipos de apoyo, fijados en el [ADR 0002](../adr/0002-dos-ports-de-geometria-y-provenance-como-value-object.md)). Las demás entidades no tienen todavía forma de dominio: aparecerán con las historias de detección (Sentinel-2/PNOA), boletines, reglas e informe, que aún no se han escrito.

Por disciplina de "no diseñar para requisitos hipotéticos futuros" (`CLAUDE.md`), esta historia limita el esquema PostGIS a lo que ya tiene entidad de dominio: `parcel` y `building`. El resto del esquema se añade incrementalmente, historia por historia, a medida que cada entidad de dominio se introduce — no se reserva hueco ni se anticipan columnas para `observation`, `layer_feature`, `norm`, `rule`, `bulletin_entry`, `finding` ni `report` en esta historia.

`docs/vision.md` ya prevé un servicio PostGIS en `infra/docker-compose.yml`, fichero que todavía no existe en el repo. Esta historia lo crea, limitado al servicio de base de datos (API, worker y MLflow, también mencionados en `vision.md` para ese mismo fichero, quedan fuera: no hay código de `api/`, `rules/` ni pipeline de detección contra el que levantarlos todavía).

Varias decisiones técnicas no tienen ADR previo y deben decidirlas el arquitecto antes o durante la implementación (ver "Preguntas abiertas"): herramienta de migraciones, tipo de columna PostGIS para `Geometry` (cuyos `rings` ya admiten geometría multi-parte), si hace falta ya un repository port en `ports/`, y la librería de acceso a datos en el adapter.

## Criterios de aceptación

### Bloque 1 — Entorno local de base de datos — CERRADO 2026-10-15

- [x] `infra/docker-compose.yml` define el servicio `db` (`postgis/postgis:16-3.4`), con `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_PORT` configurables por variable de entorno con valores por defecto (`parcel_intel`/`parcel_intel`/`parcel_intel`/`5432`).
- [x] `docker compose -f infra/docker-compose.yml up -d` deja una base de datos en la que `SELECT postgis_version();` devuelve `3.4 USE_GEOS=1 USE_PROJ=1 USE_STATS=1` sin error — verificado contra Docker real, no simulado.
- [x] El esquema se crea sobre `parcel_intel` (no `postgres`), nombre configurable por `POSTGRES_DB`.
- [x] `down -v` + `up` + aplicar migraciones deja el mismo estado inicial — verificado en esta sesión (ciclo completo real, no supuesto).
- **Hallazgo no previsto, documentado en `infra/README.md`:** con un volumen nuevo, la imagen `postgis/postgis` reinicia el servidor una vez mientras crea las extensiones; `pg_isready` puede devolver éxito *durante* ese reinicio, antes de que `postgis_version()` exista todavía. El primer intento de este cierre de historia falló por este motivo exacto (confirmado en los logs del contenedor). La comprobación de disponibilidad correcta debe esperar a que `SELECT postgis_version();` funcione, no solo a `pg_isready`.

### Bloque 2 — Migraciones versionadas — CERRADO 2026-10-15

- [x] Runner propio en SQL plano (`adapters/postgis/migrate.py` + `adapters/postgis/migrations/*.{up,down}.sql`), conforme al [ADR 0004](../adr/0004-persistencia-postgis-sql-plano-sin-repository-port.md). Dos migraciones: `0001_create_parcel`, `0002_create_building`.
- [x] `uv run python -m parcel_intel.adapters.postgis.migrate up` documentado literalmente en `CLAUDE.md` y ejecutado tal cual en esta sesión.
- [x] `parcel`: `cadastral_reference` (PK), `municipality`, `geometry(MultiPolygon, 25830)`, `area_m2`, 4 columnas `provenance_*`.
- [x] `building`: `id BIGSERIAL` (PK sintética), `parcel_reference` (FK a `parcel.cadastral_reference`), `cadastral_reference` (texto, no nulo — la referencia **del edificio**, no de la parcela), `geometry(MultiPolygon, 25830)`, `area_m2`, `construction_year`, `origin` (`CHECK IN ('catastro','detected')`), 4 columnas `provenance_*`. **Aclaración frente al texto original de este criterio:** se usan dos columnas (`parcel_reference` y `cadastral_reference`), no una sola haciendo ambas cosas — `domain/building.py` no garantiza que la referencia de un edificio coincida con la de su parcela (en rústico casi nunca coincide; en el núcleo urbano de Colmenar de Oreja, por convención local, sí — ver historia 0002), así que una sola columna FK+identidad habría sido incorrecta.
- [x] `down` revierte `building` sin afectar `parcel` — verificado: tras `down`, `\dt` muestra `parcel` pero no `building`.
- [x] Aplicar `up` dos veces seguidas no falla ni duplica (verificado: la segunda ejecución no imprime nada, `schema_migrations` ya las tenía registradas).

### Bloque 3 — Verificación con datos reales del dominio — CERRADO 2026-10-15

- [x] Test de integración (`tests/adapters/postgis/test_repository_integration.py`, `pytestmark = pytest.mark.integration`) contra el PostGIS real del Bloque 1: inserta una `Parcel` y dos `Building`, lee de vuelta y compara `cadastral_reference`, `area_m2`, `origin`, `provenance` y SRID.
- [x] Cubre explícitamente el caso multi-parte: uno de los `Building` insertados tiene `Geometry` con 2 anillos (cuerpo principal + anexo, mismo patrón real que el edificio `REFCAT-RETIRADA` de la historia 0002); la lectura conserva ambos anillos.
- [x] Insertar un `Building` con `parcel_reference` inexistente lanza `psycopg.errors.ForeignKeyViolation` — verificado con una llamada real a la base de datos, no simulado.
- [x] `uv run pytest` (sin argumentos) excluye los tests de integración por defecto (`addopts = "-m 'not integration'"`); `uv run pytest -m integration` los ejecuta aparte. Verificado: 27 passed / 4 deselected en el primer caso, 4 passed / 27 deselected en el segundo.
- [x] `uv run mypy` y `uv run ruff check .` en verde sobre el código nuevo.
- [x] `uv run lint-imports` en verde: todo el SQL, el driver `psycopg` y el mapeo WKT↔`Geometry` viven en `adapters/postgis/`.

## Fuera de alcance

- Esquema, tablas o migraciones para `observation`, `layer_feature`, `norm`, `provision`, `rule`, `bulletin_entry`, `finding` o `report`: se añaden en historias futuras, cuando cada una tenga su entidad de dominio correspondiente (detección, boletines, reglas, informe).
- Un repository port en `ports/` (p. ej. `ParcelRepositoryPort`) y su wiring desde `application/`: queda como pregunta abierta para el arquitecto; si decide que hace falta ya, se trata en un ADR y puede ampliar el alcance de esta historia o abrir la siguiente.
- Servicios de `infra/docker-compose.yml` distintos de la base de datos (API, worker, MLflow mencionados en `docs/vision.md`): no hay código en `api/` ni en los pipelines de detección/reglas contra el que levantarlos todavía.
- Caché, backups, réplicas o cualquier operación de base de datos en producción (el servidor casero mencionado en `docs/vision.md`): esta historia cubre solo el entorno de desarrollo/test local.
- Índices espaciales u optimización de consultas: se añaden cuando una historia de consumo real (p. ej. cruce espacial con capas de afección) lo necesite y pueda medir su efecto.
- Versionado histórico de `parcel`/`building` (p. ej. qué pasa si Catastro cambia una geometría con el tiempo): no hay todavía ningún pipeline que reconsulte Catastro periódicamente.
- Cualquier adaptación del cliente de Catastro (historia 0002) para escribir directamente en este esquema: esta historia entrega el esquema y las migraciones; conectar un flujo real de ingesta es trabajo de una historia posterior.

## Preguntas abiertas

- Herramienta de migraciones: Alembic, migraciones SQL planas con un runner simple, u otra alternativa ligera — `docs/vision.md` no la especifica. Decisión del arquitecto.
- Tipo de columna PostGIS para `Geometry`: ¿`geometry(Polygon, 25830)` fijo, `geometry(MultiPolygon, 25830)` fijo (más simple si toda geometría de una sola pieza se representa igual que una multi-parte de un solo elemento), o un tipo `geometry(Geometry, 25830)` genérico con la restricción de forma en otro punto? Decisión del arquitecto, condicionada a que `Geometry.rings` ya admite múltiples anillos.
- ¿Hace falta ya un `ParcelRepositoryPort` (u otro nombre por capacidad) en `ports/` para que esta historia tenga un consumidor real desde `application/`, o se deja el esquema sin wiring de aplicación hasta que exista un caso de uso que lo necesite? Decisión del arquitecto.
- Librería de acceso a datos en el adapter: driver de PostgreSQL con o sin ORM (`docs/vision.md` menciona `geopandas`/`shapely` en el stack general para geoprocesamiento, pero no fija cómo se escribe/lee desde Python hacia PostGIS). Decisión del arquitecto; si introduce un paquete de terceros nuevo relevante (p. ej. un ORM), requiere ADR conforme a `CLAUDE.md`.
- Imagen concreta de PostGIS para `infra/docker-compose.yml` (proveedor, versión fijada) y si debe coincidir con la versión que se prevé usar en el servidor casero de producción: decisión del arquitecto.
- ¿Las columnas de procedencia (`provenance_*`) se aplanan como columnas propias en cada tabla (como se ha redactado arriba) o se extraen a una tabla/tipo compuesto propio reutilizable, dado que `ADR 0002` ya anticipa que otras entidades futuras (`Observation`, `LayerFeature`, `Norm`, `BulletinEntry`) también llevarán `Provenance`? Decisión del arquitecto; no bloquea esta historia porque el criterio de aceptación solo exige que los cuatro campos existan y sean consultables, no una forma física concreta.

## Métricas de éxito

- Las dos tablas (`parcel`, `building`) existen en una base de datos PostGIS real, creadas únicamente por migraciones versionadas, reproducibles desde cero con un solo comando documentado en `CLAUDE.md`.
- El test de integración del Bloque 3 demuestra, con datos reales (no mocks), que una `Parcel` y sus `Building` asociados —incluyendo al menos un caso de geometría multi-parte— sobreviven un ciclo completo de escritura/lectura sin pérdida de información frente a la entidad de dominio original.
- Ninguna historia futura que introduzca una entidad nueva del modelo de datos (`observation`, `rule`, etc.) necesita modificar el esquema de `parcel` o `building` para encajar: señal de que el corte de esta historia fue el correcto.
- Cero deuda de alcance oculta: el esquema entregado no contiene ninguna columna o tabla para entidades que todavía no existen en `domain/`.
