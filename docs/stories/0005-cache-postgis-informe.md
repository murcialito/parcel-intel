# 0005 — El informe usa PostGIS como caché de lo ya consultado a Catastro

## Historia

Como servicio de informes de Parcel Intel, quiero que `GET /reports/{municipio}/{referencia}` reutilice lo que ya se consultó a Catastro para una referencia catastral dada, en vez de repetir las llamadas HTTP reales en cada petición, para no pagar dos veces por un dato que no ha podido cambiar y para que el informe siga disponible aunque Catastro esté lento o caído.

## Contexto

La historia 0004 dejó documentado explícitamente, en su "Fuera de alcance", que cada carga del informe repite las llamadas HTTP a Catastro (4 por petición) y que no hay caché de ningún tipo. `docs/vision.md`/`CLAUDE.md` exige "datos crudos cacheados e inmutables"; hoy el único dato crudo que no se cachea en absoluto es exactamente el de Catastro que alimenta el informe.

La historia 0003 construyó el esquema PostGIS (`parcel`, `building`) y `PostgisParcelRepository` con sus cuatro métodos por capacidad (`save_parcel`, `get_parcel`, `save_buildings`, `get_buildings_for_parcel`), pero el ADR 0004 decidió explícitamente no crear todavía ningún `ParcelRepositoryPort` en `ports/` ni wiring desde `application/` "hasta que exista un caso de uso real que lo necesite". Esta historia es ese caso de uso: el primer consumidor real del repositorio.

**Asunción de partida de esta historia, a confirmar por el arquitecto (ver "Preguntas abiertas"):** el caché es permanente, sin expiración ni refresco. Es coherente con "datos... inmutables" de `CLAUDE.md` y con que la historia 0003 ya dejó fuera de su propio alcance "qué pasa si Catastro cambia una geometría con el tiempo" y "versionado histórico" — tratar aquí la invalidación habría sido ampliar un alcance que la historia anterior cerró deliberadamente sin resolver. Si el fundador o el arquitecto prefieren otra semántica (TTL, refresco manual, etc.), es una decisión nueva que debe tomarse antes de implementar, no una que esta historia decida por su cuenta.

Esta historia no reabre la 0003: reutiliza `parcel`/`building` tal cual están, sin nuevas tablas ni columnas, y no modifica el repositorio salvo lo estrictamente necesario para que `api/main.py` (o `application/`, según decida el arquitecto) lo use.

## Criterios de aceptación — CERRADOS 2026-10-15

- [x] Primera petición de una referencia nueva: mismo número de llamadas HTTP que antes de esta historia (5, confirmado con spy), y persiste `Parcel`+`Building` en PostGIS. Verificado también **en vivo** contra Docker real: primera petición al servidor en caliente tardó 8.95s (llamadas reales a Catastro) y dejó la fila real en `parcel`/`building` (consultada por `psql` directamente).
- [x] Segunda petición a la misma referencia: cero llamadas HTTP nuevas (spy sigue en el mismo número). Verificado en vivo: segunda petición al mismo servidor, 0.04s — 220× más rápida que la primera, servida desde PostGIS.
- [x] HTML idéntico entre primera y segunda petición (`render_parcel_report_html` comparado byte a byte en `test_segunda_peticion_no_llama_a_catastro_y_sirve_el_mismo_html`), incluido `provenance.retrieved_at` original.
- [x] Referencia distinta no comparte caché (`test_referencias_distintas_no_comparten_cache`): la segunda referencia sigue llamando a Catastro con normalidad.
- [x] Resultado negativo (`ParcelNotFoundError`) no se persiste y la siguiente petición reintenta Catastro desde cero (`test_parcela_no_encontrada_no_se_cachea_y_reintenta_catastro_la_proxima_vez`).
- [x] Caso no trivial cubierto: `test_segunda_peticion_no_llama_a_catastro_y_sirve_el_mismo_html` usa la parcela urbana real `REFCAT-RETIRADA` con su edificio de 3 anillos (cuerpo + 2 anexos).
- [x] `uv run pytest` → 30 passed / 10 deselected; `uv run pytest -m integration` → 10 passed, contra PostGIS real.
- [x] Ciclo completo de Docker ejecutado de verdad (`down -v`, `up`, esperar `postgis_version()`, reaplicar migraciones, repetir suite de integración) — encontró un hallazgo nuevo, no solo confirmó lo ya sabido: incluso tras `postgis_version()` funcionando, hubo un corte de conexión adicional breve justo después (`OperationalError: server closed the connection unexpectedly`), documentado en `infra/README.md`.
- [x] `uv run mypy`, `uv run ruff check .`, `uv run lint-imports` en verde.
- [x] Ningún cambio al esquema de la historia 0003: mismas tablas `parcel`/`building`, sin migraciones nuevas.

**Verificación adicional en vivo, no pedida explícitamente por los criterios pero relevante para la pregunta abierta de resiliencia:** con PostGIS parado (`docker compose stop db`), la petición devolvió `503` en 19ms con el mensaje del ADR 0005 ("Servicio de caché no disponible..."), sin degradar a Catastro directo. Al levantar PostGIS de nuevo, la siguiente petición volvió a servir desde caché en 40ms sin intervención manual.

