# Paso Común

Nombre público del proyecto desde el 2026-11-26 (antes «Parcel Intel»). Repo `murcialito/paso-comun`; sitio en `https://murcialito.github.io/paso-comun/`. El paquete Python sigue llamándose `parcel_intel` y no se renombra.

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

Desde el 2026-11-25 el backlog vive en GitHub Issues y los agentes corren en GitHub Actions ([`docs/proceso.md`](docs/proceso.md), ADR 0022). El fundador solo refina, y solo cuando un agente se lo pide.

1. **refinador** (`.claude/agents/refinador.md`) parte épicas y features, escribe la historia en la issue con criterios Dado/Cuando/Entonces y le pone talla (`talla:s`/`m`/`l`) → `estado:lista`, `estado:diseno` o `estado:necesita-fundador`.
2. **arquitecto** (`.claude/agents/arquitecto.md`) diseña toda historia `talla:l` o con ADR antes de desarrollo (ADR 0023).
3. **desarrollador** (`.claude/agents/desarrollador.md`) implementa con tests unitarios y un test de aceptación por criterio (`tests/acceptance/test_historia_<n>.py`), anota lecciones y ADR en la misma PR y la deja abierta: nunca fusiona.
4. **revisor** (`.claude/agents/revisor.md`) revisa la PR; su veredicto es el check obligatorio `revision`.
5. CI verde + `APROBADO` + sin `veto` sobre el último commit → `fusionar.yml` fusiona y despliega (ADR 0024).

El modelo de cada fase depende de la talla: barato solo para desarrollar `talla:s`, capaz para diseñar, desarrollar y revisar `talla:l`, intermedio en lo demás; la revisión nunca usa el barato (`.github/scripts/modelo.sh`, `docs/proceso.md`).

Las historias 0001–0021 de `docs/stories/` son archivo; las nuevas viven en su issue ("Historia #n").

**Todos los agentes y toda implementación deben leer `docs/lessons/LESSONS.md` antes de empezar.**

## Comandos

```bash
uv sync --extra dev     # instalar deps (incluye pytest, mypy, ruff, import-linter)
uv run pytest           # tests
uv run mypy             # tipado estricto
uv run ruff check .     # lint
uv run lint-imports     # verificar capas hexagonales
uv run pytest -m acceptance   # tests de aceptación (uno por criterio de cada historia)

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

# Capa de vías pecuarias por municipio del ámbito (historias #36, #83): recorte con los límites del IGN, en data/derived/vias_pecuarias/<ine>.geojson
uv run python -m parcel_intel.cli.main vias-pecuarias-municipios             # descarga y cachea en data/raw
uv run python -m parcel_intel.cli.main vias-pecuarias-municipios --sin-red   # solo desde la caché

# Capa de camino actual (red del IGN sin asfaltar) por municipio, en data/derived/camino_actual/<ine>.geojson (historia #27)
uv run python -m parcel_intel.cli.main camino-actual-municipios              # descarga y cachea en data/raw
uv run python -m parcel_intel.cli.main camino-actual-municipios --sin-red    # solo desde la caché

# Capa interna de caminos de Catastro de un municipio (historia #37): parcelas >= 9000 de clase VT, por teselas de 900 m.
# Capa de uso interno: NUNCA se publica (licencia INSPIRE). Sin fichero derivado: imprime el resumen. Caché inmutable en data/raw/catastro.
# --codigo es el código de Catastro (5 dígitos, como el INE en Colmenar); --bbox, el del término en EPSG:25830 con ejes E,N.
uv run python -m parcel_intel.cli.main catastro-caminos --provincia MADRID --municipio "COLMENAR DE OREJA" --codigo 28043 --bbox 449341,4431623,470702,4442906
uv run python -m parcel_intel.cli.main catastro-caminos ... --sin-red        # solo desde la caché

# Discrepancias entre capas de trazados por municipio (historia #32): lee data/derived/{vias_pecuarias,camino_actual,catastro_caminos}/<ine>.geojson
# y escribe data/derived/discrepancias/{interno,publicable}/<ine>.geojson (el interno NUNCA se publica). Sin red. Sale con 1 si algún municipio falla.
uv run python -m parcel_intel.cli.main discrepancias --municipio 28043 [--municipio ...]
uv run python -m parcel_intel.cli.main discrepancias --ambito                # los 7 municipios del primer hito

# Publicar vías pecuarias y camino actual en site/datos/<capa>/<ine>.geojson (historia #84, ADR 0036): EPSG:4326, cada fichero
# con su .procedencia.json, e índice site/datos/indice.json. Sin red. Todo o nada: sale con 1 y no escribe si una capa falta o no es publicable.
uv run python -m parcel_intel.cli.main publicar-capas --municipio 28043 [--municipio ...] [--capa vias_pecuarias|camino_actual]
uv run python -m parcel_intel.cli.main publicar-capas --ambito

# Publicar los indicios de discrepancia en site/datos/discrepancias/<ine>.geojson con la ficha de #16 (historia #94, ADR 0044): lee
# data/derived/discrepancias/publicable/<ine>.geojson (regenerarlo con `discrepancias` si es anterior a #94), EPSG:4326, cada fichero con su
# .procedencia.json, y el índice. Sin red. Todo o nada: sale con 1 y no escribe si un municipio falta o no es publicable; uno sin indicios publicables se informa como vacío.
uv run python -m parcel_intel.cli.main publicar-discrepancias --municipio 28043 [--municipio ...]
uv run python -m parcel_intel.cli.main publicar-discrepancias --ambito

# Candidatos a corte por municipio (historia #128, ADR 0039): lee data/derived/discrepancias/interno/<ine>.geojson (#94) y las parcelas de Catastro
# (#37, caché en data/raw/catastro) y escribe el fichero INTERNO data/derived/candidatos/interno/<ine>.geojson (EPSG:25830; deriva de Catastro: NUNCA se publica).
# Un municipio sin informe de discrepancias se registra como «sin capas» (no escribe, no es fallo); uno que falla no frena el lote y hace salir con 1.
# --sin-red: solo la caché; una tesela que falta deja la señal parcela_no_camino en sin_datos con su motivo. Sin --municipio ni --ambito sale con 1.
uv run python -m parcel_intel.cli.main candidatos-corte --municipio 28043 [--municipio ...] [--sin-red]
uv run python -m parcel_intel.cli.main candidatos-corte --ambito

# Imágenes de comparación de los tramos de un municipio (historia #122, ADR 0042): descarga y comprueba las ortofotos en la caché cruda
# data/raw y escribe el manifiesto INTERNO data/derived/comparacion/<ine>.json (URL canónica, sha256, atribución, píxeles del trazo). Entrada:
# GeoJSON de tramos en EPSG:25830 con properties.id de 16 hexadecimales. Nada va a site/. Todo o nada: sale con 1 y no escribe si una franja
# falla, si hay más de 400 ventanas (antes de pedir nada) o si el manifiesto pasa de 3.000.000 bytes. --sin-red: solo desde la caché.
uv run python -m parcel_intel.cli.main imagenes-comparacion --municipio 28043 --tramos ruta/tramos.geojson [--sin-red] [--cache data/raw]
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
