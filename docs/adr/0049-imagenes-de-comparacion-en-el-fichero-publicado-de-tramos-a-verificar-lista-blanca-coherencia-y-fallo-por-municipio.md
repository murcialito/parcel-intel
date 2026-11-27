# ADR 0049 — Imágenes de comparación en el fichero publicado de tramos a verificar: lista blanca, coherencia con el tramo y fallo por municipio

- Estado: aceptada
- Fecha: 2026-11-27
- Historia: #172 (feature #103). Consumidores: #178 (visor) y #107 (dossier). Aplica los ADR 0042 §5–§7 y 0048. Amplía el ADR 0048 §5 y §8.

## Contexto

El ADR 0042 §5 decidió publicar las imágenes de comparación como enlaces al WMS del IGN con un manifiesto, no como ficheros JPEG en `site/`. `imagenes-comparacion` (#122) escribe el manifiesto interno `data/derived/comparacion/<ine>.json` y `publicar-candidatos` (#170, ADR 0048) publica los tramos aprobados sin imágenes. Faltaba decidir qué sale del manifiesto al fichero publicado, cómo se garantiza que las URL y los trazos publicados son los comprobados y qué pasa cuando un aprobado no tiene imágenes válidas.

El manifiesto no lleva la huella del candidato: si el candidato se regenera después de `imagenes-comparacion`, el trazo en píxeles del manifiesto ya no es el del tramo publicado.

## Decisión

1. **Lista blanca cerrada por feature** (`imagenes_comparacion`): por ventana, `ancho_px`, `alto_px`, `trazo_px` (todas las partes), `imagenes` en orden de `COMPARISON_SLOTS` (`url`, `franja`, `periodo`, `resolucion_m`, `atribucion` con «Obra derivada de», `texto_alternativo`) y `omitidas` (`franja`, `texto`). No salen `sha256`, `bytes`, `vuelo`, procedencia interna, `bbox` ni `srid`: la URL ya lleva el encuadre. En la colección, el bloque `comparacion` con la política, los huecos y dos textos fijos. Todo texto se redacta en el dominio (`domain/published_comparison.py`, ADR 0044): el visor no compone nada.
2. **URL = la comprobada.** El lector del manifiesto exige que la URL de cada imagen sea exactamente `window_url(ventana, vuelo)`, la URL canónica de la caché cruda (`canonical_url`, una sola función compartida por `CachedRawFetcher` y el lector). Esto cierra servidor, capa y parámetros.
3. **Coherencia con el tramo.** El dominio recalcula `comparison_windows` y `stretch_pixels` desde el tramo actual del candidato y exige igualdad exacta con el manifiesto. Las coordenadas salen del mismo fichero a 0,01 m en los dos comandos, así que no hace falta tolerancia. Si no coinciden, se pide volver a ejecutar `imagenes-comparacion`.
4. **Política y huecos.** El manifiesto debe ser de `COMPARISON_POLICY` y traer `DECLARED_GAPS`; cada ventana cubre las cinco franjas una vez. Una franja con `fallo` es una incoherencia (`imagenes-comparacion` no escribe manifiestos con fallos).
5. **Atribución y licencia por imagen** iguales a ADR 0042 §3 (`FLIGHTS`, `attribution_for`), fuente `pnoa-historico`, `CC BY 4.0`, `publicable`.
6. **Fallo por municipio, nunca omisión.** Sin manifiesto, o con un aprobado ausente, `tramo_demasiado_largo`, sin ninguna imagen, incoherente o fuera de la lista blanca: falla el municipio, con el `candidate_id` y el motivo, y no se escribe nada (como ADR 0048 §6). La revisión de #168 ya muestra la disponibilidad antes de aprobar. Las comprobaciones de licencia del trazado (#170) van antes que las de imágenes.
7. **Peso.** El fichero de candidatos que pase de 3.000.000 bytes hace fallar la publicación (ADR 0042 §5), no solo avisa. Solo en este sink; `over_threshold` queda siempre falso aquí y la línea «AVISO: por encima del umbral» de `publicar-candidatos` desaparece.
8. **Procedencia.** El `.procedencia.json` añade una fuente por vuelo publicado (servidor, fecha de descarga más reciente, licencia, atribución) y un bloque `imagenes_comparacion` que dice que las imágenes las sirve el IGN y no se alojan en el sitio. La `atribucion` de la colección suma las de las ortofotos y la fecha de la capa es la más reciente entre evidencia e imágenes. `NOTICE` lista las cadenas «Obra derivada de …» de cada vuelo.
9. **Port y adapter propios.** `ComparisonManifestSource.get_manifest` y `JsonComparisonManifestReader` (pydantic en el borde) devuelven `ComparisonManifest` con las entidades de `domain/comparison_image.py`. El lector de disponibilidad de #168 se queda como está.

### Umbrales y decisiones de producto a revisar con el fundador

No bloquean; cambiarlos solo toca este ADR, el dominio y sus tests.

- Los textos «sin cobertura de ese vuelo», «Ortofoto de <periodo> con el tramo a verificar marcado», «Imagen no disponible», el de los huecos («De 1957 a 1997: <motivo>.») y la nota «Las imágenes de comparación las sirve el Instituto Geográfico Nacional al abrir la ficha; este sitio no aloja ninguna.».
- Que un aprobado sin imágenes haga fallar el municipio en lugar de publicarse sin ellas.
- Que el visitante cargue las imágenes desde el IGN (ya en ADR 0042).

### Alternativas descartadas

- **Omitir en silencio las imágenes de un aprobado sin manifiesto válido**: un fallo de proceso quedaría oculto.
- **Copiar la URL del manifiesto sin comprobarla**: un manifiesto editado a mano podría enlazar cualquier servidor.
- **Guardar la huella del candidato en el manifiesto**: obliga a cambiar #122 y su formato; el recálculo da la misma garantía con las funciones puras ya existentes.
- **Recalcular la URL en el dominio**: el formato de la petición WMS es del adapter de PNOA.
- **Reutilizar el lector de disponibilidad de #168**: solo lee el estado y su fixture no tiene la forma real.

## Consecuencias

- `publicar-candidatos` exige `imagenes-comparacion` antes, con el mismo fichero interno de candidatos como `--tramos`, y gana `--comparacion` (por defecto `data/derived/comparacion`).
- Regenerar los candidatos obliga a regenerar las imágenes (y a revisar de nuevo si cambia la huella, ADR 0047).
- Los tests de #170 se actualizan a la forma nueva.
- Sin dependencias nuevas, sin proveedor nuevo, sin coste recurrente y sin LLM.
- Riesgo residual: dos lectores del mismo formato (#168 y este). El test de ida y vuelta con `manifest_text` (`tests/adapters/comparison_files/test_manifest_reader.py`) vigila el de esta historia.
- Riesgo residual del ADR 0042 §5 (b): el IGN cambia la capa o deja de responder. CA11 de #172 lo vigila en `red-externa` sin bloquear; el visor (#178) dice «Imagen no disponible».
