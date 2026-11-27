# Conjunto de validación de caminos cerrados

`casos.json` reúne casos de caminos cerrados ya documentados públicamente. Sirve para comprobar
que el sistema señala esos tramos por sí solo (ver `docs/vision.md`, «Validación»). Se construye
y se congela antes de ajustar umbrales.

El fichero es un objeto con una lista `casos`. Cada caso tiene estos campos:

| Campo | Obligatorio | Contenido |
|---|---|---|
| `id` | sí | Identificador único: minúsculas, dígitos y guiones (`^[a-z0-9][a-z0-9-]*$`). |
| `fuente_url` | sí | Enlace `https://` a la fuente. |
| `fuente_tipo` | sí | `prensa`, `asociación`, `resolución` u `otra`. |
| `fecha_consulta` | sí | Fecha en que se consultó la fuente, `AAAA-MM-DD`. |
| `municipio` | sí | Nombre del municipio. En `ambito: hito`, uno de los 7 del ámbito. |
| `ambito` | sí | `hito` (los 7 municipios) o `comunidad` (resto de la Comunidad de Madrid). |
| `tramo_descripcion` | sí | Descripción neutra del tramo, p. ej. «camino entre X e Y, paraje Z». |
| `cierre_fecha_aproximada` | sí | Fecha aproximada del cierre: `AAAA`, `AAAA-MM` o `AAAA-MM-DD`. |
| `tramo_linea` | no | Línea aproximada en EPSG:25830: lista de al menos 2 puntos `[x, y]`, abierta. Nunca un polígono de parcela. |
| `cierre_fecha_tipo` | no | `explicita` (la fuente da la fecha del cierre; valor por defecto si falta) o `documentado_desde` (fecha de la fuente más antigua que documenta el cierre; el cierre fue anterior o simultáneo). |
| `nota_fecha` | sí si `documentado_desde` | Texto neutro que dice qué documento da la fecha. |
| `sintetico` | no | `true` solo para casos de prueba del validador; no cuentan en los recuentos. |

## Reglas

- **Sin titularidad.** No se incluyen nombres de personas ni de sociedades, aunque la fuente los
  cite. El validador rechaza sociedades (`S.L.`, `S.A.`, `S.L.U.`, `SL`, `SA`) en los textos.
- **Sin referencias catastrales de fincas.** Campos como `propietario`, `titular`,
  `referencia_catastral` o `refcat` son error, y las referencias de 14 o 20 caracteres también
  en el texto.
- **Fecha aproximada, nunca inventada.** Si ninguna fuente da la fecha del corte, el caso lleva
  `cierre_fecha_tipo: documentado_desde` y la fecha de la fuente más antigua que lo documenta.
- **La fuente es el único respaldo.** El proyecto no afirma nada propio sobre el caso.
- **Trazabilidad.** Cada caso enlaza a su fuente y tiene fecha de consulta.

## Validación

El validador es `src/parcel_intel/adapters/validation_cases/casos_schema.py` (`validar_casos`). Para comprobar el fichero:

```bash
uv run pytest tests/validacion tests/acceptance/test_historia_51.py
```

**Catálogos aprobados de otras zonas (historia #279, hija de #271).** El catálogo de caminos públicos de Cáceres es, por lo leído, un conjunto de **trazados**, no de cortes: no se ha visto ningún dato de pérdida de traza ni obra de acceso, y no sería verdad conocida de cortes. Su contenido y licencia están pendientes de leer en local (ver `REGISTRY.md`, «Catálogo de caminos públicos de Cáceres y Extremadura»). Hasta entonces no forma parte de ningún conjunto congelado ni se publica.

Los mínimos del conjunto (6 casos, 2 de ellos en el ámbito; la meta de 10/5 se alcanzará con nuevas versiones congeladas) los comprueban las
historias #52, #53 y #54, no este formato.
