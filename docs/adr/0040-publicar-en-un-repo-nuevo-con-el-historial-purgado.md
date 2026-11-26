# ADR 0040 — Publicar en un repo nuevo con el historial purgado

- Estado: aceptada
- Fecha: 2026-11-26
- Nota: se escribió como 0035 y se renumeró a 0040, porque ese número ya lo ocupaba el ADR de licencias (`0035-licencias-codigo-y-datos-publicados-notice.md`).
- Cambia: el camino de `docs/runbook-publicacion.md` (historia #44), que reescribía el repo actual con push forzado

## Contexto

Antes de hacer público el repo hay que purgar del historial las respuestas crudas de Catastro. Sus dos licencias (INSPIRE de 2016 y descarga de 2011) prohíben difundir por Internet la información original sin transformar (ver `REGISTRY.md`).

En github.com, un push forzado no basta. Cada PR guarda `refs/pull/N/head`, de solo lectura, y esas referencias mantienen accesible el historial antiguo. Solo GitHub Support puede eliminarlas. El fundador no quiere depender de un tercero si no es estrictamente necesario.

## Decisión

1. Se crea un repo nuevo, `murcialito/parcel-intel`, con el historial purgado. El actual se renombra a `parcel-intel-archivo` y queda **privado** como archivo de las PRs.
2. Las issues se transfieren conservando su número. Los números que eran PRs se rellenan con una issue de reserva que se borra al momento, así siguen valiendo "Depende de #N", las líneas "Desbloqueo" y los nombres de rama.
3. El repo nuevo se crea privado, porque GitHub no transfiere issues de un repo privado a uno público. Se hace público al final, tras verificar la purga sobre un clon recién bajado.
4. Lo ejecuta `scripts/migrar_a_repo_nuevo.sh`, por fases que se comprueban una a una.

## Consecuencias

- El repo público nace sin `refs/pull` ni cachés del historial antiguo: no hace falta Support.
- Los enlaces a PRs antiguas (#1–#77) no funcionan en el repo nuevo: esas PRs viven en `parcel-intel-archivo`.
- Los secrets no se pueden copiar: el fundador los vuelve a guardar y da acceso a la App de Claude al repo nuevo.
- Los clones locales antiguos se re-apuntan y se limpian. No se puede empujar desde ellos historial viejo: un ruleset impide el push forzado a `main`.
