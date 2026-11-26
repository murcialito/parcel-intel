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
| `sintetico` | no | `true` solo para casos de prueba del validador; no cuentan en los recuentos. |

## Reglas

- **Sin titularidad.** No se incluyen nombres de personas ni de sociedades, aunque la fuente los
  cite. El validador rechaza sociedades (`S.L.`, `S.A.`, `S.L.U.`, `SL`, `SA`) en los textos.
- **Sin referencias catastrales de fincas.** Campos como `propietario`, `titular`,
  `referencia_catastral` o `refcat` son error, y las referencias de 14 o 20 caracteres también
  en el texto.
- **La fuente es el único respaldo.** El proyecto no afirma nada propio sobre el caso.
- **Trazabilidad.** Cada caso enlaza a su fuente y tiene fecha de consulta.

## Validación

El validador es `tests/validacion/casos_schema.py` (`validar_casos`). Para comprobar el fichero:

```bash
uv run pytest tests/validacion tests/acceptance/test_historia_51.py
```

Los mínimos del conjunto (10 casos verificados, 5 de ellos en el ámbito) los comprueban las
historias #52, #53 y #54, no este formato.
