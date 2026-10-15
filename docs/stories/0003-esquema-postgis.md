# 0003 — Esquema PostGIS y migraciones para `parcel` y `building`

## Historia

Como motor de Parcel Intel que necesita persistir las entidades de dominio ya existentes, quiero un esquema PostGIS versionado por migraciones — con un entorno local reproducible para desarrollarlo y testearlo — que almacene `parcel` y `building` fielmente a su forma en `domain/`, para que las historias siguientes (Sentinel-2, PNOA, reglas, informe) tengan dónde leer y escribir sin que cada una improvise su propio esquema.

## Contexto

`docs/vision.md` describe diez entidades del modelo de datos (`parcel`, `building`, `observation`, `layer_feature`, `norm`, `provision`, `rule`, `bulletin_entry`, `finding`, `report`), pero hoy **solo existen entidades de dominio reales** para `parcel` y `building` (más `Geometry` y `Provenance` como tipos de apoyo, fijados en el [ADR 0002](../adr/0002-dos-ports-de-geometria-y-provenance-como-value-object.md)). Las demás entidades no tienen todavía forma de dominio: aparecerán con las historias de detección (Sentinel-2/PNOA), boletines, reglas e informe, que aún no se han escrito.

Por disciplina de "no diseñar para requisitos hipotéticos futuros" (`CLAUDE.md`), esta historia limita el esquema PostGIS a lo que ya tiene entidad de dominio: `parcel` y `building`. El resto del esquema se añade incrementalmente, historia por historia, a medida que cada entidad de dominio se introduce — no se reserva hueco ni se anticipan columnas para `observation`, `layer_feature`, `norm`, `rule`, `bulletin_entry`, `finding` ni `report` en esta historia.

`docs/vision.md` ya prevé un servicio PostGIS en `infra/docker-compose.yml`, fichero que todavía no existe en el repo. Esta historia lo crea, limitado al servicio de base de datos (API, worker y MLflow, también mencionados en `vision.md` para ese mismo fichero, quedan fuera: no hay código de `api/`, `rules/` ni pipeline de detección contra el que levantarlos todavía).

Varias decisiones técnicas no tienen ADR previo y deben decidirlas el arquitecto antes o durante la implementación (ver "Preguntas abiertas"): herramienta de migraciones, tipo de columna PostGIS para `Geometry` (cuyos `rings` ya admiten geometría multi-parte), si hace falta ya un repository port en `ports/`, y la librería de acceso a datos en el adapter.

## Criterios de aceptación

### Bloque 1 — Entorno local de base de datos

- [ ] `infra/docker-compose.yml` define un servicio con una imagen de PostgreSQL con extensión PostGIS instalada, con puerto, usuario, contraseña y nombre de base de datos configurables por variables de entorno (con valores por defecto para desarrollo local).
- [ ] Levantar el servicio (`docker compose -f infra/docker-compose.yml up -d`, comando documentado literalmente donde corresponda — `CLAUDE.md` o un `infra/README.md`) deja una base de datos accesible en la que `SELECT postgis_version();` devuelve una versión sin error.
- [ ] El esquema se crea sobre una base de datos con nombre propio (no la `postgres` por defecto), nombre también configurable por variable de entorno.
- [ ] Parar y eliminar el entorno (`docker compose -f infra/docker-compose.yml down -v`) y volver a levantarlo deja la base de datos en el mismo estado inicial (sin datos residuales de una ejecución anterior) — verificable ejecutando ambos pasos en secuencia como parte del cierre de la historia.

### Bloque 2 — Migraciones versionadas

- [ ] Existe un mecanismo de migraciones versionado (herramienta concreta a decisión del arquitecto; ver "Preguntas abiertas") con al menos dos migraciones secuenciales: una que crea la tabla `parcel`, otra que crea la tabla `building`.
- [ ] El comando para aplicar las migraciones desde cero queda documentado en `CLAUDE.md` (ampliando la sección "Comandos") y se ejecuta literalmente, tal como está escrito, sin argumentos adicionales — conforme a la lección registrada en `docs/lessons/LESSONS.md` sobre comandos documentados que deben funcionar tal cual.
- [ ] Aplicar las migraciones contra la base de datos vacía del Bloque 1 crea la tabla `parcel` con, como mínimo, estas columnas y restricciones: `cadastral_reference` (texto, clave primaria), `municipality` (texto, no nulo), `geometry` (columna PostGIS con SRID 25830, tipo concreto — `Polygon` o `MultiPolygon` — a decisión del arquitecto conforme a que `Geometry.rings` admite multi-parte), `area_m2` (numérico, no nulo), `provenance_source` (texto, no nulo), `provenance_url` (texto, no nulo), `provenance_retrieved_at` (fecha, no nulo), `provenance_license` (texto, nulo permitido).
- [ ] Aplicar las migraciones crea la tabla `building` con, como mínimo: una clave primaria propia (sintética, p. ej. autogenerada), `cadastral_reference` (texto, no nulo, clave foránea a `parcel.cadastral_reference`), `geometry` (columna PostGIS con SRID 25830, mismo criterio de tipo que `parcel`), `area_m2` (numérico, no nulo), `construction_year` (entero, nulo permitido), `origin` (texto o enumerado, restringido a los valores `catastro` y `detected` de `domain/building.py`), más las cuatro columnas de procedencia equivalentes a las de `parcel`.
- [ ] Revertir la última migración (`down`/equivalente según la herramienta elegida) elimina la tabla `building` sin afectar a `parcel`, verificable comprobando que la tabla desaparece de `information_schema.tables` y que `parcel` sigue existiendo.
- [ ] Aplicar las migraciones dos veces consecutivas sobre la misma base de datos no falla ni duplica tablas (el mecanismo de migraciones registra qué se aplicó).

### Bloque 3 — Verificación con datos reales del dominio

- [ ] Un test de integración (marcado explícitamente como tal, sin red salvo la conexión a la base de datos local — conforme a la convención de `CLAUDE.md` de fixtures sin red y tests de integración aparte) levanta el esquema contra una base de datos PostGIS real (el servicio del Bloque 1 o un contenedor efímero equivalente), inserta una `Parcel` y al menos dos `Building` asociados a ella, y lee de vuelta los datos comprobando que `cadastral_reference`, `area_m2`, `origin`, `provenance` y el SRID de la geometría coinciden con los valores insertados.
- [ ] Ese mismo test cubre explícitamente el caso no trivial de geometría multi-parte: al menos una de las `Parcel` o `Building` insertadas tiene una `Geometry` con 2 o más `rings` (no solo el caso de un único anillo), y la lectura de vuelta conserva el número de anillos y sus coordenadas — conforme a la lección ya registrada en `docs/lessons/LESSONS.md` sobre no dar por cubierto el caso multi-parte con fixtures de un único anillo.
- [ ] El mismo test verifica que insertar un `Building` con `cadastral_reference` que no existe en `parcel` falla por la restricción de clave foránea (no se acepta un edificio huérfano).
- [ ] `uv run pytest` (ejecutado literalmente, tal como lo documenta `CLAUDE.md`) distingue claramente los tests de integración de este bloque del resto de la suite (marcador o ruta separada), de forma que el resto de tests sigue pasando sin que la base de datos esté levantada.
- [ ] `uv run mypy` y `uv run ruff check .` (ejecutados literalmente) pasan en verde sobre el código nuevo.
- [ ] `uv run lint-imports` sigue en verde: el código de acceso a PostGIS (SQL, driver, mapeo dominio↔fila) vive en `adapters/`, no en `domain/` ni `application/`.

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
