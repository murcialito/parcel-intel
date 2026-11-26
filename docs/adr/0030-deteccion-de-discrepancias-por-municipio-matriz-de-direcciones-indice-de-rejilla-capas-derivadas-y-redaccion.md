# ADR 0030 — Detección de discrepancias por municipio: matriz de direcciones, índice de rejilla, capas derivadas en GeoJSON y redacción de fuentes no redistribuibles

- Estado: aceptada
- Fecha: 2026-11-26
- Historias: #15 (hijas A #31 y B #32); aplica el criterio del ADR 0025 (#14) y la entidad del ADR 0029 (#22)

## Contexto

El primer hito (ADR 0021) pide mostrar las discrepancias entre fuentes de trazados sin elegir una en silencio. #14 define qué es una discrepancia entre un trazado y los de otra fuente y con qué tolerancia. Falta decidir cómo se aplica eso a todas las capas de un municipio: qué pares se comparan y en qué dirección, cómo se evita el coste cuadrático en Python puro (el dominio solo usa stdlib), de dónde salen las capas, en qué fichero se escribe el resultado y cómo se trata una fuente cuya licencia no permite redistribuir su geometría (Catastro INSPIRE, licencia de 2016).

Las fuentes no tienen el mismo alcance. La red del IGN recoge todo camino actual, público o privado. Catastro `VT` recoge las vías de dominio público. Vías pecuarias solo recoge vías pecuarias. La cartografía histórica recoge los caminos de su fecha. Que un trazado de A falte en B solo es un indicio si B debería contenerlo.

## Decisión

1. **Pares y direcciones.** Se evalúa cada par ordenado de fuentes disponibles. `AUSENTE_EN_FUENTE` y `SOLAPE` se conservan solo para los pares de `domain/discrepancy_policy.py::ABSENCE_PAIRS`: vías pecuarias → Catastro, IGN y las dos fuentes históricas; Catastro → IGN; cada histórica → Catastro e IGN. `DESPLAZAMIENTO`, que es simétrico, se conserva solo en la dirección canónica (A antes que B al ordenar las cadenas de `SourceKind`). Un trazado con `role == "anejo"` (abrevadero, descansadero) no es sujeto de ausencia ni de solape: es una superficie de descanso, no un trazado que deba aparecer en otra fuente.
2. **Prefiltro espacial.** Índice de rejilla uniforme (`domain/spatial_index.py`, celda de 250 m) sobre el bbox de cada trazado. Se consulta con el bbox del trazado evaluado ampliado por `correspondence_radius_m` del par (ADR 0025). Es un superconjunto exacto: un test compara contra fuerza bruta. Se descartan R-tree y shapely: no hacen falta para estos volúmenes y el dominio no admite terceros.
3. **Entradas como capas derivadas.** El caso de uso lee, mediante un único port (`MunicipalTrailLayerPort`), capas ya producidas por sus historias. No llama a red. Que no haya capa es "fuente ausente" (`TrailLayerUnavailableError`) y se registra con su motivo; cualquier otro error es un fallo real y se propaga, para que una fuente rota no baje en silencio el número de discrepancias. La lectura de ficheros GeoJSON es de #32.
4. **Redistribución, denegada por defecto.** `REDISTRIBUTABLE_SOURCES` (vías pecuarias, red del IGN —licencia CC BY confirmada en #24— y las dos históricas) se declara en un único sitio. `redact_for_publication` (dominio, función pura) quita la geometría de los trazados de las demás fuentes y la zona cuando el lado A no es redistribuible, y conserva identificador, procedencia, medidas y confianza. El caso de uso escribe el informe completo en un sink interno y el redactado en otro público.
5. **Identificador de registro.** Los 16 primeros hexadecimales de `sha256` sobre un JSON canónico del criterio (con versión), tipo, fuentes, trazado, contrapartes y zona redondeada a 0,01 m. Estable entre ejecuciones; cambia si cambian los datos.
6. **Determinismo.** Capas ordenadas por fuente y trazados por identificador; registros en orden canónico `(tipo, fuente A, trazado A, fuente B, contrapartes, record_id)`; nunca se itera un `set` sin ordenar y no hay marcas de tiempo.
7. **Fecha del dato de la capa.** El criterio de #14 exige que todas las contrapartes compartan `SourceRef`. Se construye uno por capa con la procedencia de la capa y, como fecha del dato, la común a todos sus trazados o `None` si difieren. La fecha de cada trazado se conserva en su `TrailEvidence`.
8. **Capas incoherentes.** Fuente repetida, trazado de otra fuente o municipio, o identificador repetido dentro de una capa lanzan `InconsistentLayersError`: mezclarlos en silencio falsearía las discrepancias.

### Umbrales de producto a revisar con el fundador

Están razonados, pero deciden lo que verá el usuario. Se pueden cambiar sin tocar la arquitectura:

- La matriz `ABSENCE_PAIRS`. En particular, si "camino del IGN sin parcela `VT` en Catastro" (posible camino privado) debería salir como indicio. Hoy no sale.
- Excluir los anejos como sujeto de ausencia y solape.
- `REDISTRIBUTABLE_SOURCES` incluye `ign_red_transporte` porque #24 ya confirmó CC BY (atribución obligatoria junto a la capa, a cargo de la publicación). El diseño de #15 la dejaba fuera "hasta cerrar #24".
- Si el fichero publicable puede llevar referencias de parcelas de camino de Catastro. Se decide en la historia de publicación del visor (#6).

## Consecuencias

- Las historias productoras de capas (#23, #27, #29 y la futura carga de históricos) y la lectura de ficheros (#32) escriben o leen un formato común. Una fuente nueva se suma con un valor de `SourceKind` y, si procede, una fila en `ABSENCE_PAIRS` y `REDISTRIBUTABLE_SOURCES`, sin tocar el caso de uso.
- El informe interno contiene geometría de Catastro: vive en `data/`, fuera de git, y ningún despliegue debe tomarlo.
- La rejilla asume trazados de tamaño parecido a la celda. Un trazado muy largo (una cañada de decenas de km) ocupa muchas celdas, lo que es correcto pero más lento. Medido: 4 fuentes × 1.500 trazados sintéticos en un área de 10 × 10 km tardan unos 7 s. Si con datos reales se acerca al límite, el siguiente paso es partir los trazados largos antes de indexar, no cambiar de librería.
- La zona de un registro redactado se representa con una geometría sin partes (`rings=()`) y `zone_redacted=True`; el escritor la saca como `geometry: null`.
- Ningún LLM interviene. Las medidas y la confianza son deterministas (ADR 0025).
