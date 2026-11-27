# ADR 0042 — Imágenes de comparación: ventanas del tramo, cinco franjas de vuelo, caché cruda de PNOA y enlaces al WMS

- Estado: aceptada
- Fecha: 2026-11-26
- Historia: #120 (feature #101, épica #5). Consumidores: #121, #122 y la historia del adapter de ventanas; #103 (publicación de candidatos) y #106 (serie del dossier).
- Cierra el riesgo del ADR 0006 §6. Reutiliza los ADR 0036 (puerta de publicación), 0037 (visor), 0039 (candidatos) y la caché cruda de #34.

## Contexto

La épica #5 pide, para cada candidato a corte, imágenes de comparación con atribución: la
ortofoto histórica frente a la actual del mismo tramo. La pieza la reutiliza el dossier (#106).
El tramo es una `MultiLineGeometry` en EPSG:25830 (ADR 0039 §3); `OrthophotoPort` recibe una
`Geometry` con margen y el adapter fija 512×512 píxeles, así que una ventana no cuadrada saldría
deformada. El ADR 0006 §6 dejó la caché de PNOA diferida hasta que hubiera un consumidor que
repitiera peticiones: el lote por municipio lo es. El sitio tiene un presupuesto de peso (#86:
3 MB por fichero, 8 MB por pantalla, 40 MB en total; hoy pesa 1,28 MB) y `site/datos/` está en
git (ADR 0036 §7).

Verificación real del 2026-11-26 (detalle en `REGISTRY.md`), ventana rural de Colmenar de Oreja
de 512 m a 1024 píxeles:

| Capa | Bytes |
| --- | --- |
| `PNOA2023` (histórico) | 243.158 |
| `OI.OrthoimageCoverage` (máxima actualidad) | 228.719 |
| `PNOA2017` | 167.525 |
| `PNOA2009` | 238.891 |
| `SIGPAC` | 155.801 |
| `OLISTAT` | 140.609 |
| `AMS_1956-1957` | 158.660 |
| `PNOA2010` (sin vuelo sobre Madrid: imagen blanca, sin error) | 6.427 |
| `PNOA2023`, ventana de 200 m a 400 píxeles | 41.968 |

La misma URL devuelve los mismos bytes, también con la forma canónica de la caché. El servicio
responde con `access-control-allow-origin: *` y `cache-control: max-age=31536000`.

## Decisión

### 1. Formato, tamaño y margen

- **JPEG tal como lo sirve el WMS**, sin recodificar: la calidad la fija el IGN y no se pierde
  nada en una segunda compresión. Ninguna librería de imagen.
- **Resolución fija de 0,5 m por píxel** (`GROUND_RESOLUTION_M`), la nativa del AMS, SIGPAC, 2006
  y 2009; los vuelos de 25 cm se ven a la mitad, suficiente para un camino de 3 a 5 m.
- **Ventana cuadrada** en EPSG:25830, con esquinas en metros enteros:
  - margen de `STRETCH_MARGIN_M = 50` m alrededor del tramo;
  - lado múltiplo de `WINDOW_SIDE_STEP_M = 32` m, entre `MIN_WINDOW_SIDE_M = 224` y
    `MAX_WINDOW_SIDE_M = 512` m, es decir, entre 448 y 1024 píxeles por lado.
- **Peso estimado por imagen**: ~0,23 bytes por píxel (medido: 0,134–0,262). Ventana máxima,
  ~0,2 MB por imagen; ventana mínima, ~47 kB.

### 2. Ventanas de un tramo (cómo se pide la ortofoto de una línea)

Sin tocar `OrthophotoPort`. Port nuevo y pequeño `OrthophotoWindowPort.get_orthophoto_window(
window: OrthophotoWindow, vintage: HistoricalVintage) -> Orthophoto`, con un recorte exacto
(bbox entero y píxeles), que también usará la señal de imagen del ADR 0039 (H4). La política del
recorte vive en `domain/comparison_image.py`, función pura `comparison_windows(stretch)`:

1. Se toman las partes del tramo **en orden, todas**; las de menos de 2 puntos o longitud 0 se
   ignoran. Si no queda ninguna, `DegenerateStretchError` antes de pedir nada (tramo vacío, de un
   punto o de puntos repetidos).
2. Cada parte se densifica a `DENSIFY_STEP_M = 5` m (`ceil(L / 5)` piezas iguales por segmento,
   vértices incluidos).
3. Los puntos se agrupan en trozos consecutivos: se cierra un trozo cuando añadir el siguiente
   punto haría que `max(ancho, alto)` del trozo pasara de `MAX_WINDOW_SIDE_M − 2·margen − 1`
   = 411 m. Un trozo puede reunir puntos de dos partes cercanas.
4. Cada trozo da una ventana: centro = centro de su bbox redondeado al metro
   (`floor(v + 0,5)`); lado = `max(224, ceil((extensión + 2·50 + 1) / 32) · 32)`; píxeles =
   lado / 0,5. El metro de holgura absorbe el redondeo del centro.
5. Si salen más de `MAX_WINDOWS_PER_STRETCH = 4` ventanas (unos 1,6 km de tramo recto), el
   tramo queda `tramo_demasiado_largo`, sin imágenes y sin peticiones.

El trazado se superpone con `stretch_pixels(stretch, window)`: todas las partes, en píxeles de
la ventana (`px = (x − min_x) / 0,5`, `py = (max_y − y) / 0,5`), redondeados a 0,1.

**Oráculos** (`X0 = 470000`, `Y0 = 4440000`, EPSG:25830; tramos sobre `y = Y0`):

| Tramo | Ventanas (min_x, min_y, max_x, max_y) | Píxeles |
| --- | --- | --- |
| `(X0, Y0)`→`(X0+80, Y0)` | (469928, 4439888, 470152, 4440112) | 448; extremos del trazado en (144.0, 224.0) y (304.0, 224.0) |
| `(X0, Y0)`→`(X0+300, Y0)` | (469942, 4439792, 470358, 4440208) | 832 |
| `(X0, Y0)`→`(X0+1000, Y0)` | trozos x∈[0, 410], [415, 825], [830, 1000]: (469949, 4439744, 470461, 4440256), (470364, 4439744, 470876, 4440256), (470771, 4439856, 471059, 4440144) | 1024, 1024, 576 |
| `(X0, Y0)`→`(X0+2000, Y0)` | 5 trozos > 4: `tramo_demasiado_largo`, ninguna ventana | — |
| Multiparte `(X0, Y0)`→`(X0+50, Y0)` y `(X0+3000, Y0)`→`(X0+3050, Y0)` | (469913, 4439888, 470137, 4440112) y (472913, 4439888, 473137, 4440112) | 448, 448 |
| `lines=()`, una parte de 1 punto, una parte de 2 puntos iguales | `DegenerateStretchError` | — |

### 3. Vuelos: cinco franjas por ventana, en orden cronológico

`COMPARISON_SLOTS` (máximo 5 imágenes por ventana y 20 por tramo):

| Franja | Vuelos, por orden de preferencia | Resolución | Atribución (SCNE, literal) |
| --- | --- | --- | --- |
| `1956-1957` | `AMS_1956-1957` | 0,5 m | `Orto-AMS 1956-1957 CC-BY 4.0 ejercito.defensa.gob.es` |
| `1997-2003` | `SIGPAC`, `OLISTAT` | 0,5 m / 1 m | `Orto-SIGPAC 1997-2003 CC-BY 4.0 scne.es` / `Orto-OLISTAT 1997-1999 CC-BY 4.0 scne.es` |
| `2006-2011` | `2009`, `2006`, `2011` | 0,5 / 0,5 / 0,25 m | `PNOA <año> CC-BY 4.0 scne.es` |
| `2014-2020` | `2017`, `2014`, `2020` | 0,25 m | `PNOA <año> CC-BY 4.0 scne.es` |
| `reciente` | `2023` (`RECENT_FLIGHT_YEAR`) | 0,25 m | `PNOA 2023 CC-BY 4.0 scne.es` |

- `HistoricalVintage` gana `"SIGPAC"` y `"OLISTAT"`, que el WMS histórico ya sirve.
- La imagen **reciente** se pide a la capa anual `PNOA2023` del servicio histórico, no al mosaico
  de máxima actualidad: es el mismo vuelo (2023-07, 25 cm, `REGISTRY.md`), pero la capa anual
  tiene un año único y conocido, así que la atribución es exacta sin `GetFeatureInfo`. Cuando
  cambie el vuelo sobre Madrid (el test de integración CA10 de #85 lo detecta), se actualizan
  `RECENT_FLIGHT_YEAR`, `NOTICE`, `REGISTRY.md` y `site/config.js` juntos, y sube
  `COMPARISON_POLICY.version`.
- **Hueco declarado**: `DECLARED_GAPS` = de 1957 a 1997 no hay ortofoto en el servicio sobre el
  ámbito (los vuelos Interministerial y Nacional no tienen imagen en él, `REGISTRY.md`). No se
  piden, no se rellenan con otra cosa y el hueco viaja con cada resultado.
- **Vuelo que no cubre**: el WMS devuelve una imagen blanca sin error. El adapter la detecta por
  tamaño (`< 0,02` bytes por píxel; medido: blancas ≤ 0,007, reales ≥ 0,061) y lanza
  `OrthophotoNotCoveredError`. La franja prueba el siguiente vuelo de su lista; si ninguno
  cubre, se omite con motivo `sin_cobertura` y la lista de vuelos probados. Nunca se toma un vuelo
  de otra franja.
- **Fallo** de una petición (red, `ServiceException`, caché ausente con `--sin-red`): la franja se
  omite con motivo `fallo` y el tipo de error, **sin** probar alternativas (un error no es falta de
  cobertura). El resto de franjas sigue. El comando por lotes sale con 1 si hay algún `fallo`.

### 4. Caché cruda (cierra el ADR 0006 §6)

- `PnoaWindowAdapter` pide a través de `CachedRawFetcher` (#34): `data/raw/`, clave = sha256 de la
  URL canónica (parámetros ordenados), cuerpo inmutable y sidecar con URL, parámetros, fecha de la
  descarga real y sha256. La clave es estable porque la ventana tiene esquinas enteras.
- `validate` exige cabecera JPEG (`\xff\xd8`): una respuesta de error no entra nunca en la caché.
  Las imágenes blancas sí entran: son la respuesta real y así `--sin-red` decide igual.
- Pausa de 1 s entre peticiones y User-Agent del proyecto (lección de #17).
- Los métodos de `OrthophotoPort` (informe por parcela) siguen sin caché: no tienen hoy un
  consumidor por lotes. Quien los conecte a uno usa este mismo fetcher.

### 5. Publicación: enlaces al WMS, no ficheros de imagen

| | Ficheros JPEG en `site/` | Enlaces al WMS con manifiesto (elegida) | Capa WMS en el mapa |
| --- | --- | --- | --- |
| Peso por ventana en el sitio | ~0,96 MB (5 imágenes de 1024 px medidas) a ~0,23 MB (224 m) | ~1,5–3 kB (5 URL, atribuciones y píxeles del trazado) | 0 |
| Peso por tramo (1–4 ventanas) | 0,23–3,9 MB | 2–12 kB | 0 |
| Por municipio (supuesto: 50 tramos, 1,5 ventanas de media) | ~45 MB: **supera solo él los 40 MB de #86** | ~0,2 MB | 0 |
| Historial de git | cada regeneración añade binarios para siempre (ADR 0036 §7) | texto pequeño | nada |
| Coste recurrente | 0 € (Pages), pero choca con los límites de Pages y del repo | 0 € | 0 € |
| Encuadre fijo y comprobado (cobertura) | sí | sí: las URL son las mismas que se descargaron y comprobaron | no: teselas 3857 sin comprobar |
| Dependencia en la visita | ninguna | el IGN, igual que el mapa base (ADR 0037) | el IGN |

**Se elige enlaces con manifiesto.** El lote descarga y comprueba cada imagen (caché en
`data/raw/`); el sitio solo publica, por tramo publicado, la URL canónica de cada imagen, su
franja, año, resolución, atribución y los píxeles del trazado. El navegador pide la imagen al IGN
al abrir la ficha (`loading="lazy"`), y la misma URL da los mismos bytes que se comprobaron. Si
el IGN no responde, la ficha dice «imagen no disponible» con su atribución; nunca se sustituye.

- **Topes**: `MAX_WINDOWS_PER_STRETCH = 4`; `MAX_WINDOWS_PER_MUNICIPALITY = 400` (de 2.000 a
  4.000 peticiones con las alternativas, ~1 h con la pausa de 1 s, y ~0,4 GB en `data/raw/` por
  municipio; el comando falla con 1 antes de pedir nada si se supera); y manifiesto publicado
  ≤ 3.000.000 bytes (umbral por fichero de #86).
- La puerta de publicación es la del ADR 0036 y la aplica #103: solo se publican las imágenes de
  candidatos publicados; los píxeles del trazado son geometría del tramo y siguen su regla
  (ADR 0039 §7: solo si la fuente A está en `REDISTRIBUTABLE_SOURCES`).
- Atribución en el visor y en el dossier: `Obra derivada de <atribución SCNE>` (la imagen está
  remuestreada a 0,5 m y lleva el trazado encima). `NOTICE` se actualiza en la historia que
  publique (#103), con las cadenas de §3.

### 6. Superposición del trazado: en la vista, no en la imagen

Se dibuja como SVG encima del `<img>` (`viewBox="0 0 ancho alto"`, `polyline` con los píxeles
del manifiesto), en la ficha del visor y en el dossier. Ninguna librería nueva: no hay que
decodificar ni recodificar JPEG, la imagen publicada es exactamente la del IGN y el trazado se
puede ocultar. El SVG se construye con `createElementNS` y atributos, nunca con `innerHTML`
(lección de #85), y no usa Leaflet (`mapa.js` sigue aislado, ADR 0037). Si un día el dossier
exige un PDF con la imagen compuesta, la librería se decide en #107 y vive en `adapters/`.

### 7. Procedencia y lo que nunca lleva una imagen

Cada `ComparisonImage` lleva: franja, vuelo, periodo, resolución, atribución con «Obra derivada
de», sha256, bytes y `Provenance` (fuente `pnoa-historico`, URL canónica del `GetMap`, fecha de
la descarga real del sidecar, licencia `CC BY 4.0`, `publicable`). Ni la imagen, ni la caché
(nombrada por sha256), ni el manifiesto (nombrado por INE) llevan referencia catastral, nombre de
finca, de paraje ni de persona: el tramo se identifica con un id opaco de 16 hexadecimales
(`StretchRequest.__post_init__` rechaza cualquier otra forma).

### 8. Historias que se derivan, en orden

| # | Historia | Talla | Depende de |
| --- | --- | --- | --- |
| 1 | #121: `OrthophotoWindow`, `OrthophotoWindowPort`, `domain/comparison_image.py` y `BuildComparisonImagesUseCase` | m | este ADR |
| 2 | Adapter `PnoaWindowAdapter` con caché cruda, detección de blanco y validación JPEG | m | 1 |
| 3 | #122: manifiesto interno `data/derived/comparacion/<ine>.json` y comando `imagenes-comparacion` | m | 1 y 2 |
| — | Publicar el manifiesto y dibujar la ficha con SVG: dentro de #103 | — | 3 y la publicación de candidatos |

**#106 reutiliza esta pieza sin duplicarla**: la serie del dossier son estas mismas ventanas y
franjas para los tramos del dossier, con el mismo caso de uso y el mismo comando. El dossier
(#107) lee los bytes de la caché por la URL del manifiesto y comprueba su sha256; no crea otro
cliente ni otra política.

### Umbrales de producto a revisar con el fundador

Razonados, no calibrados; cambiarlos sube `COMPARISON_POLICY.version` y no toca la arquitectura:

- las cinco franjas y sus vuelos (y que la reciente sea 2023);
- 0,5 m por píxel, margen de 50 m, lado de 224 a 512 m;
- 4 ventanas por tramo: un tramo de más de ~1,6 km se queda sin imágenes;
- 400 ventanas por municipio;
- que el visitante cargue las imágenes desde el IGN en vez de desde el sitio.

### Alternativas descartadas

- **Llamar a `OrthophotoPort` con la línea convertida en un rectángulo**: el adapter fija 512×512
  y el margen; una ventana no cuadrada sale deformada y la resolución queda implícita.
- **Añadir el método a `OrthophotoPort`**: obligaría a los dobles del informe por parcela a
  implementarlo sin usarlo.
- **Una sola ventana por tramo, la que lo envuelve entero**: un tramo de 2 km quedaría a 2 m por
  píxel y el camino dejaría de verse.
- **Rejilla global de ventanas fijas**: reutilizaría caché entre tramos, pero partiría un tramo
  corto en cuatro esquinas.
- **Mosaico de máxima actualidad para la imagen reciente**: su año no se conoce sin
  `GetFeatureInfo` por ventana.
- **Pillow para quemar el trazado**: dependencia nueva, recodificación con pérdida y una imagen
  que ya no es la del IGN.
- **Ficheros de imagen en el sitio**: ver §5.

## Consecuencias

- Sin dependencias nuevas, sin proveedor nuevo, sin coste recurrente y sin LLM.
- `HistoricalVintage` crece con `SIGPAC` y `OLISTAT`; `PnoaAdapter` los acepta también.
- La señal `visibilidad_ortofoto` (ADR 0039, H4) puede reutilizar `OrthophotoWindow`, el port y
  la caché; necesitará, ella sí, decodificar JPEG.
- El visor depende del IGN para las imágenes de comparación igual que para el mapa base.
- Riesgos residuales: (a) una ventana en el borde de un vuelo puede salir medio blanca y pasa la
  detección; se muestra con su año, nunca se rellena; (b) si el IGN reprocesa una capa, el visor
  mostraría bytes distintos de los comprobados; el dossier usa los de la caché, con sha256;
  (c) el umbral de blanco es una heurística medida en el ámbito; una imagen real casi uniforme
  podría quedar por debajo (la real más baja medida está 3 veces por encima).
- `REGISTRY.md` documenta las atribuciones del SCNE de cada vuelo; `NOTICE` las recogerá cuando
  se publique la primera imagen (#103).
