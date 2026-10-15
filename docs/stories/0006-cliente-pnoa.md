# 0006 — Cliente de PNOA: ortofotos actual e histórica recortadas a la parcela

## Historia

Como motor de Parcel Intel que necesita construir el módulo de datación (y, más adelante, el de construcciones), quiero un cliente que, dada una parcela, devuelva un recorte de la ortofoto actual y, opcionalmente, de un año histórico concreto, centrado en esa parcela con un margen configurable, para poder comparar visualmente lo construido en distintos momentos sin depender de coordenadas manuales ni de descargar ortofotos completas.

## Contexto

`src/parcel_intel/sources/REGISTRY.md` ya deja `confirmado`, con petición `GetMap` real contra la red, los dos servicios WMS de PNOA:

- Actual: `https://www.ign.es/wms-inspire/pnoa-ma`, capa `OI.OrthoimageCoverage`, formato `image/jpeg`, CRS nativo incluye `EPSG:25830`.
- Histórico: `https://www.ign.es/wms/pnoa-historico`, capas anuales `PNOA2004`...`PNOA2024` más los vuelos `AMS_1956-1957`, `Interministerial_1973-1986` y `Nacional_1981-1986`, mismo CRS y formato.

Ambos quedaron verificados en la historia 0001/0002 con fixtures reales (`tests/fixtures/pnoa/getmap_colmenar_actual.jpg`, `getmap_colmenar_2004.jpg`), con un bbox elegido manualmente centrado en Colmenar de Oreja — no calculado a partir de la geometría de ninguna parcela real. Esta historia es la primera en que el bbox pasa a calcularse a partir de una `Geometry` de dominio (la de `CatastroAdapter`, historia 0002), lo que puede producir un bbox distinto al de esas fixtures; por la lección registrada tras la historia 0001 ("nunca confiar en un supuesto sin petición real"), ese bbox nuevo debe verificarse contra la red real antes de darse por bueno, no asumirse equivalente al ya grabado.

Sigue el patrón ya establecido por `CatastroAdapter` (historia 0002): capacidad expuesta como port sin mencionar el proveedor, adapter que resuelve internamente la petición HTTP, y `Provenance` con la URL exacta usada. A diferencia de Catastro, el dato que se devuelve no es geometría estructurada sino una imagen — el diseño de dónde y cómo se cachea, y de qué entidad de dominio (si alguna, más allá de los bytes y su `Provenance`) representa el resultado, queda explícitamente para el arquitecto (ver "Preguntas abiertas").

Como en 0002 → 0004 → 0005, esta historia entrega **solo el cliente aislado** con sus propios tests, verificado contra fixtures reales; no toca `api/main.py` ni el informe HTML. Conectarlo al informe (mostrar la ortofoto junto a la parcela) es una historia posterior, a decidir cuándo el fundador lo pida — explícito en "Fuera de alcance", no asumido tácitamente.

## Criterios de aceptación — CERRADOS 2026-10-15

- [x] Dada una `Geometry` de dominio (p. ej. la de una `Parcel` ya resuelta por `CatastroAdapter`), el cliente calcula un bbox en `EPSG:25830` que cubre completamente el rectángulo envolvente de esa geometría más un margen en metros, aplicado en las cuatro direcciones. El margen es un parámetro con un valor por defecto documentado explícitamente en el código y la documentación de la historia/ADR correspondiente (no un "número mágico" sin comentar).
- [x] El cliente expone una capacidad para obtener la ortofoto **actual** de una parcela: hace `GetMap` contra `https://www.ign.es/wms-inspire/pnoa-ma`, capa `OI.OrthoimageCoverage`, formato `image/jpeg`, con el bbox calculado arriba, y devuelve los bytes JPEG recibidos tal cual (sin reprocesar ni recomprimir) junto con un `Provenance` (`source` identifica la fuente como PNOA actual, `url` es la URL completa de la petición `GetMap` incluyendo bbox, capa y todos los parámetros usados, `retrieved_at` es la fecha real de la llamada).
- [x] El cliente expone una capacidad para obtener la ortofoto **histórica** de una parcela para un año o vuelo concreto, aceptando como entrada únicamente los valores confirmados en `REGISTRY.md` (años `2004`–`2024` inclusive, cada uno mapeado a su capa `PNOA<año>`, más los tres vuelos nombrados `AMS_1956-1957`, `Interministerial_1973-1986`, `Nacional_1981-1986`). Hace `GetMap` contra `https://www.ign.es/wms/pnoa-historico` con la capa correspondiente y devuelve bytes JPEG + `Provenance` con la misma disciplina que el punto anterior (`source` distingue explícitamente "PNOA histórico" del "PNOA actual", y la `url` incluye la capa anual/vuelo usada).
- [x] Pedir un año o vuelo histórico que no esté en la lista confirmada de `REGISTRY.md` lanza un error explícito **antes de hacer ninguna petición de red**, con el valor pedido incluido en el mensaje — mismo patrón que `InvalidCadastralReferenceError` en `ports/errors.py`.
- [x] `Provenance.license` para ambas capacidades refleja fielmente el estado real documentado en `REGISTRY.md` para PNOA (`asumido`, pendiente de confirmación textual) — el cliente no afirma un texto de licencia concreto y verificado que `REGISTRY.md` no ha confirmado.
- [x] Si el bbox que el cliente calcula a partir de una `Geometry` real de prueba (p. ej. la parcela `REFCAT-RETIRADA` de Colmenar de Oreja, ya resuelta en la historia 0002) no coincide exactamente con el bbox ya usado al grabar `getmap_colmenar_actual.jpg` y `getmap_colmenar_2004.jpg`, se captura una petición `GetMap` real nueva con ese bbox exacto contra ambos servicios y se guarda como fixture nueva en `tests/fixtures/pnoa/` — las fixtures existentes solo se reutilizan si el bbox calculado coincide de verdad, nunca por asunción de equivalencia.
- [x] Al menos un test verifica el caso "parcela con margen configurado a un valor distinto del por defecto" y comprueba que el bbox resultante cambia en consecuencia (no basta con probar solo el valor por defecto).
- [x] `uv run pytest` pasa en verde con cero llamadas de red reales (todas las respuestas `GetMap` servidas desde fixtures grabadas).
- [x] `uv run mypy` (ejecutado literalmente, sin argumentos añadidos) pasa en verde.
- [x] `uv run ruff check .` pasa en verde.
- [x] `uv run lint-imports` pasa en verde: el cliente vive en `adapters/pnoa/`, el port correspondiente en `ports/`, sin que `application/` ni `domain/` importen nada de `adapters/`.
- [x] El port (o ports) nuevo no menciona "PNOA" ni "IGN" en su nombre ni en su interfaz pública, siguiendo el mismo criterio de nombrado por capacidad que `ParcelGeometryPort`/`BuildingGeometryPort` (ADR 0002).

