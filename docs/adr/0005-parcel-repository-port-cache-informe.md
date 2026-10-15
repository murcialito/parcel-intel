# ADR 0005 — `ParcelRepositoryPort`: un port compuesto para la caché del informe, miss por excepción, fail-fast ante PostGIS caído

- Estado: aceptada — supersede ADR-0004, punto 3 ("no se introduce `ParcelRepositoryPort`... hasta que exista un caso de uso real")
- Fecha: 2026-10-15

## Contexto

La historia 0005 pide que `GET /reports/{municipio}/{referencia}` use PostGIS como caché de lo ya consultado a Catastro. El ADR 0004 dejó dicho explícitamente que no se crearía `ParcelRepositoryPort` "hasta que exista un caso de uso real que lo necesite", y nombró `PostgisParcelRepository` por capacidad (`save_parcel`, `get_parcel`, `save_buildings`, `get_buildings_for_parcel`) precisamente para que extraer el `Protocol` el día que apareciera ese consumidor fuera barato.

Ese día es hoy. La lógica "leer caché; si falla, pedir a Catastro, guardar y devolver" no es wiring de composición — decide, por entrada, qué fuente de verdad usar y en qué orden, y qué hacer con cada resultado (incluido no persistir en caso de error de Catastro). Eso es exactamente lo que `CLAUDE.md` reserva a `application/`: un caso de uso con ports inyectados por constructor. Dejarlo en `api/main.py` violaría la regla de que `application/` es la única capa de orquestación de negocio, y además haría que esa lógica no fuera reutilizable desde un futuro `cli/` (ADR 0003) sin duplicarla.

Datos relevantes del código actual:
- `GenerateParcelReportUseCase.execute()` hoy solo llama a `ParcelGeometryPort.get_parcel()` y `BuildingGeometryPort.get_buildings()`, en ese orden, sin estado.
- `PostgisParcelRepository` ya respeta la lección de la historia 0003 (`try/except` + rollback explícito, nunca `with self._connection:` para operaciones donde el repositorio no posee la conexión).
- `api/main.py` instancia `CatastroAdapter` por petición, con el municipio resuelto desde la URL; no hay ninguna conexión a PostGIS en el camino de la API todavía.
- El servidor de producción es un Docker Compose casero sin alta disponibilidad: no hay métricas, alertas ni operador de guardia — una degradación silenciosa puede pasar inadvertida indefinidamente.
- El AC de la historia fija que la primera petición hace "el mismo número de llamadas HTTP que sin esta historia", incluida la ineficiencia ya señalada en la revisión de la historia 0002 (`CatastroAdapter.get_buildings()` vuelve a resolver el centroide y a pedir el WFS de parcela). Esto cierra, por el propio texto del AC, la pregunta de si esta historia debe arreglar esa redundancia: no debe.

## Decisión

**1. `ParcelRepositoryPort` se crea ahora, en `ports/repository.py`, como un único port compuesto — no cuatro métodos sueltos ni dos ports separados (parcela / edificios):**

```python
class ParcelRepositoryPort(Protocol):
    def get_report(self, cadastral_reference: str) -> ParcelReport: ...
    def save_report(self, report: ParcelReport) -> None: ...
```

`GenerateParcelReportUseCase` recibe este port como tercer parámetro de constructor (junto a `parcel_port` y `building_port`, que no desaparecen: siguen siendo necesarios para el camino de caché fría). `execute()` pasa a:

```python
def execute(self, cadastral_reference: str) -> ParcelReport:
    try:
        return self._repository.get_report(cadastral_reference)
    except ParcelNotCachedError:
        pass
    parcel = self._parcel_port.get_parcel(cadastral_reference)
    buildings = tuple(self._building_port.get_buildings(cadastral_reference))
    report = ParcelReport(parcel=parcel, buildings=buildings)
    self._repository.save_report(report)
    return report
```

