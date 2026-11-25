# Parcel Intel

Herramienta abierta y sin ánimo de lucro para la defensa de caminos públicos: reconstruye qué trazados deberían ser públicos (vías pecuarias oficiales, Catastro, cartografía histórica) y señala los tramos donde hoy parecen desaparecer o quedar dentro de una finca cerrada. Principios innegociables: el sistema señala **indicios a verificar**, con confianza y evidencia — nunca ilegalidades ni dictámenes; **nunca se nombra a propietarios**; las reglas propuestas por IA requieren aprobación humana antes de usarse.

Primer hito en Colmenar de Oreja y municipios vecinos (Comunidad de Madrid). Cambio de rumbo del 25 nov 2026: el informe de due diligence por referencia catastral (historias 0001–0020) queda como base reutilizable y posible fase posterior; pisos, fuera. Ver [`docs/vision.md`](docs/vision.md) y el ADR 0021.

## Arquitectura: hexagonal, innegociable

- `src/parcel_intel/domain/` — entidades y lógica pura (parcel, building, finding, rule...). **Cero imports de terceros, cero imports de otras capas.** Solo stdlib.
- `src/parcel_intel/ports/` — interfaces (`typing.Protocol`). Solo pueden importar `domain`.
- `src/parcel_intel/application/` — casos de uso (generar informe, evaluar reglas, resolver geolocalización de boletín). Reciben ports por inyección. Solo importan `ports` y `domain`. **Jamás un adapter.**
- `src/parcel_intel/adapters/` — implementaciones concretas (Catastro, Sentinel-2/STAC, PNOA, LiDAR, BOE, BOCM, IDEM/planeamiento, DeepSeek, PostGIS). Aquí viven los SDKs, HTTP y geoprocesamiento con librerías externas.
- `src/parcel_intel/cli/` y `src/parcel_intel/api/` — composition root: el ÚNICO lugar donde se instancian adapters concretos y se inyectan.

La regla se hace cumplir con `import-linter` (contrato en `pyproject.toml`). Si `lint-imports` falla, el cambio no se mergea. No se discute, se corrige.

Otras reglas:
- Dependencias nuevas de terceros: solo en adapters, y requieren ADR si introducen un proveedor nuevo (fuente de datos, LLM, etc.).
- Validación con pydantic solo en los bordes (adapters, API). El dominio usa dataclasses congeladas.
- mypy estricto en verde siempre.
- Ningún LLM en la evaluación de reglas; solo fuera de línea: autoría de reglas y extracción (con revisión humana) y redacción de textos que se publican ya generados. **Nada llama a un LLM en una consulta de usuario.**
- Coste de funcionamiento casi cero: solo datos públicos, análisis por lotes y publicación como ficheros estáticos siempre que se pueda. Cualquier componente con coste recurrente (backend, almacenamiento de fotos, API de pago) requiere ADR con estimación de coste.
- Ningún dato de titularidad entra en el sistema ni sale en ninguna vista. Una capa solo se publica en el mapa si su licencia permite redistribución.
- Todo dato lleva procedencia: fuente, URL, fecha de descarga y licencia.
- Operaciones métricas en EPSG:25830 (ETRS89 / UTM 30N); almacenamiento en ese CRS.
- Datos crudos cacheados e inmutables en `data/` (fuera de git); el procesamiento es reproducible desde la caché.
- Los tests no llaman a red: fixtures grabadas en `tests/fixtures/`; tests de integración marcados aparte.
- Cada hallazgo debe poder rastrearse hasta su evidencia y su regla.

## Flujo de trabajo por feature (obligatorio)

1. **business-analyst** escribe la historia → `docs/stories/NNNN-*.md`
2. **architect** valida el diseño; si hay decisión nueva, emite ADR → `docs/adr/`
3. Implementación contra los criterios de aceptación de la historia
4. **code-reviewer** revisa el diff antes de dar por cerrado
5. **lessons-learned** cierra el ciclo → `docs/lessons/LESSONS.md`

**Todos los agentes y toda implementación deben leer `docs/lessons/LESSONS.md` antes de empezar.**

## Comandos

```bash
uv sync                 # instalar deps
uv run pytest           # tests
uv run mypy             # tipado estricto
uv run ruff check .     # lint
uv run lint-imports     # verificar capas hexagonales

docker compose -f infra/docker-compose.yml up -d    # levantar PostGIS local
uv run python -m parcel_intel.adapters.postgis.migrate up      # aplicar migraciones
uv run python -m parcel_intel.adapters.postgis.migrate down    # revertir la última
uv run python -m parcel_intel.adapters.postgis.migrate status  # ver estado
uv run pytest -m integration    # tests que requieren PostGIS local levantado

# Autoría de reglas asistida por LLM (historia 0019) -- requiere DEEPSEEK_API_KEY en el entorno
uv run python -m parcel_intel.cli.main author --layer dph_cauce --text ruta/articulo.txt
uv run python -m parcel_intel.cli.main review list
uv run python -m parcel_intel.cli.main review approve <identifier>
uv run python -m parcel_intel.cli.main review reject <identifier>
```

## Contexto de negocio (resumen)

- Modelo: sin ánimo de lucro y código abierto. Sin clientes, precios ni cuentas de pago; solo se plantearían aportaciones si hubiera costes reales de funcionamiento.
- Usuarios: asociaciones de defensa de caminos, senderistas, ciclistas, ganaderos y ayuntamientos pequeños.
- Fase 1 (actual): caminos públicos. Primer hito en Colmenar de Oreja y vecinos: (a) mapa de trazados que deberían ser públicos, (b) candidatos a corte, (c) visor web estático. Después: avisos ciudadanos con foto y dossier para el ayuntamiento.
- Fase posterior posible: informe de rústico para compradores (reutiliza 0001–0020). Pisos: fuera del alcance.
- Validación: casos de caminos cerrados ya documentados públicamente; el sistema debe señalarlos por sí solo.
- **Antes de programar el hito**: verificar resolución, frecuencia y licencia de cada fuente de imágenes y cartografía, y si cada municipio tiene inventario de caminos publicado (resultado en `src/parcel_intel/sources/REGISTRY.md`).
- LLM: API de DeepSeek (`DEEPSEEK_API_KEY`), solo fuera de línea, siempre detrás de una interfaz única en `ports/`. Todo consumo se registra (coste y tokens).
- Riesgos abiertos (ver `docs/vision.md`): que un candidato publicado se lea como acusación o identifique indirectamente a un propietario; licencias de redistribución de las capas; método de detección de cortes.
