# Fixtures del visor (historia #85)

Todo lo que hay en `datos/` es **sintético**, escrito a mano para los tests (lección 0012):
municipios con INE inventados `99001`–`99004`, coordenadas en la zona del ámbito y el mismo
formato que publica `publicar-capas` (#84). No son datos reales de ninguna fuente.

| Municipio | Vías pecuarias | Camino actual | Qué ejercita |
| --- | --- | --- | --- |
| 99001 A | `Polygon` + `MultiPolygon` de 2 partes | `LineString` + `MultiLineString` de 2 partes | CA2, CA3, CA4, CA14 |
| 99002 B | `features: []` (vacía) | 1 línea | CA13 |
| 99003 C | ruta del índice sin fichero (404) | 1 línea | CA9 |
| 99004 D | 1 polígono | JSON cortado a mitad (inválido) | CA9 |

Las propiedades trampa de CA6 (`titular`, `refcat`, `<b>`) no están aquí: el test las inyecta en
memoria, para que estas fixtures pasen la lista blanca de CA8.
