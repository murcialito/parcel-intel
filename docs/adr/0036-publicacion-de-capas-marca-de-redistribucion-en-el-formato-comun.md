# ADR 0036 — Publicación de capas: la marca de redistribución viaja en el formato común y un único sink escribe site/datos

- Estado: aceptada
- Fecha: 2026-11-26
- Historia: #84 (feature #82); consumidores: #85 (visor) y #86 (resto del ámbito)

## Contexto

El primer hito (ADR 0021) publica como ficheros estáticos las capas de vías pecuarias (IDEM, CC BY 4.0 Comunidad de Madrid) y de camino actual (red de transporte del IGN, CC BY 4.0). El ADR 0028 fijó la marca `Provenance.redistribution` y la puerta `PublishableLayer`, pero las capas derivadas del formato común (ADR 0030) no guardaban la marca: el lector la reconstruía siempre como `INTERNAL_ONLY`, y el adapter de vías pecuarias ni siquiera la ponía. `scripts/construir_sitio.py` exige además un `.procedencia.json` con `redistribucion: "publicable"` por fichero de datos. Faltaba decidir cómo llega la marca del adapter al fichero publicado, en qué CRS y formato se publica y cómo encuentra el visor los municipios.

## Decisión

1. **La marca viaja con el dato.** Los escritores de capa derivada escriben `redistribucion` en cada procedencia con los valores de `Redistribution` (`publicable`, `solo_uso_interno`). El lector la reconstruye; si falta, `INTERNAL_ONLY`; si es otro valor, error de formato. La pone el adapter de la fuente (ADR 0028): `RoadNetworkAdapter` y ahora `LivestockTrailAdapter`. Se descarta una lista blanca de fuentes en la composición: duplicaría `REDISTRIBUTABLE_SOURCES` y dejaría pasar un fichero cuya procedencia dice otra cosa.
2. **La puerta también mira la capa.** `PublishableLayer` pasa a ser genérica (`PublishableLayer[T]`) y acepta `layer_provenance`, que también debe ser `PUBLIC`. Una capa vacía con procedencia interna ya no pasa.
3. **Catálogo único de capas publicables** en `domain/published_layers.py` (`PUBLISHED_LAYERS`): identificador de capa, fuente, atribución literal de `NOTICE` y aviso. Catastro no está. Añadir una capa exige ADR.
4. **Un port de salida**, `PublishedLayerSink.publish(publicaciones)`, que solo acepta publicaciones construidas sobre `PublishableLayer`. Todo o nada: se valida y serializa todo, índice incluido, antes de escribir; nunca se borra lo publicado. Caso de uso `PublishLayersUseCase`, CLI `publicar-capas`.
5. **Formato publicado**: GeoJSON RFC 7946 en EPSG:4326 (`[lon, lat]`, 6 decimales, sin `crs`), compacto y determinista, con lista blanca cerrada de propiedades (`nombre`, `tipo`, `fecha_dato`, `procedencia`). Reproyección (pyproj) y simplificación (shapely) solo en el adapter; todo cálculo métrico sigue en EPSG:25830.
6. **Índice** `site/datos/indice.json` con su procedencia, regenerado entero en cada publicación a partir de lo que hay en `site/datos/`, para que el visor no tenga que listar directorios.
7. **`site/datos/` va en git**: el despliegue construye el sitio desde el repositorio y CI no tiene `data/`. Se regenera desde la caché con `--sin-red`.

### Umbrales y criterios de producto (a revisar con el fundador)

- Umbral de 3 000 000 bytes por fichero (alineado con #86) y tolerancia de simplificación de 2,0 m, aplicada en EPSG:25830 solo por encima del umbral.
- La atribución pública de camino actual es la de `NOTICE` («Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional»), no la del fichero derivado de #27. Aplica el ADR 0035.
- No se publican `fictitious`, longitudes, áreas ni códigos internos; sí `nombre` y `tipo` de la vía pecuaria tal como los da IDEM.
- Las astillas de recorte (12 piezas de vías pecuarias del ámbito por debajo de 1 m², ADR 0032) se publican: son invisibles y quitarlas es un umbral pendiente del fundador.
- Una capa vacía no se publica, y el municipio sin capas no entra en el índice.
- La procedencia del límite municipal del IGN usado para recortar va en el `.procedencia.json`, pero el visor solo muestra la atribución de la capa.

## Consecuencias

- Los ficheros ya escritos en `data/derived/` sin marca no se publican hasta regenerarlos con `vias-pecuarias-municipios --sin-red` y `camino-actual-municipios --sin-red`.
- `TrailLayer` gana `municipality_name` y `boundary_provenance` opcionales; las discrepancias no cambian.
- Cada regeneración con datos nuevos añade al historial de git el peso de los ficheros cambiados; la serialización determinista evita diffs sin cambios. Si el peso crece, el siguiente paso son teselas vectoriales (#86 documenta el disparador).
- El límite municipal no se marca `PUBLIC` porque no se publica como capa. Si algún día se publica, necesita su atribución verificada (NOTICE la tiene «pendiente de verificar»).
- Ningún LLM interviene y no hay coste recurrente: ficheros estáticos en GitHub Pages.

### Notas de implementación (#84)

- **Capa vacía (resuelto en #86).** El escritor de #83 toma la procedencia de una capa sin piezas del límite del IGN, que no está marcado `PUBLIC` (caso real: vías pecuarias de Belmonte de Tajo, 28019, 0 piezas). Se decidió **omitir la capa vacía antes de la puerta**: no publica ningún dato, así que no hay nada que redistribuir. El caso de uso la cuenta en `empty` y el comando imprime «capa vacía, no se publica». `PublishableLayer` sigue rechazando una colección vacía con procedencia interna (el dominio no cambia); lo que cambia es que el caso de uso ya no se la pasa. Se descartó tomar la procedencia de la consulta de IDEM: el adapter devuelve `[]` y la pierde.
- Una parte de polígono o de línea que la simplificación dejaría vacía o degenerada se conserva sin simplificar; una parte diminuta puede quedarse en un triángulo, pero nunca desaparece.
- `bbox` del índice se calcula sobre las coordenadas ya redondeadas, así contiene todas las publicadas.
