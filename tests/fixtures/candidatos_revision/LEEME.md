# Fixtures de la revisión de candidatos a corte (historia #168)

**Todo es sintético.** Ningún fichero viene de una consulta real: ni candidatos, ni
revisiones, ni manifiesto. La persona revisora (`revisora-sintetica`) es inventada, y el
`trail_id` con forma de referencia catastral (`99999A00109101`) usa el prefijo de
municipio inexistente `99999` (lecciones de #37 y #96).

Se regeneran con:

```bash
uv run python -m tests.fixtures.candidatos_revision.generar
```

Un test (`tests/adapters/curated_candidates/test_fixture.py`) comprueba que los ficheros
versionados son los que genera el módulo.

| Fichero | Contenido |
|---|---|
| `candidatos/28043.geojson` | Fichero interno de candidatos de #128, escrito con `GeoJsonCutCandidateWriter`: 5 candidatos; uno con el tramo en dos piezas y otro con sujeto de Catastro. |
| `curated/28043/revision.json` | Aprobado vigente, rechazado, propuesto explícito, aprobado caducado (huella de otra `support_fraction`) y una huérfana (tramo desplazado 1 m). |
| `comparacion/28043.json` | Manifiesto de #122 reducido: `con_imagenes`, `sin_imagenes`, `tramo_demasiado_largo`; el caducado no está (`no_en_manifiesto`). |
