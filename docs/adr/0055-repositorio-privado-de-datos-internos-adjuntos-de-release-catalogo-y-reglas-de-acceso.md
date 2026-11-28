# ADR 0055 — Repositorio privado de datos internos: adjuntos de release, catálogo por fuente y reglas de acceso

- Estado: aceptada
- Fecha: 2026-11-28 (diseño del 2026-11-27)
- Historia: #294 (feature #293; hijas #295 y #296)
- Relacionados: ADR 0028 (caché cruda y redistribución), ADR 0035 y 0041 (licencias y Catastro), ADR 0040 (repo nuevo y `parcel-intel-archivo`), ADR 0022 y 0024 (agentes en Actions)

## Contexto

Hay datos que el proyecto necesita pero no puede publicar:
- Catastro INSPIRE (#37, licencia de 2016);
- Catastro histórico de rústica (#268, #287; Resolución de la DGC de 23-03-2011, que prohíbe difundir el original por internet);
- probablemente, los proyectos de clasificación del Fondo Documental de Vías Pecuarias (#280, #284), cuya solicitud obliga a no usarlos para fines distintos de los declarados.

Hoy esos datos viven solo en `data/` del portátil del fundador: sin copia, sin catálogo y sin poder usarse desde otra máquina. El Catastro histórico de Colmenar (unos 1,2-1,5 GB, descarga manual con Cl@ve) existe en un único disco. Además, la caché cruda de Catastro no se puede reproducir: una descarga posterior devuelve el Catastro de esa fecha, no el de la primera.

Cuando se diseñó esta historia, el repo público tenía dos credenciales que habrían llegado a un repo privado nuevo del fundador:
- `PROJECT_TOKEN`, un token clásico con `repo`. La documentación de GitHub ([Managing PATs](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)) dice que un token clásico «can access every repository that you can access».
- La App de Claude, si estaba instalada con «All repositories».

Las dos se corrigieron el 2026-11-27 (§5, condiciones previas). Los logs de Actions y las PR del repo público son públicos.

## Decisión

### 1. Dónde: repo privado `murcialito/paso-comun-datos`, con los ficheros grandes como adjuntos de release

Comparación (volumen estimado del año 1: 15 GB; precios de la documentación oficial, consultada el 2026-11-27):

| Opción | Coste estimado | Copia | Reutilizar desde otra máquina | Catálogo | Contras |
|---|---|---|---|---|---|
| **Repo privado + adjuntos de release** (elegida) | **0 €**. «Each file included in a release must be under 2 GiB»; «There is no limit on the total size of a release, nor bandwidth usage»; «Up to 1000 release assets may be associated with a single release» ([About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)) | Sí | Sí, con `gh` | En git, junto a los datos | Depende de una sola cuenta. Límite de 2 GiB por fichero |
| Git LFS en el mismo repo | 0 € hasta 10 GiB de almacenamiento y 10 GiB de ancho de banda al mes (GitHub Free, [Git LFS billing](https://docs.github.com/en/billing/concepts/product-billing/git-lfs)); por encima, de pago | Sí | Sí | En git | Ver «Por qué no Git LFS» abajo |
| Disco externo o NAS | Compra única de un disco de 1-2 TB (del orden de 60-100 €, sin verificar) y nada recurrente | Sí | No | No | Solo copia de seguridad: no sirve para trabajar desde otra máquina ni da catálogo |
| Cloudflare R2 | 10 GB-mes gratis y 0,015 USD/GB-mes después ([R2 pricing](https://developers.cloudflare.com/r2/pricing/)). Con 15 GB, ≈ 0,08 USD/mes (≈ 0,90 USD/año); con 50 GB, ≈ 0,60 USD/mes. Salida gratis | Sí | Sí | Aparte | Proveedor, cuenta y credencial S3 nuevos, más una dependencia nueva (cliente S3). Coste recurrente en cuanto se pasa de 10 GB. Por comprobar si exige medio de pago para el nivel gratuito |
| Backblaze B2 | Los primeros 10 GB gratis y desde 6,95 USD/TB-mes después ([B2 pricing](https://www.backblaze.com/cloud-storage/pricing)). Con 15 GB, ≈ 0,04 USD/mes. Salida gratis hasta 3× lo almacenado | Sí | Sí | Aparte | Los mismos que R2 |

Se elige el repo privado con adjuntos de release porque:
- cuesta cero y no tiene tope total ni de ancho de banda;
- usa la identidad que el fundador ya tiene (`gh auth`): ni proveedor, ni credencial, ni dependencia nuevos (GitHub ya aloja el código y el backlog);
- el catálogo vive en git junto a los datos;
- ofrece mecanismos de inmutabilidad: subir un adjunto con el nombre de otro da error 422 y hay que borrar el viejo antes ([REST: release assets](https://docs.github.com/en/rest/releases/assets)), y existen las releases inmutables ([Immutable releases](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/immutable-releases): «Git tags cannot be moved», «Release assets cannot be modified or deleted»). Esa página no dice si están en GitHub Free ni en repos personales privados: **a comprobar al crear el repo (#296)**.

**Por qué no Git LFS.** La feature #293 citaba una cuota de «1 GB»: está desfasada. La vigente en GitHub Free es de **10 GiB de almacenamiento y 10 GiB de ancho de banda al mes**. Aun así no sirve:
- los 15 GB estimados del año 1 ya pasan de los 10 GiB de almacenamiento;
- una sola restauración completa en otra máquina agota el ancho de banda del mes;
- borrar objetos LFS es difícil (hay que borrar el repo o pedirlo a soporte), y aquí no se quiere borrar nada sin control;
- por encima de la cuota es de pago, y los adjuntos de release no tienen tope.

### 2. Segunda copia (opcional)

El disco externo se acepta como **segunda copia**, a criterio del fundador. Cubre la pérdida de la cuenta de GitHub. No forma parte del flujo ni del catálogo.

### 3. Qué va en git, qué como adjunto y cómo es el catálogo

Estructura del repo privado:

```
README.md                         reglas de este ADR, resumidas
catalogo/<fuente>.json            un catálogo por fuente (esquema abajo)
procedencia/<fuente>/<id>.procedencia.json
derivados/<capa>/<ine>/<AAAA-MM-DD>-<sha8>.<ext>   instantáneas internas pequeñas (§4)
```

- **En git:**
  - catálogos, procedencias y `README.md`;
  - ficheros derivados internos de texto y pequeños (< 10 MB cada uno, muy por debajo del aviso de 50 MiB y del bloqueo de 100 MiB: «GitHub blocks files larger than 100 MiB», [About large files](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)). El repo debe quedar por debajo de 1 GB («ideally less than 1 GB, and less than 5 GB is strongly recommended»).
- **Como adjunto de release:**
  - todo original de una fuente (PDF, `.7z`, GML, imágenes), sea cual sea su tamaño;
  - todo lo binario o que pase de 10 MB.
  - Las cachés de muchos ficheros (la caché cruda de Catastro, con una entrada por petición) se empaquetan en un `.tar.gz` por fuente, municipio y fecha, hecho de forma reproducible: nombres ordenados, `--mtime` fijo, `gzip -n`.
  - Un fichero de 2 GiB o más se parte en trozos de menos de 2 GiB. El catálogo lleva el sha256 de cada trozo y el del fichero entero.
- **Releases:**
  - una por lote de subida, con etiqueta `<fuente>-<ine>-<AAAAMMDD>` (p. ej. `catastro-historico-28043-20261127`);
  - se crea en borrador, se adjunta todo y se publica;
  - si el plan lo permite, con releases inmutables activadas en el repo (#296 lo comprueba). Si no, la inmutabilidad la garantizan la convención y la comprobación de sha256.
- **Catálogo** (`catalogo/<fuente>.json`, UTF-8, claves en español, esquema versionado):

```json
{
  "esquema": 1,
  "fuente": "catastro_historico",
  "entradas": [
    {
      "id": "catastro-historico-28043-ac-20261127",
      "fuente": "catastro_historico",
      "producto": "Avance catastral",
      "municipio_ine": "28043",
      "url": "https://www.sedecatastro.gob.es/ (Sede Electrónica, descarga con Cl@ve)",
      "fecha_descarga": "2026-11-27",
      "licencia": "Resolución de la DGC de 23-03-2011, https://www.catastro.hacienda.gob.es/ayuda/legislacion/ovc/resoluciondgc20110323_tfs.pdf",
      "publicable": false,
      "restricciones_uso": ["solo uso interno", "no difundir el original ni recortes por internet", "citar «Dirección General del Catastro» y la fecha de acceso"],
      "sha256": "<64 hexadecimales>",
      "tamano_bytes": 123456789,
      "almacen": {"tipo": "release", "etiqueta": "catastro-historico-28043-20261127", "adjunto": "catastro-historico-28043-ac-20261127.7z"},
      "formato": "fichero",
      "destino": "raw/catastro_historico/28043/AC.7z",
      "procedencia": "procedencia/catastro_historico/catastro-historico-28043-ac-20261127.procedencia.json",
      "sustituido_por": null
    }
  ]
}
```

Reglas del catálogo:
- Campos obligatorios: `id`, `fuente`, `url`, `fecha_descarga`, `licencia`, `publicable`, `restricciones_uso` (lista no vacía), `sha256`, `tamano_bytes`, `almacen`, `formato`, `destino` y `procedencia`.
- Campos opcionales: `producto`, `municipio_ine`, `partes` (lista de `{adjunto, sha256, tamano_bytes}`) y `sustituido_por`.
- `id`: `^[a-z0-9][a-z0-9._-]{0,99}$`, único en todo el repo. El adjunto se llama como el `id` más la extensión.
- `publicable` es siempre `false`: lo publicable no necesita este repo. El campo existe para que cada entrada lo declare.
- `almacen.tipo` vale `release` o `git`; en `git` lleva `ruta`.
- `formato` vale `fichero` o `tar`. Un `tar` se desempaqueta en el directorio `destino` y rechaza cualquier miembro que salga de él (en #295, `tarfile` con `filter="data"`).
- `destino` es relativo a `data/`, empieza por `raw/` o `derived/`, y no lleva `..` ni es absoluto.
- Se prohíbe cualquier campo de titularidad: `titular`, `propietario`, `nif`, `dni`, `nombre_persona`, etc. No se escribe ninguna referencia catastral de finca en el catálogo, ni en etiquetas, ni en nombres de adjunto.
- **Solo se añade.** Una entrada no se edita ni se borra. Una versión nueva es un fichero nuevo, con `id` y procedencia propios. A la vieja solo se le rellena `sustituido_por`.

Lo que #295 debe respetar (sin firmas, que se fijan allí): el catálogo se valida en el dominio con dataclasses congeladas; el acceso al almacén va tras un port de una capacidad («leer catálogo» y «abrir un fichero por id»); el adapter usa el CLI `gh` del usuario; el composition root es solo `cli/` (nunca `api/` ni un workflow). El destino de la sincronización es `data/raw/<fuente>/...` (y `data/derived/...` para las instantáneas), inmutable como `CachedRawFetcher`. No se transforma nada: se guarda el original tal como se descargó, en su CRS.

### 4. Qué se copia (incluido `data/derived/*/interno/`)

- **Siempre:**
  - originales que no se pueden volver a descargar igual: Catastro histórico;
  - la caché cruda de Catastro INSPIRE (`data/raw/catastro/`) por municipio y fecha;
  - los proyectos del Fondo Documental cuando lleguen, con el fin declarado en la solicitud como restricción de uso.
- **De `data/derived/*/interno/` no se copia nada de forma rutinaria**: se regenera desde la caché cruda y el código (CLAUDE.md).
  - **Excepción: instantánea de lo que respalda una publicación.** Cada vez que se publica con `publicar-candidatos` o `publicar-discrepancias`, se copia a `derivados/` lo interno que alimentó esa publicación:
    - `candidatos/interno/<ine>.geojson`;
    - `discrepancias/interno/<ine>.geojson`;
    - `comparacion/<ine>.json`;
    - `validacion/medicion.json`.
  - La procedencia de la instantánea lleva el commit del repo público y la fecha. Así, cada tramo publicado se puede rastrear hasta su evidencia aunque el código cambie después y la regeneración dé otra huella.
- No se copian las fuentes públicas (IGN, IDEM, BOE): no hacen falta aquí.

### 5. Acceso y autenticación

- **Acceso:** solo el fundador, mientras no se aclare la licencia. Sin colaboradores, sin forks, sin deploy keys y sin secrets copiados del repo público.
- **Sincronización (#295):**
  - es un comando local del repo público que lanza el fundador desde su terminal;
  - usa el CLI `gh` del usuario mediante subprocess (`gh release download`, `gh api`), que se autentica con la sesión de `gh auth login` del fundador;
  - el comando no lee, guarda, imprime ni pasa por argumentos ningún token, y no usa `GH_TOKEN` del entorno salvo a través de `gh`;
  - si no hay acceso, sale con 0 y un mensaje genérico, sin nombrar repo, rutas ni ficheros;
  - se niega a correr si `CI` o `GITHUB_ACTIONS` están definidos;
  - ningún workflow lo invoca;
  - el repo público no guarda ningún secreto para este fin: no se toca ningún secreto del repo público.
- **Ningún agente del repo público tiene acceso al repo privado,** ni en Actions ni en local. Una sesión local de Claude Code en el portátil del fundador no ejecuta la sincronización ni `gh` contra `paso-comun-datos`.
- **Condiciones previas a crear el repo privado.** Las dos están **hechas, el 2026-11-27**:
  1. **`PROJECT_TOKEN` reemitido** como token clásico con **solo `public_repo` y `project`**, **sin `repo`**, válido 1 año (caduca hacia el 2027-11-27; el fundador tiene un recordatorio local para renovarlo). El token antiguo con `repo` está borrado. Según la documentación de [ámbitos](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps), `repo` da «full access to public and private repositories», `public_repo` «Limits access to public repositories» y `project` da «read/write access to user and organization projects». Con `public_repo` el token no llega a ningún repo privado. Los fine-grained no sirven: no admiten «Projects owned by a user account». Comprobado: «Sincronizar tablero» termina bien con el token nuevo ([run 46064791921](https://github.com/murcialito/paso-comun/actions/runs/46064791921)).
  2. **App de Claude** instalada con «Only select repositories», solo con `murcialito/paso-comun` y sin `paso-comun-datos`.
  - #296 las vuelve a comprobar en su guía antes de crear el repo.
- **Falta el ámbito `workflow` en `PROJECT_TOKEN`.** En la interfaz de GitHub, marcar `workflow` en un token clásico marca también `repo` completo, así que el token nuevo no lo lleva. Consecuencia probable: cuando `main` ha cambiado ficheros de `.github/workflows/`, el `update-branch` que hace `fusionar.yml` con `PROJECT_TOKEN` puede fallar al poner al día una PR. Hoy ese caso cae en «no se pudo poner al día» y la PR pasa a Actualizar rama, que la pone al día con un merge del agente: no se pierde nada, solo se tarda una vuelta más. Valoración: un token de GitHub App limitado a este repo (con permiso `workflows`) resolvería el caso sin llegar al privado, pero es una credencial y una App más que mantener para un caso raro (los agentes no tocan workflows; solo el fundador). **No compensa por ahora.** Se revisa si el caso deja de ser raro.
- **Procesado interno:** en local o en workflows del propio repo privado. Sus logs son privados. Cuesta 12 USD de cómputo al mes incluidos en Free (y 500 MB de artefactos, [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)), y sin la App de Claude instalada. Hoy no se prevé ninguno.

### 6. Titularidad

Tampoco entra en el repo privado ningún dato de titularidad:
- ni Hojas de Características, ni Relación de Propietarios, ni Fichas parcelarias, ni ningún documento con nombres, DNI o NIF de personas;
- de un proyecto del Fondo Documental que lleve relación de colindantes, solo se sube lo que no tenga nombres. Si no se puede separar, no se sube.

La guía de subida (#296) incluye una comprobación manual previa. El validador del catálogo (#295) rechaza los campos de titularidad.

### 7. No se reutiliza `parcel-intel-archivo`

Ese repo guarda el historial anterior a la purga (ADR 0040) y queda congelado. No se le añaden datos, releases ni colaboradores.

### 8. Decisión pendiente: colaboradores

Si entran colaboradores, el fundador decide entre dos opciones:
- **(a)** Cuentan como parte del proyecto y acceden al repo privado. Requiere aclarar con la DGC si pasarles el original sin transformar es difundirlo a terceros.
- **(b)** Cada uno descarga con su propia Cl@ve. Se comparte solo el catálogo (sin datos), y el sha256 comprueba que se trata del mismo producto.

Recomendación: **(b)** mientras no haya respuesta de la DGC. Hasta que el fundador decida, el acceso es solo suyo.

## Consecuencias

- La copia cuesta cero y usa la cuenta de GitHub que ya existe. El riesgo de perder la cuenta lo cubre el disco opcional.
- `CLAUDE.md` y `docs/proceso.md` recogen las reglas del §5 y del §6. `docs/proceso.md` deja de decir que `PROJECT_TOKEN` necesita `repo`.
- Quedan dos comentarios desfasados fuera del alcance de esta historia (solo documentación; los agentes no editan workflows): la cabecera de `.github/workflows/sincronizar-tablero.yml` (líneas 6-7, dice que el token necesita `repo` «para ver las issues del repo privado», de cuando el repo era privado) y la de `.github/scripts/revisiones_pendientes.sh` («PROJECT_TOKEN (repo)»). Los corrige el fundador, o una historia de tubería.
- #295 implementa la sincronización solo de bajada, con el catálogo de §3. #296 escribe la guía de creación y subida con las condiciones previas del §5.
- La inmutabilidad depende de la convención y del sha256, y además de las releases inmutables si el plan las ofrece.
- Si el volumen pasa de unos 100 GB o un fichero no se puede trocear con sentido, se revisa este ADR (R2 o B2 son la alternativa, con su coste).

## Canales consultados

Se leyeron (2026-11-27, en el diseño de #294) las páginas de docs.github.com enlazadas arriba, la de precios de R2 en developers.cloudflare.com y la de precios de B2 en backblaze.com. No se verificó: si las releases inmutables están en GitHub Free para repos personales privados (queda para #296), si R2 exige medio de pago en el nivel gratuito, ni el precio de un disco externo (estimación).
