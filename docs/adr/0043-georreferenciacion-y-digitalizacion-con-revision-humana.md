# ADR 0043 — Georreferenciación afín por unidad sobre el render del WMS y digitalización en píxeles con revisión humana

- Estado: aceptada
- Fecha: 2026-11-26
- Historias: #18 (este ADR), #17 (datos de partida), #19 (entidad y repositorio), #20 y #21 (carga), #50 (protección de `curated/**`)

## Contexto

Las planimetrías del IGN (1870-1880, 7 municipios del ámbito) y la 1.ª edición del MTN50 hoja 0606 (1881)
son mapas manuscritos sin vectorizar (REGISTRY.md). Son la única fuente de trazados de caminos anterior
al PNOA de 1956. Para usarlas como indicio hay que (1) llevarlas a EPSG:25830 con un error medido,
(2) dibujar sus caminos y (3) que una persona apruebe cada trazado antes de que se use o se publique.
El proyecto no admite coste recurrente, ni datos de titularidad, ni nada propuesto por una herramienta
sin aprobación humana.

#17 verificó que el original escaneado está en el Centro de Descargas del CNIG (JPG + ECW, ED50 UTM 30
extendido), pero la descarga exige reCAPTCHA v3: solo la puede hacer una persona, y el fichero PLANI
280075 no aparece en el listado público. Los WMS de minutas y de primera edición del MTN sirven las dos
imágenes sin captcha, pero ya reproyectadas y en mosaico, con desajustes de decenas de metros entre hojas.

## Datos de partida

