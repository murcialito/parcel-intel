# Fixtures de la publicación de tramos a verificar (historia #170)

**Todo es sintético.** Ningún fichero viene de una consulta real. Reutiliza los
candidatos de `tests/fixtures/candidatos_revision/` (#168): la persona revisora
(`revisora-sintetica`) es inventada y el `trail_id` con forma de referencia catastral
(`99999A00109101`) usa el prefijo de municipio inexistente `99999`.

Se regeneran con:

```bash
uv run python -m tests.fixtures.candidatos_publicar.generar
```

Un test (`tests/adapters/published_layers/test_candidate_sink.py`) comprueba que los
ficheros versionados son los que genera el módulo.

| Fichero | Contenido |
|---|---|
| `candidatos/28043.geojson` | El fichero interno de candidatos de #168 (5 candidatos; uno con el tramo en dos piezas y otro con sujeto de Catastro). |
| `curated/28043/revision.json` | Aprobados con su huella vigente `aprobado`, `propuesto` (dos piezas) y `caducado`; `rechazado` rechazado; `sin_revision` sin entrada (propuesto); sin huérfana. 3 aprobados, 1 propuesto y 1 rechazado. |
| `medicion.json` | Informe de `medir-candidatos` con la forma real (`build_measurement_report`): 6 casos, 4 fuera del ámbito, ninguno evaluable; cocientes no calculables. |
| `medicion_calculable.json` | La misma forma con cobertura 1 de 2 y precisión 1 de 3. |

Oráculos de id público (Bloque 0, `public_candidate_id`): `aprobado` → `980ea673dbc2917f`,
`propuesto` → `fe4fe6c2754e854f`, `caducado` → `9cdd209df9143b26`.
