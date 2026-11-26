# Runbook: purgar el historial y pasar el repo a público

Historia #44 (feature #39, épica #2). Autorización del fundador (en #39): reescribir el historial con `git filter-repo` y hacer `push --force` a `main` **una sola vez**, con el repo privado y sin PRs abiertas. Alternativa descartada: repo nuevo.

**Por qué**: las respuestas crudas de Catastro que hay en el historial están bajo la licencia INSPIRE de 2016, que prohíbe difundirlas por Internet sin transformarlas (ver `src/parcel_intel/sources/REGISTRY.md`). Antes de publicar el repo no pueden quedar en ningún commit, tag ni caché.

**Rutas a purgar**: las de `scripts/rutas_purga.txt` (`tests/fixtures/catastro/` y `tests/fixtures/caminos/catastro_*`). Este documento no reproduce el contenido de esos ficheros.

Esta historia solo entrega las herramientas y este documento. **La ejecución la hace el fundador**, después de que se fusione #38 (fixtures sintéticas que sustituyen a las originales en el árbol de trabajo).


> **Camino elegido: repo nuevo ([ADR 0035](adr/0035-publicar-en-un-repo-nuevo-con-el-historial-purgado.md)).**
> No se hace push forzado sobre este repo, para no depender de GitHub Support con `refs/pull/*`. Se ejecuta `scripts/migrar_a_repo_nuevo.sh` por fases: `preparar`, `archivar`, `crear`, `numerar`, `restaurar`, `activar` (tras guardar los secrets) y `publicar`. La fase `preparar` purga **por contenido**. Las fixtures sintéticas (#45 y #46) comparten ruta con las respuestas reales, así que una purga por rutas también las borraría. Se quitan del historial todas las versiones que han estado en `tests/fixtures/catastro/` o `tests/fixtures/caminos/catastro_*`, salvo las de `main`. Antes, se comprueba que las de `main` no llevan referencias catastrales reales, y después se verifica de forma independiente (en el ensayo: el historial original da 41 rastros y el purgado, 0). `scripts/purgar_historial.sh` y `scripts/verificar_purga.sh` (por rutas) no se usan en este camino. Las secciones "Pasos" (5 a 7), "Purga en GitHub" y "Rollback" quedan como referencia del camino descartado.

## Requisitos de la herramienta

`git-filter-repo` (p. ej. `pip install git-filter-repo`). Es herramienta de operador: no está en `pyproject.toml`.

## Precondiciones

Comprobar todas antes de empezar; si una falla, parar.

1. Repo **privado**: `gh repo view murcialito/parcel-intel --json visibility` devuelve `"visibility":"PRIVATE"`.
2. **Sin PRs abiertas**: `gh pr list --state open --repo murcialito/parcel-intel` no devuelve nada. Una PR abierta apunta a commits antiguos y se rompería.
3. **#38 fusionada**: `gh issue view 38 --repo murcialito/parcel-intel --json state` devuelve `CLOSED` y `main` ya no referencia las rutas purgadas en su árbol (`git ls-tree -r --name-only main` sin coincidencias con `scripts/rutas_purga.txt`). Si no, el árbol actual seguiría conteniéndolas y la purga las borraría de `main` rompiendo tests.
4. **Copia de seguridad** completa y fuera del directorio de trabajo: `git clone --mirror git@github.com:murcialito/parcel-intel.git ../parcel-intel-backup.git`. Es lo que permite el rollback.
5. Ningún agente en marcha: sin workflows de Actions en ejecución (`gh run list --status in_progress`) ni jobs que vayan a empujar a `main`.
6. `git filter-repo --version` funciona.

## Pasos

Todos sobre una copia de trabajo desechable; el remoto no se toca hasta el paso 5.

1. **Clon desechable**, desde el mirror y sin enlaces duros: `git clone --no-local ../parcel-intel-backup.git ../parcel-intel-purga`.
2. **Purga**: `scripts/purgar_historial.sh ../parcel-intel-purga scripts/rutas_purga.txt --copia-desechable`. El script se niega si el directorio no es la raíz de un clon, si tiene cambios sin confirmar o si falta `--copia-desechable`. `git filter-repo` elimina el remoto `origin` del clon: no se puede empujar por error.
3. **Verificación**: `scripts/verificar_purga.sh ../parcel-intel-purga scripts/rutas_purga.txt`. Debe devolver 0. Comprueba commits de todas las refs, tags, blobs alcanzables y reflog/objetos sueltos tras `gc --prune=now`. Si devuelve ≠ 0 lista las rutas y commits con rastro: no seguir; corregir y repetir desde el paso 1.
4. **VISTO BUENO EXPLÍCITO DEL FUNDADOR.** Con la verificación en verde, el fundador revisa `git log --oneline --all` y el árbol de `main` en el clon y escribe en #39 que autoriza el `push --force`. Sin ese comentario, no se continúa.
5. **Push forzado de ramas y tags**: en el clon, `git remote add origin git@github.com:murcialito/parcel-intel.git`, después `git push --force --all origin` y `git push --force --tags origin`. Si la rama `main` está protegida, desactivar temporalmente la protección contra force-push y restaurarla al terminar.
6. **Reapuntar**: comprobar que la rama por defecto sigue siendo `main` y que no han quedado ramas antiguas en el remoto (`git ls-remote origin`).
7. **Verificación por re-clonado**: `git clone git@github.com:murcialito/parcel-intel.git ../parcel-intel-verificacion` y ejecutar `scripts/verificar_purga.sh ../parcel-intel-verificacion scripts/rutas_purga.txt`. Debe devolver 0. Ejecutar además `uv sync --extra dev` y la batería de comandos de `CLAUDE.md` para comprobar que el repo purgado sigue en verde.

## Purga en GitHub

`git filter-repo` y el push forzado no limpian todo lo que GitHub retiene:

- **GitHub Support**: abrir una solicitud en <https://support.github.com/contact> pidiendo (a) la purga de los commits huérfanos que sigan accesibles por hash, (b) la limpieza de `refs/pull/*` (las PRs ya cerradas, como #30, conservan sus commits en `refs/pull/<n>/head`, que no se pueden reescribir con push) y (c) el vaciado de las cachés de vistas de GitHub. Indicar las rutas purgadas y el motivo (licencia de datos). Hasta que respondan, **el repo no se hace público**.
- **Forks**: comprobar que no hay (`gh api repos/murcialito/parcel-intel/forks --jq length` devuelve 0). Un fork privado conserva el historial antiguo. Si existe, eliminarlo o pedir a su dueño que lo elimine.
- **Artefactos y cachés de Actions**: borrar los artefactos (`gh api repos/murcialito/parcel-intel/actions/artifacts`) y las cachés de Actions (`gh cache delete --all`) que puedan contener el árbol antiguo; revisar también los logs de ejecuciones antiguas si imprimieran contenido de las rutas.
- **Otros sitios**: GitHub Pages (#41) no debe haberse desplegado aún desde un árbol con esas rutas; releases y wikis, si existen, se revisan igual.

## Comunicación

- Los clones antiguos **se descartan** (se borran y se vuelve a clonar). **No se hace merge** ni `pull` desde ellos hacia el repo purgado: reintroduciría los commits antiguos.
- Avisar en #39 cuando termine el push forzado, para que cualquier agente o persona con un clon lo elimine antes de volver a trabajar.
- Las ramas `claude/...` que existan se crean de nuevo desde el `main` purgado.

## Rollback

Si algo sale mal después del push forzado (verificación fallida, repo roto), y mientras el repo siga privado:

1. Desde el mirror de la precondición 4: `git -C ../parcel-intel-backup.git push --mirror git@github.com:murcialito/parcel-intel.git`. Restaura todas las refs al estado anterior.
2. Comprobar con `git ls-remote` que las refs coinciden con las del mirror.
3. Anotar el fallo en #39 antes de reintentar. El mirror se conserva hasta que el repo sea público y estable; después se borra, porque contiene el rastro que se ha purgado.

## Paso final: hacer público

Es una **acción manual del fundador**, no de un agente ni de un workflow: Settings → General → Danger Zone → Change visibility → Public. Solo cuando:

- la verificación del paso 7 está en verde,
- GitHub Support ha confirmado la purga de `refs/pull/*` y cachés,
- no hay forks,
- y el fundador ha borrado o custodiado el mirror de la precondición 4 fuera de cualquier lugar público.

Después, borrar el clon de purga y el mirror si ya no hacen falta.

## Clon local (tras migrar)

El clon local tiene el historial antiguo. No se vuelve a clonar, para no perder `data/` (caché cruda, fuera de git): se re-apunta y se limpia.

```bash
git fetch origin
git checkout main
git reset --hard origin/main
git branch | grep -v '^\* main$' | xargs -r git branch -D
git reflog expire --expire=now --all && git gc --prune=now
```

La URL del remoto no cambia (`git@github.com:murcialito/parcel-intel.git`), pero ahora apunta al repo nuevo. El ruleset de `main` impide que un push desde un clon antiguo reintroduzca el historial viejo.
