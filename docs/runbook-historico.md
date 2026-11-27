# Runbook: georreferenciar y aprobar los trazados históricos de Villarejo de Salvanés

Historia #60 (feature #21, épica #20; método en el [ADR 0043](adr/0043-georreferenciacion-y-digitalizacion-con-revision-humana.md)). Para la persona que prepara los datos reales. **Ningún agente** crea `curated/historico/280277-*` ni `281469-*` ni marca nada como `aprobado` (decisión del fundador del 2026-11-26 en #20): `curated/**` está protegido por CODEOWNERS y por la guardia de #50.

Nada de esto nombra propietarios: los trazados son caminos, con fecha y error, nunca titularidad. Son **indicios a verificar**, no dictámenes.

## 1. Las dos unidades a crear

Fuente: capa `Minutas` de `https://www.ign.es/wms/minutas-cartograficas` (CC BY 4.0, Orden FOM/2807/2015). Municipio: Villarejo de Salvanés, INE 28180. Una **unidad** es una ventana del render `GetMap` (EPSG:25830) de **≤ 5 × 5 km**, y no debe cruzar una **costura del mosaico** (el borde entre hojas o levantamientos distintos, donde cambia el documento de origen). Si el término no cabe en una ventana, se crean más (`-w2`, `-w3`...), cada una con sus propios puntos.

| `unit_id` | Documento | Fecha (`document_date`) | Precisión (`document_date_precision`) | Escala |
|---|---|---|---|---|
| `280277-w1` | 280277 | `1874-11-21` | `"day"`: fecha exacta del documento | 1:25.000 (`scale_denominator: 25000`) |
| `281469-w1` | 281469 | `1870-01-01` | `"year"`: fecha **genérica de la serie**, no de levantamiento | 1:50.000 (`scale_denominator: 50000`) |

- La escala se lee del propio documento (cabecera o ficha del CNIG) y decide los umbrales: **1:25.000 → LOO ≤ 15 m, residuo máximo ≤ 35 m; 1:50.000 → LOO ≤ 30 m, residuo máximo ≤ 70 m**. Si no se puede leer, no se adivina: se pregunta en la issue.
- `281469` lleva `1870-01-01` porque es la fecha de la serie. Con `"year"`, la ficha y la atribución solo hablan de «1870». Marcarla `"day"` sería presentar como exacta una fecha que no lo es.
- Cada unidad es independiente: su propio `puntos_control.csv`, su propio error y su propia aprobación.

Estructura por unidad, en `curated/historico/<unit_id>/`: `unidad.json`, `puntos_control.csv`, `trazados.geojson`. Para el formato, copiar la fixture sintética `tests/fixtures/caminos/planimetrias/historico/280075-w1/` y cambiar todo (`unit_id`, `document_id`, fecha, precisión, escala, `municipality_code: "28180"`, URL del render con el `BBOX` de la ventana, `sha256`). Poner `georeferenced_by` con tu usuario de GitHub, no `fixture-sintetica`.

La imagen de trabajo se descarga sola a `data/raw/ign_planimetrias/<unit_id>.png` (con su `.provenance.json`) la primera vez que se ejecuta `historico ajuste` sin `--sin-red`; después se reutiliza y no se vuelve a pedir. Copiar de ahí su `sha256` a `unidad.json`.

## 2. Leer los puntos de control sobre el PNOA

Cada punto es una pareja: píxel (`col`, `row`) en la imagen de trabajo y coordenada (`x_25830`, `y_25830`) en el terreno. **La coordenada se lee sobre el PNOA** (ortofoto actual, `coordinate_source` = «Lectura sobre el PNOA 2023» o la edición que uses), sobre elementos que existían en el siglo XIX y siguen allí: cruces de caminos antiguos, esquinas de iglesias o ermitas, plazas, puentes, cementerios. **Nunca se leen de Catastro**: su licencia INSPIRE no permite redistribuir su geometría y, además, ataría la georreferenciación a lindes de fincas. Tampoco se usan puntos de la propia planimetría.

- Mínimo **6 puntos retenidos repartidos en ≥ 3 cuadrantes** de la imagen. Mejor 8 o más: el ajuste (afín de 6 parámetros) mide su error por validación cruzada (LOO).
- Un punto dudoso no se borra: se deja con `retained = false` y un `discard_reason`.
- Sin nombres de propietarios en `description` ni en ningún campo.

## 3. Orden de trabajo

1. **`ajuste`**: `uv run python -m parcel_intel.cli.main historico ajuste <unit_id>`. Imprime candidatos, retenidos, cuadrantes, RMSE, residuo máximo, RMSE LOO, umbrales, veredicto y una línea por punto. Sale con 1 si no pasa. Repetir (quitar o corregir el punto con mayor residuo, añadir puntos en el cuadrante que falte) hasta `veredicto: aceptable`. Anotar el `puntos_sha256`.
2. **Digitalización en QGIS**: abrir la imagen de trabajo, trazar cada camino como `LineString` en píxeles y guardarlo en `trazados.geojson` con `"review": "propuesto"`, un `trail_id` (`T001`...) y su `kind`. **Nada se marca `aprobado` en este paso.**
3. **`evidencia`**: `uv run python -m parcel_intel.cli.main historico evidencia <unit_id>` escribe en `evidencia/` un PNG de dos paneles por trazado propuesto (la planimetría y el PNOA con el trazado transformado y su banda de ± 2 × LOO), con su `.procedencia.json`. Sirve para que quien revisa compare sin repetir el trabajo.
4. **PR con la aprobación**: en la PR, cada trazado que se acepta pasa a `"review": "aprobado"` con `reviewed_by`, `reviewed_at` y el `control_points_sha256` copiado del `puntos_sha256` del paso 1. La aprobación la hace **un miembro de CODEOWNERS**; el agente nunca la escribe. Si después cambia un solo punto, el hash caduca y los trazados vuelven a `propuesto`.
5. **`cargar`** (con PostGIS): `uv run python -m parcel_intel.cli.main historico cargar <unit_id>`. Solo se cargan los aprobados; salen `propuestos`, `rechazados` y cualquier `extrapolado`. Repetirlo con las mismas entradas da `insertados: 0` y `sin_cambios: n`.

## 4. Si una unidad no pasa los umbrales: rama B, «solo consulta»

Si, tras añadir y corregir puntos, el RMSE LOO o el residuo máximo siguen por encima del umbral de su escala (típico en 1:50.000 con pocos elementos reconocibles), esa unidad **no se carga**: sigue la **rama B / «solo consulta»**. La imagen y sus datos se citan como documento consultable (enlace al CNIG, fecha y precisión), pero no se publica ningún trazado georreferenciado ni se mide nada con ella. Se anota en la issue de la historia qué unidad quedó así, con el valor medido y el umbral, y la otra unidad sigue su camino: no se afectan.

## 5. Antes de enviar la PR

- `uv run python -m parcel_intel.cli.main historico ajuste <unit_id>` sale con 0 para cada unidad que se aprueba.
- Ningún fichero contiene referencias catastrales, nombres de propietarios ni titularidad.
- La atribución que saldrá es «Obra derivada de <fuente> <año> CC-BY 4.0 © Instituto Geográfico Nacional de España»; con `"year"` el año es el de la serie.