## Fuera de alcance

- Expiración, TTL o cualquier refresco periódico del caché: esta historia trata el caché como permanente (ver "Contexto"). Decidir esa invalidación, si hace falta, es una historia futura.
- Qué pasa si Catastro cambia una geometría o atributo con el tiempo, o versionado histórico de `parcel`/`building`: ya estaba fuera de alcance en la historia 0003 y sigue sin resolverse aquí.
- Nuevas tablas, columnas o migraciones sobre el esquema de la historia 0003.
- Caché de otras fuentes (Sentinel-2, PNOA, BOE/BOCM, planeamiento): esta historia es exclusivamente la caché de lo que hoy provee `CatastroAdapter` (parcela y edificios).
- Resiliencia ante la caída de PostGIS (reintentos, circuit breaker, fallback automático a Catastro directo): el comportamiento concreto ante PostGIS no disponible es una pregunta abierta para el arquitecto, no se implementa un mecanismo de resiliencia específico en esta historia salvo el que el arquitecto decida como mínimo imprescindible.
- Invalidación manual (endpoint o comando para forzar un refresco de una referencia concreta).
- Cambios en `cli/` (composition root paralela a `api/`, ADR 0003): esta historia solo toca el flujo de `GET /reports/...`.
- Métricas de coste de LLM/TTS: no aplica, esta historia no toca ningún proveedor de LLM.

## Nota de cierre: excepción al criterio "ningún cambio de esquema"

El AC original decía explícitamente que esta historia no tocaría el esquema de la historia 0003. El code-reviewer encontró un riesgo real de corrupción de datos (duplicación permanente de `building` bajo escritura concurrente, ver `docs/lessons/LESSONS.md`) que solo se puede corregir correctamente con una restricción de unicidad en base de datos — se añadió la migración `0003_building_unique_reference` como excepción justificada a ese criterio: una corrección de integridad de datos encontrada en revisión prevalece sobre un alcance ya cerrado por escrito. No es una migración planeada de antemano ni alcance añadido por conveniencia.

## Preguntas abiertas

- ¿Se crea ya `ParcelRepositoryPort` (u otro nombre por capacidad) en `ports/`, con `PostgisParcelRepository` implementándolo y `GenerateParcelReportUseCase` recibiéndolo por inyección — dado que `CLAUDE.md` exige que `application/` "solo importe ports y domain, jamás un adapter" y esta es exactamente el caso de uso real que el ADR 0004 esperaba para crear el port — o se sigue instanciando la clase concreta directamente desde `api/main.py`, dejando `application/` sin tocar y la lógica de "leer caché, si falla ir a Catastro y guardar" en la capa de composición? Decisión del arquitecto; puede requerir ADR nuevo que amplíe o sustituya al ADR 0004 en ese punto.
- ¿Qué debe pasar si PostGIS no está disponible (contenedor parado) cuando llega una petición? ¿Degradar llamando a Catastro directamente (el informe sigue funcionando, pero sin cachear ni leer caché esa vez) o responder con un error claro (p. ej. 503) exigiendo que el operador levante el servicio? Afecta directamente a cómo se implementa el criterio de aceptación de "primera petición sigue llamando a Catastro" — decisión del arquitecto.
- Esta historia asume que los resultados negativos (`ParcelNotFoundError`, referencia inexistente en Catastro) nunca se cachean y se reintentan siempre contra Catastro. Si en producción esto resulta costoso (p. ej. un usuario reintentando muchas veces una referencia mal escrita), puede convenir cachear también el negativo con alguna marca explícita — pero no se implementa en esta historia sin que el fundador lo pida.
- Mecanismo concreto para verificar "cero llamadas HTTP nuevas a Catastro" en el test de la segunda petición: ¿un spy/contador inyectado sobre el cliente HTTP de `CatastroAdapter` (sin red, coherente con "los tests no llaman a red" de `CLAUDE.md`), o un test de integración que además mide tráfico de red real? Decisión del arquitecto sobre el mecanismo, no solo sobre el criterio.
- ¿La comprobación de "¿está ya en caché?" se hace con una lectura (`get_parcel`) que puede lanzar `ParcelNotFoundInRepositoryError`, capturada como señal de "cache miss", o conviene un método explícito `exists(cadastral_reference) -> bool` en el repositorio para no usar una excepción como control de flujo normal? Decisión del arquitecto.

## Métricas de éxito

- Peticiones repetidas a la misma referencia catastral generan 0 llamadas HTTP hacia Catastro, medido con el mecanismo de verificación que decida el arquitecto (spy/contador o test de integración de red).
- El tiempo de respuesta de una petición servida desde caché es perceptiblemente menor que el de una petición que sí llama a Catastro (medido informalmente con el mismo test de integración que ejercita ambos casos; no se fija un umbral numérico en esta historia por falta de infraestructura de carga).
- Ninguna historia futura que añada una fuente nueva (Sentinel-2, PNOA, boletines) necesita modificar el esquema de `parcel`/`building` ni el contrato del repositorio para convivir con esta caché — señal de que el corte de esta historia fue el correcto.
- El informe servido desde caché es indistinguible, para quien lo lee, del informe servido en vivo contra Catastro (criterio de aceptación de HTML idéntico).
