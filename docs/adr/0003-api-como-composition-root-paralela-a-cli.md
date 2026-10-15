# ADR 0003 — `api/` es composition root al mismo nivel que `cli/`

- Estado: aceptada
- Fecha: 2026-10-15

## Contexto

`CLAUDE.md` define `cli/` como "el ÚNICO lugar donde se instancian adapters concretos y se inyectan". La historia 0004 introduce el primer código real en `api/` (FastAPI): el endpoint de informe HTML instancia `CatastroAdapter` directamente y lo inyecta en `GenerateParcelReportUseCase`, exactamente el mismo patrón que se esperaría de `cli/`. `vision.md` ya listaba `api/` como módulo FastAPI en la estructura del repo, pero `CLAUDE.md` no lo mencionaba como composition root — ambigüedad real que `api/main.py` resolvió en código antes de que hubiera una decisión escrita.

## Decisión

`api/` es una segunda composition root, al mismo nivel que `cli/`, no una capa por debajo de ella ni un caso de uso de `application/`. En el contrato de `import-linter` (`pyproject.toml`), `parcel_intel.cli` y `parcel_intel.api` se declaran como capas independientes del mismo rango (`"parcel_intel.cli | parcel_intel.api"`): ninguna puede importar a la otra, ambas pueden importar `adapters/`, `application/`, `ports/` y `domain/`.

Justificación: `cli/` y `api/` son dos puntos de entrada distintos al mismo motor (uno para ejecución por terminal, otro para servir sobre HTTP), no una jerarquía entre ellos. Cada uno instancia sus propios adapters según su propio contexto de ejecución (p. ej. `api/main.py` crea un `CatastroAdapter` por petición HTTP con el municipio que llega en la URL; un futuro `cli/` probablemente lo haga una vez por invocación con el municipio como argumento).

## Alternativas consideradas

- **`api/` como caso de uso de `application/`**: rechazada. `application/` no debe depender de FastAPI ni de ningún framework HTTP; mezclar la definición de rutas con los casos de uso rompería la regla de `CLAUDE.md` de que application solo importa `ports` y `domain`.
- **`api/` por debajo de `cli/`** (p. ej. que `cli/` levante el servidor FastAPI): rechazada por ahora. No hay ningún caso de uso real todavía en que `cli/` necesite controlar el ciclo de vida de `api/`; añadir esa dependencia sin un caso de uso concreto sería diseñar para un requisito hipotético.

## Consecuencias

- Cuando exista `cli/` con código real (ninguna historia lo ha necesitado todavía), debe seguir el mismo patrón: instanciar adapters concretos e inyectarlos, sin importar `api/`.
- Si en el futuro `cli/` y `api/` necesitan compartir lógica de construcción de adapters (p. ej. una fábrica de `CatastroAdapter` a partir de un nombre de municipio), esa fábrica no puede vivir en ninguno de los dos sin romper la independencia — se revisita entonces, posiblemente como una función de ayuda en `adapters/` mismo o un pequeño módulo de configuración compartido.
