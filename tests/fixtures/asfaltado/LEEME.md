# Fixtures de la historia #183 — SINTÉTICAS

Todo lo de `entrada/` está **inventado a mano** (lección 0012): ni un metro de geometría
ni una procedencia son reales. Cada capa lo dice en su `aviso` y en su `procedencia`. El
municipio `28997` no existe. Imita `data/derived/` en el formato común (ADR 0030), con
`superficie` en la colección y en cada feature (ADR 0050).

Las vías pecuarias son franjas de 10 m de ancho (lección de #94), de x = 450000 a
x = 451000, con el eje en la `y` indicada. Ids de tramo 9000000000xx (no reales).

| Vía | Eje (y) | Contraparte del IGN | Criterio | Resultado con la red asfaltada |
| --- | --- | --- | --- | --- |
| `VP-A` | 4435000 | `900000000001` **asfaltado** a 2 m, todo el eje | CA1 | ningún registro |
| `VP-B` | 4436000 | `900000000002` **sin asfaltar** a 2 m, todo el eje | CA2 | ningún registro (igual que antes) |
| `VP-C` | 4437000 | `900000000003` **asfaltado** a 2 m, solo de x = 450000 a 450600 | CA3 | `SOLAPE` con zona de x = 450610 a 451000 |
| `VP-D` | 4438000 | `900000000004` **asfaltado** paralelo a 20 m | CA10 | ningún registro: el asfaltado no es sujeto y `DESPLAZAMIENTO` vía → IGN no se conserva |
| `VP-E` | 4439000 | `900000000005` **sin asfaltar** paralelo a 20 m | CA10 | `DESPLAZAMIENTO` IGN → vía con sujeto `900000000005`, igual con o sin red asfaltada |

Con `camino_asfaltado/28997.geojson` vacío, `discrepancias` da `AUSENTE_EN_FUENTE` en
`VP-A`, `VP-C` y `VP-D` y el mismo `DESPLAZAMIENTO` de `VP-E`.

Oráculo de `VP-C` (Bloque 0, pasando la fixture por `discrepancias`): zona de
x = 450610 a x = 451000. Contraste con `shapely`: los puntos del eje a más de 11,18 m
(tolerancia vía–IGN) del tramo asfaltado empiezan en x = 450600 + √(11,18² − 2²) ≈
450611,0; la zona del criterio empieza en la muestra anterior (paso de 5 m), así que
se compara con `abs=5`.
