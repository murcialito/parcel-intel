# Guía: repo privado de datos internos (`murcialito/paso-comun-datos`)

Historia #296, hija de #293. Sigue el [ADR 0055](../adr/0055-repositorio-privado-de-datos-internos-adjuntos-de-release-catalogo-y-reglas-de-acceso.md) sin decisión nueva: ante cualquier duda manda el ADR. Esta guía la sigue **el fundador, a mano, desde su terminal**. Crear el repo y subir los datos son acciones del fundador.

Qué cubre: crear el repo privado, subir la copia de seguridad del Catastro histórico de rústica de Colmenar de Oreja (28043) como adjuntos de una release, y dejar en git el catálogo y la procedencia. Lo que no cubre: la sincronización de bajada (#295), el comprobador local de sha256 y de titularidad (no está en alcance; sería otra historia) y la copia de la caché cruda de Catastro INSPIRE y de `derivados/` (ADR 0055 §4; otra guía cuando toque).

## Reglas que no se negocian

- **Ningún agente ni workflow del repo público ejecuta esta guía ni usa `gh` contra el repo privado.** Ni en Actions ni en local. Una sesión de Claude Code en el portátil no sube ni descarga nada del repo privado.
- **Ningún dato de titularidad entra en el repo privado.** No se sube ni se descarga ninguna Hoja de Características, Relación de Propietarios ni Ficha parcelaria (ADR 0055 §6).
- **Lo subido es inmutable.** Una versión nueva es un fichero nuevo con `id` y procedencia propios; a la vieja solo se le rellena `sustituido_por`.
- Las rutas son relativas a la raíz del repo público (`data/...`). No hay rutas del portátil en esta guía.
- Los comandos son para Linux o macOS. En macOS, `sha256sum` se sustituye por `shasum -a 256`.

Requisitos locales: `gh` autenticado con tu cuenta (`gh auth status`), `jq`, `7z` (paquete `7zip` o `p7zip`) y `git`.

## 0. Condiciones previas (ADR 0055 §5)

Estas dos condiciones se cumplieron el 2026-11-27. Compruébalas antes de crear nada: si alguna no se cumple, para aquí.

**0.1 `PROJECT_TOKEN` es un token clásico con solo `public_repo` y `project`.**

- En tu cuenta, abre *Settings → Developer settings → Personal access tokens → Tokens (classic)* y localiza el token que usa el secret `PROJECT_TOKEN` (el valor no se ve y no hace falta).
- Comprueba que sus ámbitos son exactamente `public_repo` y `project`, **sin `repo`**.
- Si lleva `repo`, regenera el token con solo esos dos ámbitos y actualiza el secret con `gh secret set PROJECT_TOKEN --repo murcialito/paso-comun`. Te pedirá el valor: no lo escribas en un comando, en un fichero ni en un chat.
- Comprobación de funcionamiento: el workflow *Sincronizar tablero* debe terminar en verde.

**0.2 La App de Claude solo tiene acceso a `murcialito/paso-comun`.**

- En tu cuenta, abre *Settings → Applications → Installed GitHub Apps → Claude → Configure*.
- En *Repository access* debe figurar **«Only select repositories»**, con `murcialito/paso-comun` y sin `paso-comun-datos`.
- Si figura «All repositories», cámbialo antes de crear el repo privado. Con «All repositories» la App llegaría también al repo nuevo.

## 1. Crear el repo privado

Crea el repo **privado**, sin colaboradores, forks, deploy keys ni secrets:

```bash
gh repo create murcialito/paso-comun-datos --private --add-readme --description "Datos internos de Paso Común (ADR 0055). Privado: ningún agente accede."
```

`--add-readme` deja un primer commit en el repo. Una release apunta a una rama con commits, así que el repo no debe quedar vacío cuando llegue el paso 5. El README se sustituye en el paso 6.

Comprueba lo que el ADR exige:

```bash
gh repo view murcialito/paso-comun-datos --json visibility,isPrivate
```

Debe salir `"visibility": "PRIVATE"` e `"isPrivate": true`.

```bash
gh api repos/murcialito/paso-comun-datos/collaborators --jq '.[].login'
```

Debe salir solo `murcialito` (el propietario).

```bash
gh api repos/murcialito/paso-comun-datos/keys --jq 'length'
gh api repos/murcialito/paso-comun-datos/actions/secrets --jq '.total_count'
gh api repos/murcialito/paso-comun-datos/forks --jq 'length'
```

Deben salir `0`, `0` y `0`: sin deploy keys, sin secrets y sin forks.

## 2. Releases inmutables

Antes de publicar ninguna release, comprueba si tu plan permite **releases inmutables** para un repo personal privado. La documentación de GitHub no lo aclara (ADR 0055 §1).

- Abre `murcialito/paso-comun-datos` → *Settings* y busca la opción de releases inmutables (*Immutable releases*).
- Si aparece, actívala. Anota en el README del repo privado (paso 6) la fecha y «releases inmutables: activadas».
- Si no aparece, anota en el README «releases inmutables: no disponibles en este plan (fecha)». La inmutabilidad la garantizan entonces la convención de este documento y la comprobación de sha256 del paso 7.

## 3. Comprobación previa a la subida

Antes de subir nada, revisa cada `.7z` **sin extraerlo**. Son cinco, uno por producto de rústica de la Sede: `AC.7z`, `TP.7z`, `1R.7z`, `2R.7z` y `3R.7z`, en `data/raw/catastro_historico/28043/`. Si tus ficheros tienen otro nombre, usa el tuyo y ajusta el catálogo del paso 6.

**3.1 Listado.** Para cada fichero:

```bash
7z l data/raw/catastro_historico/28043/AC.7z
```

**3.2 Nombres prohibidos.** Ninguno de estos nombres o patrones puede aparecer. El comando debe **no dar salida**:

```bash
7z l data/raw/catastro_historico/28043/AC.7z | grep -i -E 'caracter|propietar|ficha|\.(xlsx?|csv|txt)$'
```

Lo que buscas es, en el nombre de cualquier entrada: «Hoja de Características», «Relación de Propietarios», «Ficha parcelaria», y cualquier `.xls`, `.xlsx`, `.csv` o `.txt` de relación de titulares. Si aparece alguno, **para**: ese fichero no se sube y se avisa en la issue #296.

**3.3 Solo cartografía en PDF.** Cada `.7z` debe traer solo PDF de cartografía. Este comando lista las entradas que no son PDF; la única línea esperable es la del propio `.7z` (y carpetas, si las hay):

```bash
7z l -slt data/raw/catastro_historico/28043/AC.7z | grep '^Path = ' | grep -v -i '\.pdf$'
```

Cualquier otra línea es un fichero que no es PDF: para y revísalo antes de subir.

**3.4 Procedencia.** Cada fichero necesita su `procedencia/catastro_historico/<id>.procedencia.json` en el repo privado (paso 6). Si los ficheros se bajaron a mano y no existe procedencia, créala antes con estos campos (el `sha256` se calcula en el paso 4):

```json
{
  "id": "catastro-historico-28043-ac-20261127",
  "fuente": "catastro_historico",
  "url": "https://www.sedecatastro.gob.es/ (Sede Electrónica, descarga con Cl@ve)",
  "fecha_descarga": "2026-11-27",
  "licencia": "Resolución de la DGC de 23-03-2011, https://www.catastro.hacienda.gob.es/ayuda/legislacion/ovc/resoluciondgc20110323_tfs.pdf",
  "restricciones_uso": [
    "solo uso interno",
    "no difundir el original ni recortes por internet",
    "citar «Dirección General del Catastro» y la fecha de acceso"
  ],
  "sha256": "a calcular en el paso 4",
  "tamano_bytes": "a calcular en el paso 4"
}
```

**3.5 Tamaño.** GitHub admite como máximo **2 GiB por adjunto** (2147483648 bytes). Cada `.7z` debe pesar menos:

```bash
wc -c < data/raw/catastro_historico/28043/AC.7z
```

Si alguno llegara a 2 GiB o más, se parte en trozos de menos de 2 GiB (por ejemplo, `split -b 1900M`). El catálogo lleva entonces la lista `partes` con el sha256 y el tamaño de cada trozo, y el del fichero entero. Con los cinco productos de Colmenar, que suman unos 1,2 GB, no debería hacer falta.

## 4. sha256, tamaños y procedencia

Calcula el sha256 y el tamaño de cada fichero:

```bash
sha256sum data/raw/catastro_historico/28043/AC.7z
wc -c < data/raw/catastro_historico/28043/AC.7z
```

Repite para `TP.7z`, `1R.7z`, `2R.7z` y `3R.7z`. Apunta los valores: van al catálogo (paso 6).

Compara el sha256 de cada fichero con el de su `.procedencia.json`. Deben coincidir. Si no coinciden, para: el fichero o la procedencia están mal, y no se sube nada hasta averiguar cuál.

Un sha256 de 64 caracteres hexadecimales es el formato correcto. Una salida como `a rellenar` o una cadena más corta es un error.

## 5. Release: borrador, adjuntos, publicar

Una release por lote, con etiqueta `<fuente>-<ine>-<AAAAMMDD>`. Para el lote de Colmenar: `catastro-historico-28043-20261127`.

Cada adjunto se llama como su `id` más la extensión, así que hay que copiar cada `.7z` con su nombre definitivo. Las copias van a un directorio **nuevo** fuera del repo público, nunca a `data/`:

```bash
mkdir ../subida-catastro-28043
cp data/raw/catastro_historico/28043/AC.7z ../subida-catastro-28043/catastro-historico-28043-ac-20261127.7z
cp data/raw/catastro_historico/28043/TP.7z ../subida-catastro-28043/catastro-historico-28043-tp-20261127.7z
cp data/raw/catastro_historico/28043/1R.7z ../subida-catastro-28043/catastro-historico-28043-1r-20261127.7z
cp data/raw/catastro_historico/28043/2R.7z ../subida-catastro-28043/catastro-historico-28043-2r-20261127.7z
cp data/raw/catastro_historico/28043/3R.7z ../subida-catastro-28043/catastro-historico-28043-3r-20261127.7z
```

Crea la release **en borrador**:

```bash
gh release create catastro-historico-28043-20261127 --repo murcialito/paso-comun-datos --draft --title "Catastro histórico de rústica, Colmenar de Oreja (28043), descarga del 2026-11-27" --notes "Lote inicial. Uso interno: ver catalogo/catastro_historico.json."
```

Adjunta los cinco ficheros:

```bash
gh release upload catastro-historico-28043-20261127 --repo murcialito/paso-comun-datos ../subida-catastro-28043/*.7z
```

Comprueba nombres y tamaños de los adjuntos antes de publicar. Cada tamaño debe coincidir con `tamano_bytes` del paso 4:

```bash
gh release view catastro-historico-28043-20261127 --repo murcialito/paso-comun-datos --json assets --jq '.assets[] | [.name, .size] | @tsv'
```

Solo cuando todo cuadra, publica la release:

```bash
gh release edit catastro-historico-28043-20261127 --repo murcialito/paso-comun-datos --draft=false
```

Si `gh release upload` da error por un nombre repetido, **no borres nada**. Un adjunto con ese nombre ya existe: el lote es otro, o hay que crear una versión nueva con `id` propio (ver «Reglas de inmutabilidad»).

## 6. Subir a git: catálogo, procedencia y README

Clona el repo privado en un directorio nuevo, fuera del repo público:

```bash
gh repo clone murcialito/paso-comun-datos ../paso-comun-datos
```

Dentro del clon, crea los tres elementos y reemplaza el README del paso 1:

- `README.md`: reglas del ADR 0055 resumidas (sin copiar el ADR entero): solo para el fundador; sin datos de titularidad; lo subido es inmutable y una versión nueva es un fichero nuevo; los adjuntos son de releases con etiqueta `<fuente>-<ine>-<AAAAMMDD>`; el estado de las releases inmutables (paso 2). Añade una línea de estado: «Copia: sin subir» hasta que el fundador confirme la subida, y entonces «copia hecha el <fecha>».
- `catalogo/catastro_historico.json`: el catálogo del ejemplo de la sección siguiente, con los sha256 y tamaños reales del paso 4 y sin ningún «a rellenar».
- `procedencia/catastro_historico/<id>.procedencia.json`: uno por fichero, como en el paso 3.4, con el sha256 y el tamaño reales.

Luego confirma y sube:

```bash
git add README.md catalogo procedencia
git commit -m "Catastro histórico de Colmenar (28043): catálogo y procedencia del lote 20261127"
git push
```

## 7. Verificación posterior

Para confirmar que lo subido es lo que dice el catálogo, descarga los adjuntos a un directorio **nuevo** y compáralos con los sha256 del catálogo. Hazlo desde la raíz del clon del repo privado:

```bash
mkdir ../verificacion-catastro-28043
gh release download catastro-historico-28043-20261127 --repo murcialito/paso-comun-datos --dir ../verificacion-catastro-28043
jq -r '.entradas[] | "\(.sha256)  \(.almacen.adjunto)"' catalogo/catastro_historico.json > ../esperado-28043.sha256
(cd ../verificacion-catastro-28043 && sha256sum -c ../esperado-28043.sha256)
```

La salida esperada es una línea `OK` por cada adjunto:

```
catastro-historico-28043-ac-20261127.7z: OK
catastro-historico-28043-tp-20261127.7z: OK
catastro-historico-28043-1r-20261127.7z: OK
catastro-historico-28043-2r-20261127.7z: OK
catastro-historico-28043-3r-20261127.7z: OK
```

Cualquier `FALLO` significa que el adjunto no es el que dice el catálogo. Para, no borres el adjunto y avisa en #296.

## Catálogo inicial (Colmenar de Oreja, 28043)

Ejemplo del esquema 1 del ADR 0055 §3, con una entrada por producto de rústica. Los campos `sha256` y `tamano_bytes` se rellenan con los valores reales del paso 4 antes de subir el catálogo; en esta versión de la guía dicen «a rellenar por el fundador». Ninguna referencia catastral de finca ni nombre de persona aparece en el catálogo.

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
      "sha256": "a rellenar por el fundador",
      "tamano_bytes": "a rellenar por el fundador",
      "almacen": {"tipo": "release", "etiqueta": "catastro-historico-28043-20261127", "adjunto": "catastro-historico-28043-ac-20261127.7z"},
      "formato": "fichero",
      "destino": "raw/catastro_historico/28043/AC.7z",
      "procedencia": "procedencia/catastro_historico/catastro-historico-28043-ac-20261127.procedencia.json",
      "sustituido_por": null
    },
    {
      "id": "catastro-historico-28043-tp-20261127",
      "fuente": "catastro_historico",
      "producto": "Topográfico Parcelario",
      "municipio_ine": "28043",
      "url": "https://www.sedecatastro.gob.es/ (Sede Electrónica, descarga con Cl@ve)",
      "fecha_descarga": "2026-11-27",
      "licencia": "Resolución de la DGC de 23-03-2011, https://www.catastro.hacienda.gob.es/ayuda/legislacion/ovc/resoluciondgc20110323_tfs.pdf",
      "publicable": false,
      "restricciones_uso": ["solo uso interno", "no difundir el original ni recortes por internet", "citar «Dirección General del Catastro» y la fecha de acceso"],
      "sha256": "a rellenar por el fundador",
      "tamano_bytes": "a rellenar por el fundador",
      "almacen": {"tipo": "release", "etiqueta": "catastro-historico-28043-20261127", "adjunto": "catastro-historico-28043-tp-20261127.7z"},
      "formato": "fichero",
      "destino": "raw/catastro_historico/28043/TP.7z",
      "procedencia": "procedencia/catastro_historico/catastro-historico-28043-tp-20261127.procedencia.json",
      "sustituido_por": null
    },
    {
      "id": "catastro-historico-28043-1r-20261127",
      "fuente": "catastro_historico",
      "producto": "1.ª renovación",
      "municipio_ine": "28043",
      "url": "https://www.sedecatastro.gob.es/ (Sede Electrónica, descarga con Cl@ve)",
      "fecha_descarga": "2026-11-27",
      "licencia": "Resolución de la DGC de 23-03-2011, https://www.catastro.hacienda.gob.es/ayuda/legislacion/ovc/resoluciondgc20110323_tfs.pdf",
      "publicable": false,
      "restricciones_uso": ["solo uso interno", "no difundir el original ni recortes por internet", "citar «Dirección General del Catastro» y la fecha de acceso"],
      "sha256": "a rellenar por el fundador",
      "tamano_bytes": "a rellenar por el fundador",
      "almacen": {"tipo": "release", "etiqueta": "catastro-historico-28043-20261127", "adjunto": "catastro-historico-28043-1r-20261127.7z"},
      "formato": "fichero",
      "destino": "raw/catastro_historico/28043/1R.7z",
      "procedencia": "procedencia/catastro_historico/catastro-historico-28043-1r-20261127.procedencia.json",
      "sustituido_por": null
    },
    {
      "id": "catastro-historico-28043-2r-20261127",
      "fuente": "catastro_historico",
      "producto": "2.ª renovación",
      "municipio_ine": "28043",
      "url": "https://www.sedecatastro.gob.es/ (Sede Electrónica, descarga con Cl@ve)",
      "fecha_descarga": "2026-11-27",
      "licencia": "Resolución de la DGC de 23-03-2011, https://www.catastro.hacienda.gob.es/ayuda/legislacion/ovc/resoluciondgc20110323_tfs.pdf",
      "publicable": false,
      "restricciones_uso": ["solo uso interno", "no difundir el original ni recortes por internet", "citar «Dirección General del Catastro» y la fecha de acceso"],
      "sha256": "a rellenar por el fundador",
      "tamano_bytes": "a rellenar por el fundador",
      "almacen": {"tipo": "release", "etiqueta": "catastro-historico-28043-20261127", "adjunto": "catastro-historico-28043-2r-20261127.7z"},
      "formato": "fichero",
      "destino": "raw/catastro_historico/28043/2R.7z",
      "procedencia": "procedencia/catastro_historico/catastro-historico-28043-2r-20261127.procedencia.json",
      "sustituido_por": null
    },
    {
      "id": "catastro-historico-28043-3r-20261127",
      "fuente": "catastro_historico",
      "producto": "3.ª renovación",
      "municipio_ine": "28043",
      "url": "https://www.sedecatastro.gob.es/ (Sede Electrónica, descarga con Cl@ve)",
      "fecha_descarga": "2026-11-27",
      "licencia": "Resolución de la DGC de 23-03-2011, https://www.catastro.hacienda.gob.es/ayuda/legislacion/ovc/resoluciondgc20110323_tfs.pdf",
      "publicable": false,
      "restricciones_uso": ["solo uso interno", "no difundir el original ni recortes por internet", "citar «Dirección General del Catastro» y la fecha de acceso"],
      "sha256": "a rellenar por el fundador",
      "tamano_bytes": "a rellenar por el fundador",
      "almacen": {"tipo": "release", "etiqueta": "catastro-historico-28043-20261127", "adjunto": "catastro-historico-28043-3r-20261127.7z"},
      "formato": "fichero",
      "destino": "raw/catastro_historico/28043/3R.7z",
      "procedencia": "procedencia/catastro_historico/catastro-historico-28043-3r-20261127.procedencia.json",
      "sustituido_por": null
    }
  ]
}
```

## Plantilla del lote de Aranjuez (28013)

La descarga de Aranjuez está en curso. Es un segundo lote con los mismos pasos 1 a 7 (el repo ya existe: el paso 1 no se repite, y el 0 se revisa igual). Se añade al catálogo **una entrada por producto descargado**, siguiendo esta plantilla. La fecha y los sha256 se rellenan cuando el fundador los tenga; no se dan por hechos antes.

Etiqueta de la release: `catastro-historico-28013-<AAAAMMDD>`, con la fecha de la descarga. Cada entrada, con `<producto>` en minúsculas (`ac`, `tp`, `1r`, `2r`, `3r`) y la fecha de la descarga:

```json
{
  "id": "catastro-historico-28013-<producto>-<AAAAMMDD>",
  "fuente": "catastro_historico",
  "producto": "<nombre del producto>",
  "municipio_ine": "28013",
  "url": "https://www.sedecatastro.gob.es/ (Sede Electrónica, descarga con Cl@ve)",
  "fecha_descarga": "a rellenar por el fundador",
  "licencia": "Resolución de la DGC de 23-03-2011, https://www.catastro.hacienda.gob.es/ayuda/legislacion/ovc/resoluciondgc20110323_tfs.pdf",
  "publicable": false,
  "restricciones_uso": ["solo uso interno", "no difundir el original ni recortes por internet", "citar «Dirección General del Catastro» y la fecha de acceso"],
  "sha256": "a rellenar por el fundador",
  "tamano_bytes": "a rellenar por el fundador",
  "almacen": {"tipo": "release", "etiqueta": "catastro-historico-28013-<AAAAMMDD>", "adjunto": "catastro-historico-28013-<producto>-<AAAAMMDD>.7z"},
  "formato": "fichero",
  "destino": "raw/catastro_historico/28013/<PRODUCTO>.7z",
  "procedencia": "procedencia/catastro_historico/catastro-historico-28013-<producto>-<AAAAMMDD>.procedencia.json",
  "sustituido_por": null
}
```

## Reglas de inmutabilidad

- **Solo se añade.** Una entrada del catálogo no se edita ni se borra. La única modificación permitida a una entrada vieja es rellenar `sustituido_por` con el `id` de la nueva.
- **Un adjunto no se sobrescribe.** Si ya existe un adjunto con ese nombre, GitHub rechaza la subida. No se borra el viejo: una versión nueva es un fichero nuevo, con `id`, adjunto y procedencia propios.
- **Una versión nueva** (por ejemplo, otra descarga de la misma renovación): nuevo `id` con la fecha de esa descarga, nueva release si es otro lote, procedencia nueva, y `sustituido_por` en la entrada vieja.
- Si las releases inmutables están activadas (paso 2), GitHub además impide cambiar una release publicada y mover su etiqueta.

## Qué no se sube

- Hojas de Características, Relación de Propietarios, Fichas parcelarias ni ningún documento con nombres, DNI o NIF de personas (ADR 0055 §6).
- Un proyecto del Fondo Documental que lleve relación de colindantes: solo se sube lo que no tenga nombres. Si no se puede separar, no se sube.
- Tokens, contraseñas ni claves de ningún tipo.

## Quién ejecuta esta guía

Solo el fundador, desde su terminal. Ningún agente ni workflow del repo público ejecuta esta guía ni usa `gh` contra `murcialito/paso-comun-datos`. El comprobador local de sha256 y de titularidad no está en alcance de #296.