`ParcelNotFoundError`/`InvalidCadastralReferenceError` de Catastro se propagan sin tocar `save_report`, así que "no cachear negativos" (AC) no necesita lógica extra: `save_report` solo es alcanzable después de construir un `ParcelReport` completo.

Por qué un port, no dos: el ADR 0002 separó `ParcelGeometryPort`/`BuildingGeometryPort` porque un futuro proveedor (detección por imagen) tendría autoridad solo sobre edificios, nunca sobre la geometría de parcela — esa asimetría de autoridad no existe aquí. La caché lee y escribe parcela+edificios como una sola unidad (un informe); partir el port de persistencia en dos sin un segundo consumidor real que lo justifique repetiría exactamente el patrón de diseño especulativo que el propio ADR 0004 acaba de rechazar ("no diseñar para requisitos hipotéticos").

**2. `PostgisParcelRepository` gana `get_report`/`save_report` como envoltorios transaccionales de los cuatro métodos ya existentes (que se conservan intactos, sin romper sus tests de la historia 0003):**

```python
def save_report(self, report: ParcelReport) -> None:
    with self._connection.transaction():
        self.save_parcel(report.parcel)
        self.save_buildings(report.parcel.cadastral_reference, list(report.buildings))
```

Esto resuelve, de paso y sin tocar el esquema, el riesgo de estado parcial que tendría llamar a `save_parcel` y `save_buildings` como dos operaciones independientes (proceso interrumpido entre una y otra deja una parcela cacheada con cero edificios, indistinguible de una parcela rústica real sin edificios).

**Aclaración explícita, porque se parece superficialmente al patrón prohibido por la lección de la historia 0003**: `self._connection.transaction()` (psycopg 3) no es lo mismo que usar `self._connection` directamente como context manager. Lo segundo (`with self._connection:`) cierra la conexión al salir del bloque — por eso está prohibido en un repositorio que no posee el ciclo de vida de su conexión. `connection.transaction()` es una API distinta: solo demarca un bloque `BEGIN`/`COMMIT` o `ROLLBACK` (con soporte de savepoints si se anida), sin cerrar nada. Es el mecanismo correcto para esto y no contradice la lección registrada; el implementador no debe evitarlo por exceso de cautela.

Los `save_parcel`/`save_buildings` reutilizados dentro de `save_report` ya hacen su propio `commit()`/`rollback()` individual (historia 0003); al quedar anidados dentro de `connection.transaction()`, ese commit interno pasa a ser un no-op de psycopg dentro de la transacción exterior — correcto, pero si al implementar se prefiere evitar la dependencia de ese detalle de psycopg, es aceptable extraer el SQL de ambos a funciones privadas sin commit propio y mover el único `commit`/`rollback` al nivel de `save_report`/`get_report`. Cualquiera de las dos formas es válida; lo que no es aceptable es un `save_report` sin transacción explícita.

**3. El miss de caché se señala por excepción (`ParcelNotCachedError`), no por un método `exists() -> bool` separado.** El código ya establece este patrón (`ParcelNotFoundError` de Catastro funciona igual). Un `exists()` adicional obligaría a dos ida-vueltas a PostGIS (comprobar y luego leer) o a duplicar la query de lectura en dos sitios, sin ganar nada: no hay ningún control de flujo "normal" distinto de "está o no está".

`ParcelNotFoundInRepositoryError` (historia 0003, hoy definida en `adapters/postgis/repository.py`) se renombra a `ParcelNotCachedError` y se mueve a `ports/errors.py`. No puede seguir viviendo en el adapter: `application/` necesita capturarla y `application/` solo puede importar `ports` y `domain`, nunca `adapters` (`CLAUDE.md`, regla no negociable). Esto obliga a actualizar `tests/adapters/postgis/test_repository_integration.py` (importa hoy `ParcelNotFoundInRepositoryError` desde `adapters.postgis.repository`) para importar desde `ports.errors` — cambio mecánico de una línea, cubierto por "lo estrictamente necesario para que `application/` lo use" que la propia historia autoriza explícitamente.

