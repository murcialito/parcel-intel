# ADR 0035 — Licencias del código y de los datos publicados, y fichero NOTICE

- Estado: aceptada (el fundador fijó el número 0035 el 2026-11-26)
- Fecha: 2026-11-25 (fecha de las decisiones del fundador)
- Historia: #43 (feature #40, épica #2)
- Corregida: la exclusión de Catastro del §3 la limita el [ADR 0041](0041-publicar-informacion-derivada-del-catastro.md). Se publica lo derivado que no reproduce la información original, con fuente, fecha y aviso; la geometría de las parcelas sigue sin publicarse.

## Contexto

El repositorio ya tiene licencia de código (Apache-2.0, historia #42). Falta registrar en un único sitio cómo se licencian los datos derivados que se publicarán en el mapa, qué atribución lleva cada capa y qué fuentes quedan fuera de la publicación. Sin eso, la atribución se decide capa a capa y puede olvidarse.

El fundador ya tomó tres decisiones, recogidas en la feature #40:

1. El código se licencia con Apache-2.0.
2. Los datos derivados publicados se licencian con CC BY 4.0, con su atribución y licencia en la procedencia de cada capa.
3. Las capas derivadas de Catastro no se publican hasta tener consulta jurídica, y OpenStreetMap (ODbL) queda fuera del mapa por ahora.

Las citas de licencia y los textos de atribución están verificados en `src/parcel_intel/sources/REGISTRY.md`, sección «Fuentes del primer hito de caminos públicos», apartado «Detalle de licencias».

## Decisión

Este ADR solo registra las tres decisiones anteriores. No propone ninguna nueva.

1. **Código**: Apache License 2.0, texto en `LICENSE`.
2. **Datos derivados publicados**: CC BY 4.0. Cada capa publicada muestra su atribución junto a los datos y guarda su licencia en la procedencia (`Provenance`, ver `CLAUDE.md`: fuente, URL, fecha de descarga y licencia). La marca de redistribución y la guarda de publicación en código son de la historia #33; este ADR no las implementa.
3. **Exclusiones**:
   - Catastro (INSPIRE): solo uso interno. Su licencia propia de 2016 prohíbe difundir la información original sin transformarla. Ninguna capa derivada suya se publica hasta tener consulta jurídica. *(Corregido por el ADR 0041: esto se limita a la geometría y los atributos de las parcelas. Los indicios y resultados derivados sí se publican.)*
   - OpenStreetMap (ODbL): no entra en el mapa por ahora.
4. **Fichero `NOTICE`** en la raíz: lista cada fuente publicable con su licencia, URL de licencia y texto de atribución tal como figura en `REGISTRY.md`. Lo que no consta allí se marca «pendiente de verificar».

## Numeración

La historia #43 pedía registrar esto en el ADR 0024, pero ese número ya lo ocupa `docs/adr/0024-merge-por-workflow-no-por-agente.md`, una decisión distinta. Tampoco se reutiliza el 0032: lo ocupa `docs/adr/0032-capa-de-vias-pecuarias-por-municipio-recorte-con-shapely-tras-un-port.md` (#36). Este ADR queda en el 0035, el siguiente libre, por decisión del fundador. El test de CA5 busca el fichero por su sufijo, no por el número.

## Consecuencias

- La atribución de cada capa se revisa contra `NOTICE` y `REGISTRY.md`. `NOTICE` es el texto que se muestra al público.
- Un test de coherencia (`tests/acceptance/test_historia_43.py`, CA6) falla si una fuente marcada «Publicar» en `REGISTRY.md` no aparece en `NOTICE`, o si `NOTICE` nombra Catastro como publicable. Así `NOTICE` no puede quedarse atrás del registro sin que el CI lo note.
- Las atribuciones de PNOA (formato de obra derivada con producto y fecha), de unidades administrativas y de MTN25 quedan «pendiente de verificar». Hasta que se verifiquen, no se publican con ese texto.
- Esta decisión no resuelve si una capa derivada de Catastro cuenta como «transformación». Eso sigue abierto en `docs/vision.md` y requiere consulta jurídica.