Fuente: `tests/fixtures/caminos/planimetrias/verificacion.json` (#17, 2026-11-25) y sus `*.provenance.json`.
U = umbral de RMSE LOO de "Umbrales de producto".

| | Planimetría 280075 (Colmenar de Oreja, 1875-08-06) | MTN50 0606 "Chinchón" (1881) |
| --- | --- | --- |
| Imagen de trabajo | Render `GetMap` del WMS `minutas-cartograficas`, capa `Minutas`, EPSG:25830 | Render `GetMap` del WMS `primera-edicion-mtn`, capa `MTN50`, EPSG:25830 |
| Formato | image/png | image/png |
| Píxeles | 2000 × 2000 (ventana 464200–469200 E, 4437450–4442450 N) | 2000 × 2000 (misma ventana) |
| sha256 | `4b356414497cae86e425a062354e174ff2ccedcd21dcaddc9a2677763fe2ae21` | `0c96eaa15797dcc3617838d3288e432f45a0ecbff60c5fe940ec0ff4bebe7c68` |
| m/píxel del render | 2,5 | 2,5 |
| Resolución nativa estimada | 2,5 m/px (rango 2 a 3; `asumido`, por la rodilla de s(k)) | 4 m/px (rango 3 a 5; `asumido`) |
| Resolución efectiva (la peor de las dos) | 2,5 m/px (3 en el peor caso) | 4 m/px (5 en el peor caso) |
| Escala del documento | 1:25.000 (ficha del CNIG de la serie en Colmenar) | 1:50.000 |
| U y U/3 | 15 m y 5 m/px | 30 m y 10 m/px |
| ¿Resolución ≤ U/3? | Sí, también en el peor caso (3 ≤ 5) | Sí, también en el peor caso (5 ≤ 10) |
| Puntos candidatos identificables | 6: cruce radial norte, iglesia de Santa María, Plaza Mayor, ermita de San Juan, cementerio, ermita del Cristo | 6: los mismos |
| De ellos con coordenada | 3, leídas a ojo sobre PNOA (±25 a 30 m), todos en el casco a < 600 m entre sí | 3, igual; desajuste local frente a PNOA de 15 a 60 m a ojo |
| Original escaneado | CNIG, JPG + ECW; el PLANI 280075 no aparece en el listado público; píxeles desconocidos | Ficha del CNIG no abierta en #17 (`bloqueado`) |
| **Viabilidad** | **Viable con este método** sobre el render (≥ 6 candidatos y resolución ≤ U/3) | **Viable con este método** sobre el render (≥ 6 candidatos y resolución ≤ U/3) |

El reparto (≥ 6 puntos retenidos en ≥ 3 cuadrantes) es una condición de la carga de cada unidad, no de
la viabilidad del documento. Con los 3 puntos con coordenada de #17, la carga de cualquiera de las dos
unidades se **rechazaría** (menos de 6 retenidos, un solo cuadrante). #20 necesita que una persona ponga
al menos 6 puntos repartidos por la ventana, con coordenada leída sobre PNOA a la escala de 1:1.000 o mayor.

## Decisión

### Imagen de trabajo

1. Se georreferencia una **unidad**: un rectángulo del render del WMS, descargado una vez por `GetMap`
   (EPSG:25830, PNG, 2,5 m/px, hasta 5 × 5 km) y cacheado inmutable con su URL exacta y su sha256. Cada
   unidad tiene `unit_id` = `<documento>-w<n>` (p. ej. `280075-w1`).
2. **No se confía en la georreferenciación del servicio.** Puntos de control y trazados se expresan en
   píxeles de la imagen cacheada, y la transformación píxel → EPSG:25830 se ajusta contra PNOA como si la
   imagen no tuviera coordenadas. Así el error se mide igual que con un escaneo crudo.
3. Una unidad no debe cruzar una costura del mosaico (cambio de hoja, hueco blanco). Si la cruza, no pasará
   los umbrales: se parte en unidades más pequeñas.
4. **Rama B**: si una unidad no pasa los umbrales ni partiéndola, una persona descarga del CNIG el JPG
   original de esa hoja (nunca de forma automática: reCAPTCHA) y lo registra como unidad
   `<documento>-h<n>` con `kind = original_cnig`. Se ignora el ECW y su georreferenciación ED50. El método
   es el mismo.
5. **Rama alternativa** (documento no viable o unidad que no pasa ni con la rama B): queda como
   "solo consulta", con su enlace al IGN, y no aporta trazados.

### Transformación

1. **Afín de 6 parámetros por unidad**, ajustada por mínimos cuadrados con código del proyecto en `domain/`
   (stdlib): x = a + b·col + c·row ; y = d + e·col + f·row.
2. Alternativas descartadas:
   - Helmert de 4 parámetros: no absorbe la contracción anisótropa del papel ni del escaneo.
   - Polinómica de 2.º orden: con 6 a 10 puntos se sobreajusta y extrapola mal fuera de ellos.
   - *Thin plate spline*: el residuo en los puntos es nulo por construcción, de modo que oculta el error.
   - Usar tal cual la georreferenciación del WMS o del ECW: no deja medir el error, y #17 vio desajustes
     de 15 a 60 m.
3. En una unidad de ≤ 5 km (o una hoja de ≤ ~30 km), la diferencia entre las proyecciones de la época y
   UTM queda por debajo del error de dibujo y la absorbe la afín.
4. **Puntos de control:**
   - Mínimo 6 retenidos por unidad, en ≥ 3 de los 4 cuadrantes de la imagen.
   - Su envolvente convexa en píxeles debe contener todos los vértices de los trazados cargados. Un vértice
     fuera de ella rechaza ese trazado ("extrapolación: añadir puntos de control").
   - Orden de preferencia: (1) hitos estables visibles hoy (iglesias, ermitas, puentes, mojones de término
     o kilométricos, vértices del IGN); (2) cruces de caminos presentes en el documento, en PNOA 1956 y en
     PNOA 2023; (3) cruces presentes solo en PNOA 1956.
   - La coordenada se lee sobre **PNOA** (CC BY 4.0) en EPSG:25830 a escala 1:1.000 o mayor, o se toma de
     un vértice o mojón del IGN. **Nunca de Catastro**: su licencia no permite publicar los puntos, y los
     puntos se versionan y se publican con el trazado.
   - Descartar un punto exige motivo escrito. Como máximo se descarta el 25 % de los candidatos. Los
     descartados se conservan con su residuo.

### Error

1. Métricas sobre los puntos retenidos: RMSE de ajuste, residuo máximo y RMSE con validación cruzada
   dejando uno fuera (LOO: cada punto se predice con la afín ajustada sin él).
2. El **error publicado** de la unidad, y de cada trazado suyo, es el **RMSE LOO**, porque el de ajuste
   es optimista.
3. Umbrales por tipo de documento: los de "Umbrales de producto", en milímetros de papel × escala.
4. Si la unidad supera cualquiera de ellos, o no cumple el reparto, **la unidad no se carga**: no aporta
   ningún trazado y se informa del motivo con los valores medidos y el umbral. Se puede partir o pasar
   a la rama B.

### Registro

Por unidad se guarda:
- `unit_id`, número de documento IGN, tipo (`planimetria`/`mtn50`), municipio INE, fecha y su precisión
  (`day`/`year`) y escala;
- la imagen de trabajo: tipo, URL exacta, fecha de descarga, licencia, sha256, píxeles;
- todos los puntos de control, con estado, motivo de descarte y residuo, y el sha256 del fichero de puntos;
- los parámetros a–f y las métricas (RMSE, residuo máximo, LOO);
- quién puso los puntos (usuario de GitHub) y cuándo.

Dónde:
- la imagen, inmutable, en `data/raw/ign_planimetrias/<unit_id>.*`, con `<unit_id>.provenance.json`;
- la entrada humana, versionada, en `curated/historico/<unit_id>/` (`unidad.json`, `puntos_control.csv`,
  `trazados.geojson`, `evidencia/`);
- el registro calculado, en PostGIS (`historic_georeference`, #20), y los trazados en `historic_trail`
  (#19), con identificador `<unit_id>-<trail_id>`.

Git es la fuente de verdad. La base se puede reconstruir desde `curated/` y `data/raw/`.

### Digitalización y revisión

1. Estados: `propuesto` → `aprobado` | `rechazado`, en el GeoJSON versionado. En código son
   `proposed/approved/rejected`.
2. Una **persona** dibuja los caminos en coordenadas de píxel de la imagen de trabajo (QGIS, sin
   georreferenciar), en estado `propuesto`. En esta feature no hay vectorización automática.
   **Ningún agente digitaliza ni marca `aprobado`.**
3. Evidencia de cada trazado propuesto: un PNG versionado en la PR con dos paneles.
   - El recorte de la imagen de trabajo con el trazado dibujado encima.
   - El recorte de PNOA 2023 con el trazado transformado y su banda de incertidumbre.
4. Aprueba un miembro de CODEOWNERS de `curated/**` (al principio, el fundador). La garantía es la de
   #50: CODEOWNERS, más la guardia de `fusionar.yml`, que exige la aprobación del fundador sobre el
   último commit, más la protección de rama.
   - La aprobación consiste en revisar la PR que pone `review: aprobado` con `reviewed_by` (su usuario
     de GitHub) y `reviewed_at` (ISO 8601 con zona).
   - Rechazar exige `review_note`.
5. **Solo los `aprobado` se transforman, se guardan como `approved` y se publican** (`list_approved_*`).
   Los propuestos y rechazados se quedan en git como historia de la revisión.
6. Si cambian los puntos de control de una unidad, sus aprobaciones dejan de valer: en la misma PR los
   trazados vuelven a `propuesto` y se revisan con la evidencia nueva.

### Almacenamiento e incertidumbre

1. `LineString` en EPSG:25830, guardada **sin simplificar** (tolerancia 0). La digitalización manual ya es
   dispersa, y simplificar añadiría error sin medirlo.
2. En la salida publicada (fuera de este ADR) se simplifica con Douglas-Peucker a `min(2 m, LOO/5)` y las
   coordenadas se redondean al metro.
3. La incertidumbre es un atributo: `georeferencing_error_m` = RMSE LOO de la unidad. El visor dibuja el
   trazado histórico como una **banda de ± 2 × error**, no como una línea fina, y nunca muestra
   coordenadas con más precisión que el metro.

### Licencia y publicación

CC BY 4.0 (Orden FOM/2807/2015; licencia de uso del IGN). La atribución va junto a los datos.

- Por trazado (`derived_work_attribution` de #19 = `Obra derivada de {source} {año} {license}`), con
  `license = "CC-BY 4.0 © Instituto Geográfico Nacional de España"` y:
  - planimetría: `source = "Planimetría de <municipio>, IGN, documento <nº>"`, p. ej.
    `Obra derivada de Planimetría de Colmenar de Oreja, IGN, documento 280075 1875 CC-BY 4.0 © Instituto Geográfico Nacional de España`;
  - MTN50: `source = "Primera edición MTN50, IGN, hoja 0606"`, que da
    `Obra derivada de Primera edición MTN50, IGN, hoja 0606 1881 CC-BY 4.0 © Instituto Geográfico Nacional de España`.
- Por capa (pie del mapa o del fichero publicado), las de REGISTRY.md (#17):
  - `Obra derivada de Planimetrías 1870-1950 CC-BY 4.0 © Instituto Geográfico Nacional de España`;
  - `Obra derivada de Primera edición MTN50 1875-1968 CC-BY 4.0 © Instituto Geográfico Nacional de España`;
  - `Obra derivada de PNOA 2023 CC-BY 4.0 scne.es`, por las coordenadas de los puntos y la evidencia.
- **Ningún dato de titularidad**: Catastro no interviene; `label` solo transcribe nombres de caminos
  (nunca de fincas, casas ni personas); `reviewed_by` y `georeferenced_by` son usuarios de GitHub de
  colaboradores; la lista cerrada de propiedades del GeoJSON rechaza cualquier otra.

### Herramientas

- **QGIS** (GPL-2.0+, gratuito), en el ordenador de quien digitaliza y fuera de línea. Solo para leer
  píxeles de la imagen de trabajo, dibujar en píxeles y leer coordenadas sobre el WMS de PNOA.
- El ajuste, el error y la transformación los hace `domain/` con stdlib. Sin GDAL, coherente con el ADR 0007.
- La evidencia se genera con numpy (ya es dependencia) y `zlib` de stdlib. Pillow (HPND, gratuita), solo si
  una unidad de la rama B es JPG, y solo en `adapters/evidence/`.
- Sin proveedor nuevo: IGN y PNOA ya están registrados. Sin coste recurrente: descargas únicas cacheadas,
  proceso por lotes local, entradas en git y salidas estáticas.

### Umbrales de producto (aprobados por el fundador el 2026-11-26)

- Planimetría y MTN50: RMSE LOO ≤ 0,6 mm × escala y residuo máximo ≤ 1,4 mm × escala
  (1:25.000 → 15 m / 35 m; 1:50.000 → 30 m / 70 m). Si no se cumplen, la unidad no aporta trazados.
- Viabilidad del documento: resolución efectiva ≤ U/3 y ≥ 6 puntos candidatos identificables. Si no,
  "solo consulta".
- Reparto en la carga: ≥ 6 retenidos en ≥ 3 cuadrantes; máximo 25 % de descartes.
- Banda de incertidumbre publicada: ± 2 × RMSE LOO.

## Consecuencias para #19 y #20

- **#19 no cambia.** Este ADR fija los valores:
  - `document_id` = número IGN;
  - `identifier` = `<unit_id>-<trail_id>`;
  - `georeferencing_error_m` = RMSE LOO de la unidad;
  - `reviewer` = usuario de GitHub del aprobador;
  - `provenance.source` y `provenance.license` según "Licencia y publicación".

  La fixture sintética de #19 puede conservar su texto de licencia: es sintética. Los valores reales los
  pone #20.
- **#20**:
  - `domain/georeferencing.py` (`WorkingImage`, `ControlPoint`, `AffineTransform`, `GeoreferenceFit`,
    `GeoreferenceUnit`, `fit_affine`, `thresholds_m`, `check_acceptable`, `pixel_hull_contains`);
  - errores en `ports/errors.py`;
  - ports `WorkingImagePort`, `CuratedHistoricInputPort` y `GeoreferenceRepositoryPort`;
  - adapters `ign_historic/`, `curated_historic/`, `evidence/` y `postgis/` (tabla `historic_georeference`
    con UPSERT por `unit_id`);
  - caso de uso `load_historic_trails` (todo se valida antes de escribir);
  - CLI `historico ajuste|evidencia|cargar`;
  - formato cerrado de `unidad.json`, `puntos_control.csv`
    (`point_id,col,row,x_25830,y_25830,coordinate_source,description,retained,discard_reason`) y
    `trazados.geojson` en píxeles;
  - invalidación de aprobaciones al cambiar `control_points_sha256`. #20 diseña cómo retirar las filas
    antiguas.
- **#21**: repite el flujo por unidad, sin decisiones nuevas. Pasa a la rama B solo en las unidades que
  no pasen los umbrales.
- **#50**: es la garantía de la aprobación humana. No se aprueba ningún trazado real hasta que esté fusionada.
- **ADR 0025** no cambia: compara con su tolerancia fija por tipo de fuente (planimetría 40 m, MTN50 50 m).
  Para su recalibración (#16) se anota que un MTN50 aceptado puede tener 2 × LOO de hasta 60 m, más que su
  tolerancia, mientras que una planimetría aceptada queda en ≤ 30 m.

## Límites

- El error medido es el del ajuste en los puntos de control, no la exactitud del dibujo de la época lejos
  de ellos.
- Una afín no corrige la deformación local del papel (pliegues, humedad, empalmes de hojas) ni los
  desajustes internos del mosaico del WMS.
- Un camino del documento puede haber desaparecido, haberse desviado legalmente o estar mal dibujado.
  Su ausencia hoy no es prueba de corte.
- Que un camino aparezca en 1875 no prueba que sea público hoy. Todo trazado histórico es un **indicio
  fechado con su error**, nunca una prueba, un deslinde ni un dictamen.
