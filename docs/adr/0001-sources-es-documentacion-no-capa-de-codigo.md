# ADR 0001 — `sources/` es documentación de contrato, no una sexta capa de código

- Estado: aceptada
- Fecha: 2026-10-15

## Contexto

`docs/vision.md` propone un árbol de repositorio con `src/parcel_intel/sources/` ("un módulo por fuente: catastro, sentinel, pnoa, lidar, boe, bocm, layers") junto a `detection/`, `bulletins/`, `rules/`, `reports/`, `api/`. `CLAUDE.md`, en cambio, exige una frontera hexagonal estricta de cinco capas (`domain/`, `ports/`, `application/`, `adapters/`, `cli/`), donde los SDKs, HTTP y parsing de cada proveedor externo (Catastro, PNOA, BOE, BOCM, IDEM...) viven exclusivamente en `adapters/<proveedor>/`.

El esqueleto ya creado en el repo (`src/parcel_intel/{sources,detection,bulletins,rules,reports,api}/`) sigue literalmente el árbol de `vision.md` y todavía no contiene `domain/`, `ports/`, `application/` ni `adapters/`. La historia 0001 fija su único entregable en `src/parcel_intel/sources/REGISTRY.md`, y la historia 0002 (cliente de Catastro) es la primera que escribirá código real. Si no se resuelve ahora, 0002 puede arrancar escribiendo un cliente HTTP con pydantic directamente en `sources/catastro.py`, colapsando el hexágono desde el primer commit de código y dejando a `import-linter` sin un contrato que lo impida, porque `sources` no es una capa reconocida.

## Decisión

1. `src/parcel_intel/sources/` se mantiene únicamente como ubicación de `REGISTRY.md` (documentación de contrato de endpoints). No es una capa de código: no contiene `__init__.py`, no se importa desde ningún módulo Python, y el contrato de `import-linter` no la declara como capa válida para imports cruzados.
2. Todo cliente concreto de un proveedor externo (Catastro, PNOA, LiDAR, BOE, BOCM, IDEM/planeamiento, Sentinel-2) se implementa en `src/parcel_intel/adapters/<proveedor>/`, conforme a `CLAUDE.md`. Cada adapter implementa un port definido en `src/parcel_intel/ports/` según la *capacidad* que ofrece (p. ej. `ParcelGeometryPort`, `PlanningDataPort`, `OrthophotoPort`, `BulletinFeedPort`), no según el proveedor concreto, para que cambiar de proveedor sin tocar casos de uso sea el camino por defecto.
3. Los módulos de `vision.md` que sí son lógica de dominio o de orquestación propia del proyecto (`detection/`, `bulletins/`, `rules/`, `reports/`, `api/`) deben, a su vez, repartirse entre `domain/`, `application/`, `adapters/` y `cli`/`api` según corresponda a cada pieza concreta — no se aceptan como capas nuevas al margen del hexágono. Esto se detallará con un ADR específico cuando la historia 0003 (esquema PostGIS) o 0007 (evaluador de reglas) aterricen código real ahí, si hace falta.

## Alternativas consideradas

- **A. Seguir `vision.md` literalmente** y poner el código de cada cliente en `sources/<proveedor>.py`: rechazada. Rompe la regla "única capa con SDKs/HTTP/pydantic es `adapters/`" desde el primer cliente, y `import-linter` no puede proteger un directorio que no reconoce como capa.
- **B. `sources/` documentación + `adapters/<proveedor>/` código** (elegida): mantiene el path que la historia 0001 ya fijó (`src/parcel_intel/sources/REGISTRY.md`, citado también en `vision.md`), evitando reabrir ese criterio de aceptación, y resuelve la ambigüedad antes de que 0002 escriba código.
- **C. Mover `REGISTRY.md` a `docs/sources/REGISTRY.md`**, fuera de `src/`: descartada por ahora porque la historia 0001 y `vision.md` fijan explícitamente la ruta dentro de `src/parcel_intel/sources/`; reabrirla no aporta valor frente a la opción B, que logra el mismo aislamiento (sin imports) sin tocar un criterio ya cerrado.

## Consecuencias

- La historia 0002 (cliente de Catastro) debe crear `src/parcel_intel/ports/` (si no existe) con el/los port(s) de geometría, y `src/parcel_intel/adapters/catastro/` para el cliente concreto — no `sources/catastro.py`.
- `sources/` queda congelado como carpeta de un solo archivo (`REGISTRY.md`); si en el futuro se necesita más documentación de contrato por fuente, se añade ahí como markdown, nunca como paquete Python.
- No introduce un proveedor third-party nuevo ni dependencia externa, por lo que no aplica coste de salida de proveedor en este ADR; el coste de salida de cada proveedor de datos (Catastro, PNOA, BOE, BOCM, IDEM) se evaluará en el ADR de cada adapter cuando se implemente, conforme a la regla de `CLAUDE.md` de ADR obligatorio por proveedor nuevo.
- Riesgo residual: `detection/`, `bulletins/`, `rules/`, `reports/`, `api/` siguen sin mapear explícitamente a las cinco capas hexagonales. Se revisita con un ADR dedicado antes de que la primera historia de código aterrice en cada uno de ellos.
