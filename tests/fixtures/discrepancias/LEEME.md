# Fixtures de la historia #32 — SINTÉTICAS

Todo lo de este directorio está **inventado a mano** (lección 0012): ni un metro de
geometría ni una procedencia son reales. No se pueden usar como evidencia de ninguna
fuente. Cada capa lo dice en su `aviso` y en su `procedencia`.

`entrada/` imita `data/derived/` en el formato común de capa derivada (ADR 0030):

| Fichero | Contenido |
| --- | --- |
| `vias_pecuarias/28043.geojson` | `Polygon` (VP-1), `MultiPolygon` de dos partes (VP-2), `LineString` 3D (VP-3) |
| `camino_actual/28043.geojson` | R-1 sobre VP-1; R-3 paralela a VP-3 a 12,5 m; R-2 lejos de todo |
| `catastro_caminos/28043.geojson` | C-1 sobre VP-1; C-2 sin equivalente en ninguna otra capa |
| `vias_pecuarias/28045.geojson`, `camino_actual/28045.geojson` | municipio sin Catastro ni histórico |
| `camino_actual/28044.geojson` | JSON corrupto a propósito (lote con un fallo) |
| `camino_asfaltado/<ine>.geojson` | red asfaltada **vacía** junto a cada `camino_actual/` (historia #183): `discrepancias` exige los dos ficheros, y vacía no cambia ningún oráculo |

Resultado esperado de 28043 sin Catastro (fijado a mano antes de implementar, lección
0017): un `DESPLAZAMIENTO` de 12,5 m (R-3 frente a VP-3; tolerancia del par
`hypot(5, 10)` = 11,18 m) y un `AUSENTE_EN_FUENTE` (VP-2 sin equivalente en el IGN).
