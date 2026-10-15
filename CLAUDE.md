# Parcel Intel

Informe de due diligence legal y física de inmuebles a partir de una referencia catastral: cruza lo que hay sobre el terreno (imagen, LiDAR, Catastro) con lo que la norma permite (planeamiento, boletines, afecciones). El principio rector es innegociable: el sistema señala **indicios a verificar**, con confianza y norma aplicable — nunca un dictamen jurídico.

MVP técnico en Colmenar de Oreja y Villaconejos (Comunidad de Madrid), sin canal B2B ni abogado validador. Ver [`docs/vision.md`](docs/vision.md) para la visión completa, las fases geográficas y las decisiones abiertas.

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
- Ningún LLM en la evaluación de reglas; solo en extracción de boletines (con revisión humana) y en redacción de explicaciones del informe.
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
```

## Contexto de negocio (resumen)

- Fase 0 (actual): MVP técnico en Colmenar de Oreja y Villaconejos — validar el motor de punta a punta con parcelas verificables en persona. Sin canal B2B, sin abogado validador, sin modelo de precio definido todavía.
- Fase 1: entrada comercial en Murcia/Alicante/Almería, suelo rústico, comprador extranjero con dolor alto y poca competencia.
- Fase 2: España entera, comunidad autónoma a comunidad autónoma.
- LLM del MVP: API de DeepSeek (`DEEPSEEK_API_KEY`), siempre detrás de una interfaz única en `ports/` para poder cambiar de proveedor o ir a modelo local sin tocar el resto del motor. Todo consumo se registra (coste y tokens).
- Riesgos abiertos sin resolver (ver `docs/vision.md`): responsabilidad legal/seguro antes de cobrar un informe real; cómo financiar la digitalización de boletines/planeamiento al escalar a más municipios.