## Fuera de alcance

- Conectar este cliente al informe HTML o a `api/main.py` — queda para una historia posterior, igual que Catastro esperó hasta la historia 0004 para conectarse al informe.
- Caché persistente de las imágenes descargadas en `data/` (filesystem, PostGIS u otra forma): esta historia solo exige que los tests no llamen a red vía fixtures grabadas, no que el adapter tenga caché de producción. La política de caché es decisión del arquitecto (ver "Preguntas abiertas").
- Cualquier procesamiento, análisis o detección sobre la imagen (comparar ortofotos de distintos años, detectar construcciones nuevas, medir superficies): eso es el pipeline de "Datación"/"Construcciones" de `docs/vision.md`, historia futura.
- PNOA LiDAR (otra fuente de `docs/vision.md`, tarea distinta).
- Soportar años o vuelos históricos no confirmados en `REGISTRY.md`; si se necesita cobertura adicional, es una actualización de ese registro, no de esta historia.
- Reproyección a un CRS distinto de `EPSG:25830` (que ya es el CRS nativo soportado y el de almacenamiento del proyecto).
- Resolución/tamaño de píxel óptimo para detectar construcciones pequeñas: esta historia solo exige que la petición `GetMap` especifique de forma explícita y documentada el ancho/alto pedido (no un valor implícito del servicio); afinar esa resolución para el caso de uso de datación es tarea de la historia de detección.

## Preguntas abiertas

- ¿Qué entidad de dominio representa el resultado — se crea ya una entidad simple (p. ej. `Orthophoto`: bytes/referencia, bbox, fecha o año, `Provenance`), se adelanta una versión reducida de `observation` (sin "tipo de cambio" ni "confianza", que no aplican aquí), o el cliente devuelve directamente una tupla `(bytes, Provenance)` sin entidad de dominio nueva en esta historia? Decisión del arquitecto.
- ¿Un solo port que sirve ortofoto actual e histórica (con parámetro de año/vuelo opcional) o dos ports separados? Decisión del arquitecto, con el mismo criterio de nombrado por capacidad que ya rige en `ports/geometry.py`.
- ¿Dónde y cómo se cachean las imágenes descargadas — filesystem en `data/pnoa/...`, PostGIS como `bytea`/large object, o no se cachea todavía en esta historia (igual que PostGIS no se introdujo hasta que hubo caso de uso real en la historia 0003)? Decisión del arquitecto; si decide "no cachear todavía", debe quedar explícito como tal, no como omisión.
- Valor por defecto del margen configurable en metros: ¿mismo criterio que el margen de Sentinel-2 (tarea 4 de `docs/vision.md`, aún no implementada) o un valor propio para PNOA, dado que su resolución submétrica permite un margen más ajustado que el de Sentinel-2 (10 m/píxel)? Decisión del arquitecto.
- Forma exacta del parámetro de año/vuelo histórico en la interfaz pública: ¿un `int` para los años 2004–2024 con los tres vuelos nombrados como un tipo `Literal` aparte, o un único tipo que los unifique? Decisión del arquitecto.

## Métricas de éxito

- Cero reaperturas de esta historia por "el bbox calculado no es el que de verdad acepta el servicio" — el criterio de verificación de bbox contra red real (arriba) existe precisamente para evitarlo antes de cerrar la historia, no después.
- Al menos una ortofoto actual y una histórica de una parcela real y verificable en persona por el fundador (Colmenar de Oreja o Villaconejos) obtenidas end-to-end por el cliente, sentando la base empírica para el futuro `tests/golden/` del módulo de datación.
- `uv run pytest`, `uv run mypy`, `uv run ruff check .` y `uv run lint-imports` en verde, ejecutados literalmente como en `CLAUDE.md`, antes de cerrar la historia.
