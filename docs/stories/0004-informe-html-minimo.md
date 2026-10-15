# 0004 — Informe HTML mínimo de una parcela

## Historia

Como fundador que necesita ver el motor funcionando de punta a punta antes de seguir invirtiendo en piezas no visibles (PostGIS, Sentinel-2, boletines), quiero un endpoint que, dada una referencia catastral de Colmenar de Oreja o Villaconejos, devuelva una página HTML con la parcela, sus edificios y su geometría dibujada, para confirmar con datos reales que el cliente de Catastro de la historia 0002 sirve para algo visible.

## Contexto

Esta historia **se escribe después de implementarse**, no antes — rompe el orden del flujo obligatorio de `CLAUDE.md` (business-analyst → architect → implementación → code-reviewer) por una petición explícita del fundador en mitad de la historia 0003 ("sigamos hasta tener algo visible en el front"): se decidió pausar la historia 0003 (esquema PostGIS, que queda escrita en `docs/stories/0003-esquema-postgis.md` pero sin implementar) y saltar directamente a la tarea 8 de `docs/vision.md` ("informe mínimo en HTML"), adelantándola sobre las tareas 3-7.

El propio `code-reviewer` señaló como hallazgo bloqueante que esta implementación se hizo sin historia previa y sin tests — este documento y los tests añadidos después son la corrección de ese hallazgo, no el proceso ideal. La lección queda registrada en `docs/lessons/LESSONS.md` para el próximo ciclo: saltar el orden está bien si el fundador lo pide explícitamente, pero la historia y los tests no son opcionales ni siquiera cuando se escriben después.

No hay persistencia todavía (no existe la historia 0003 implementada): cada petición al endpoint llama en vivo al Catastro real a través de `CatastroAdapter`. No hay hallazgos ni reglas (historia 0007 no existe aún): el informe solo muestra lo que ya se puede obtener — geometría y atributos de parcela y edificios — no indicios ni normativa aplicable.

## Criterios de aceptación

- [x] Existe `domain/report.py` (`ParcelReport`, dataclass frozen con `parcel: Parcel` y `buildings: tuple[Building, ...]`), sin importar nada de `ports`/`adapters`/terceros.
- [x] Existe `application/generate_report.py` (`GenerateParcelReportUseCase`) que recibe `ParcelGeometryPort` y `BuildingGeometryPort` por inyección y compone un `ParcelReport`. No importa ningún adapter concreto.
- [x] Existe `adapters/reports/html.py` que renderiza un `ParcelReport` como página HTML autocontenida (sin plantillas de terceros), incluyendo un SVG con la geometría de la parcela y de cada edificio escalada y con el eje Y invertido (UTM → SVG). Soporta geometrías multi-anillo (parcelas o edificios con varios cuerpos) dibujando todos los anillos, no solo el primero.
- [x] Si la parcela no tiene ningún anillo de geometría, el renderizador lanza `EmptyGeometryError` con la referencia catastral en el mensaje, en vez de fallar con un `ValueError` sin contexto.
- [x] Existe `api/main.py` (FastAPI) con `GET /reports/{municipio}/{referencia}`, que instancia `CatastroAdapter` para el municipio pedido (solo `colmenar-de-oreja` y `villaconejos`, los dos del MVP) y devuelve el HTML renderizado.
- [x] Municipio no soportado → 404 con mensaje explícito. Referencia mal formada → 400 (`InvalidCadastralReferenceError`). Parcela inexistente → 404 (`ParcelNotFoundError`).
- [x] `pyproject.toml`: `parcel_intel.cli` y `parcel_intel.api` quedan como capas independientes al mismo nivel en el contrato de `import-linter` (`"parcel_intel.cli | parcel_intel.api"`) — ninguna puede importar a la otra, ambas son composition root. Ver ADR 0003.
- [x] Verificado manualmente contra la red real de Catastro (no solo con fixtures): parcela urbana con edificio multi-anillo (`REFCAT-RETIRADA`, Colmenar de Oreja), parcela rústica sin edificios (`REFCAT-RETIRADA`, Villaconejos) y referencia inexistente (404) — capturas de pantalla tomadas en esta sesión.
- [x] Tests sin red para los cuatro módulos nuevos: `application/generate_report.py` (fakes de los dos ports), `adapters/reports/html.py` (con edificios, sin edificios, multi-anillo, `construction_year=0` no tratado como ausente, geometría vacía → error), `api/main.py` (contrato HTTP con `TestClient` y un doble de `CatastroAdapter`, sin red).
- [x] `uv run pytest`, `uv run mypy`, `uv run ruff check .`, `uv run lint-imports` en verde.

## Fuera de alcance

- Esquema PostGIS y persistencia (historia 0003, pendiente de retomar).
- Hallazgos, confianza, norma aplicable (historia 0007, motor de reglas, no existe todavía) — este informe no es el informe final de `docs/vision.md`, solo una prueba de que el motor llega hasta el navegador.
- Sentinel-2, PNOA, LiDAR, BOE, BOCM (historias 0004-0006 de `docs/vision.md`, renumeradas tras este salto — ver nota abajo).
- Caché de peticiones a Catastro: cada carga del informe repite las llamadas HTTP (4 por petición, ver nota de rendimiento en la historia 0002).
- PDF, autenticación, o cualquier cosa más allá de HTML servido en caliente.

**Nota de numeración:** esta historia ocupa el número 0004 aunque la tarea 8 de `docs/vision.md` ("informe mínimo en HTML") estaba prevista para el final. Las tareas 4-7 de `docs/vision.md` (Sentinel-2, PNOA, BOE/BOCM, reglas) siguen pendientes y se numerarán 0005 en adelante según se escriban, no según el orden original del documento.

## Preguntas abiertas

- ¿Se retoma la historia 0003 (PostGIS) a continuación, o se sigue priorizando superficie visible (p. ej. añadir PNOA/ortofoto al informe) antes de volver a persistencia? Decisión del fundador.
- El informe hoy no tiene identidad visual ni está pensado para enseñarse a un comprador real — es una prueba técnica. Falta decidir si el "informe mínimo" de la tarea 8 original se da por cumplido con esto o si se espera algo más próximo al entregable final antes de cerrar esa tarea.