**4. PostGIS no disponible → fail-fast con `503`, sin fallback automático a Catastro directo.** `api/main.py` abre una conexión por petición reutilizando `get_connection()` (ya existe en `adapters/postgis/connection.py`, usado hoy por el runner de migraciones), con el mismo patrón "un adapter por petición" que ya usa para `CatastroAdapter`:

```python
with get_connection() as conn:
    repository = PostgisParcelRepository(conn)
    ...
```

Aquí `with get_connection() as conn:` **sí** es correcto, y no contradice la lección de la historia 0003: la lección prohíbe que un *repositorio* cierre una conexión que no posee; aquí quien crea la conexión y es dueño de su ciclo de vida para la duración de esta única petición es precisamente `api/main.py`. Cerrarla al final del `with` es exactamente lo que se quiere.

Cualquier `psycopg.OperationalError` (al conectar, o a media petición si PostGIS cae durante la consulta) no se captura en `application/` — no puede: `application/` no importa `psycopg` ni ningún símbolo de `adapters`, así que por la propia frontera hexagonal la excepción llega intacta a `api/main.py`, que la traduce a `HTTPException(503, "Servicio de caché no disponible; inténtalo de nuevo en unos segundos.")`.

No se degrada automáticamente a Catastro directo cuando PostGIS está caído. En un servidor casero sin alta disponibilidad ni monitorización, degradar en silencio esconde una caída de PostGIS detrás de peticiones que "siguen funcionando pero ya no cachean" — nadie se entera de que el contenedor está parado hasta que el coste por informe sube sin explicación aparente, justo la métrica de negocio que este proyecto más vigila. Un 503 explícito es la señal mínima imprescindible para que el operador reinicie el contenedor (`docker compose up -d`); no introduce ningún mecanismo nuevo de resiliencia (no hay reintentos, no hay circuit breaker) — es simplemente no capturar un error que de otro modo ya se propagaría solo.

## Alternativas consideradas

- **No crear el port; orquestar "leer caché / ir a Catastro / guardar" directamente en `api/main.py`, instanciando `PostgisParcelRepository` igual que hoy se instancia `CatastroAdapter`**: rechazada. Es la opción que `CLAUDE.md` prohíbe explícitamente ("application/ ... jamás un adapter" implica, a la inversa, que la lógica de negocio no vive en la capa de composición). Además duplicaría esta lógica el día que `cli/` (ADR 0003) necesite generar el mismo informe sin pasar por HTTP.
- **Dos ports separados, `ParcelCachePort`/`BuildingCachePort`, simétricos a `ParcelGeometryPort`/`BuildingGeometryPort` del ADR 0002**: rechazada. La separación del ADR 0002 responde a una asimetría real de autoridad entre proveedores (imagen vs. Catastro) que no existe en persistencia: no hay ningún proveedor de caché previsto que solo pueda guardar edificios sin parcela. Partir el port sin ese segundo consumidor real sería diseño especulativo, justo lo que el ADR 0004 ya rechazó una vez en este mismo punto.
- **Extraer literalmente los cuatro métodos de `PostgisParcelRepository` al port (`save_parcel`, `get_parcel`, `save_buildings`, `get_buildings_for_parcel`), tal como anticipaba el ADR 0004**: rechazada como forma final del port, aunque se mantienen como métodos internos del adapter. El consumidor real (`GenerateParcelReportUseCase`) no necesita parcela y edificios por separado: los necesita como una unidad (un informe), y expornerlos sueltos en el port habría dejado al caso de uso la responsabilidad de orquestar dos llamadas y gestionar el riesgo de estado parcial — exactamente el problema que resolver con una transacción en el adapter evita de raíz.
- **`exists(cadastral_reference) -> bool` explícito en vez de excepción**: rechazada. Obliga a dos round-trips a PostGIS o a duplicar la query de lectura; el patrón de excepción como señal de "no está" ya es el que usa el resto del código (`ParcelNotFoundError` de Catastro) y mantiene `execute()` en una sola rama de control.
- **Degradar automáticamente a Catastro directo cuando PostGIS no responde**: rechazada para esta historia. Técnicamente viable (capturar `OperationalError` en `api/main.py` y saltarse la caché), pero introduce un segundo camino de ejecución que hay que probar y mantener, y en un servidor sin monitorización esconde exactamente el tipo de fallo que el operador necesita ver. Si en producción las caídas de PostGIS resultan frecuentes, revisar esta decisión con datos reales, no de forma preventiva.
- **Mantener `ParcelNotFoundInRepositoryError` en `adapters/postgis/repository.py` y que `application/` la capture igualmente**: rechazada. Rompería la regla no negociable de capas (`application/` solo importa `ports`/`domain`) y además `lint-imports` lo bloquearía.
- **Conexión de PostGIS de vida larga (pool, o una única conexión global reutilizada entre peticiones) en vez de una por petición**: rechazada por ahora, por simplicidad y coherencia con el patrón ya existente (`CatastroAdapter` también se instancia por petición). El MVP no tiene concurrencia real que lo justifique; si el volumen de peticiones lo exige, introducir un pool (`psycopg_pool`) es un cambio contenido a `adapters/postgis/connection.py` y a cómo `api/main.py` obtiene la conexión, sin tocar `domain/`, `ports/` ni `application/` — se revisita entonces con datos de carga reales, no antes.

## Consecuencias

- Nuevo archivo `ports/repository.py` con `ParcelRepositoryPort`. `ports/errors.py` gana `ParcelNotCachedError` (renombrado desde `ParcelNotFoundInRepositoryError`, movido desde `adapters/postgis/repository.py`).
- `GenerateParcelReportUseCase.__init__` gana un tercer parámetro obligatorio (`repository: ParcelRepositoryPort`); cualquier test existente que lo instancie con solo dos ports debe actualizarse.
- `PostgisParcelRepository` gana `get_report`/`save_report`; sus cuatro métodos de la historia 0003 se conservan sin cambios de firma y siguen cubiertos por los tests existentes.
- `tests/adapters/postgis/test_repository_integration.py` actualiza el import de `ParcelNotFoundInRepositoryError` → `ParcelNotCachedError` desde `parcel_intel.ports.errors`.
- `api/main.py` pasa a instanciar también `PostgisParcelRepository` por petición, abriendo conexión con `get_connection()` dentro de un `with`, y mapea `psycopg.OperationalError` a `HTTPException(503, ...)`. Sigue sin instanciar nada en `application/` más allá de la inyección por constructor — no cambia su rol de composition root (ADR 0003).
- La ineficiencia ya señalada en la revisión de la historia 0002 (`CatastroAdapter.get_buildings()` vuelve a resolver centroide y WFS de parcela) **no se corrige en esta historia**: el propio AC de la historia 0005 fija que la primera petición hace "el mismo número de llamadas HTTP que sin esta historia". Queda documentado aquí, otra vez, para que no se pierda: ahora que existe caché, el coste de esa redundancia solo se paga una vez por referencia (en la petición que falla la caché), lo que reduce la urgencia de corregirla pero no la elimina — sigue siendo candidata a una historia futura dedicada, no a un parche dentro de esta.
- Riesgo residual aceptado explícitamente: si el proceso muere a mitad de `save_report` después de que la transacción de PostGIS haga commit pero antes de responder al cliente HTTP, el cliente ve un error pero la próxima petición a esa referencia sí encontrará caché completa (correcto, porque la transacción es atómica a nivel de PostGIS). El escenario que esta decisión sí evita es el más peligroso: commit parcial (parcela sin sus edificios) por fallar entre dos operaciones no transaccionadas — eso ya no puede ocurrir con `connection.transaction()`.
- Coste de salida de proveedor: no aplica cambio respecto al ADR 0004 (sigue siendo PostGIS/psycopg, ya evaluado allí). Esta decisión no introduce ningún proveedor de terceros nuevo.
