# ADR 0060 — Catálogo de citas normativas: formato, huella y política de reutilización del BOE

Estado: aceptado
Fecha: 2026-11-28
Historias: #187 (feature #105; contenido en #188, consumo en #189)

> Numeración: el diseño de #187 dejaba el número «al crear el fichero». El siguiente libre el
> 2026-11-28 era el 0060.

## Contexto

El dossier para el ayuntamiento (épica #8) debe citar la normativa que regula cada tipo de bien
(vía pecuaria, camino) sin interpretarla ni parafrasearla. Las citas las escribe una persona; ningún
LLM interviene. Una cita se asocia al tipo de fuente del indicio (`SourceKind`), nunca a una finca,
un tramo ni un municipio. El texto de las leyes puede contener palabras vetadas en el texto público
(«titular»): solo se admiten dentro del literal citado.

El aviso legal del BOE (https://www.boe.es/informacion/aviso_legal/index.php, leído el 2026-11-27 y
releído el 2026-11-28) permite reutilizar sus documentos con fines comerciales y no comerciales con
estas condiciones: citar la fuente con enlace a boe.es («Fuente de los datos: Agencia Estatal Boletín
Oficial del Estado» al copiar o difundir; «Basado en datos de la Agencia Estatal Boletín Oficial del
Estado» en obras derivadas); no desnaturalizar el sentido; mencionar la fecha de la última
actualización si el documento la incluye; no sugerir carácter oficial, y en la legislación
consolidada «indicarse expresamente que se trata de un texto consolidado de carácter meramente
informativo». Solo son oficiales y auténticos los textos de la edición electrónica. Las citas
literales están en `REGISTRY.md`, sección «BOE».

El aviso legal del BOCM (https://www.bocm.es/aviso-legal, leído el 2026-11-27) no tiene condiciones de
reutilización. Solo dice que la reproducción, distribución o transformación no autorizadas, salvo para
uso personal y privado, infringen la propiedad intelectual.

## Decisión

1. **Entrada humana en git**: `curated/normativa/catalogo.json`, con formato cerrado
   `{"version", "huella_catalogo", "citas": [{id, norma, identificador, articulo, fecha_norma,
   ultima_actualizacion, texto, texto_sha256, url, consultado, licencia, version_catalogo,
   tipos_fuente, nota?}]}`. Cualquier otra clave rechaza el fichero entero, y así no cabe ningún
   campo de finca, tramo, municipio ni persona. Se edita a mano en una PR. Al estar bajo
   `curated/**`, la aprueba el fundador. Ningún agente escribe su contenido.
2. **Solo el BOE, solo texto consolidado**: la URL es `https://www.boe.es/buscar/act.php?id=<identificador>`
   con ancla opcional (`#a2`), y el identificador cumple `BOE-A-AAAA-N`. La licencia es un valor
   cerrado: las condiciones de reutilización del BOE con el enlace a su aviso legal. El BOCM queda
   fuera mientras no se lea una licencia que permita difundir sus textos.
3. **Literal sin interpretar**: el texto se copia tal cual del texto consolidado. Debe estar en NFC,
   sin espacios al principio ni al final. Es el único campo exento de las palabras vetadas (#16).
   Los demás campos de texto (norma, artículo, nota) las rechazan, igual que las referencias
   catastrales y los localizadores de parcela.
4. **Huella del texto**: `texto_sha256` = sha256 de `texto` en UTF-8, **sin normalizar**. Si no
   coincide, el mensaje da la huella calculada para que quien edita la copie tras comprobar el texto.
5. **Versión y huella del catálogo**: `version` es un entero ≥ 1 que cada cita repite en
   `version_catalogo`. Se sube en la misma PR que cambia, añade o quita cualquier cita. Así una
   versión nombra un contenido fijo y un dossier que la cite es reproducible desde git. La
   `huella_catalogo` es el sha256 del JSON canónico (`sort_keys`, separadores compactos,
   `ensure_ascii`) de `{"version": …, "citas": […]}`, con las citas ordenadas por `id` y cada una
   con **todas** las claves del formato (incluida `texto_sha256`, `tipos_fuente` como lista ordenada
   y `nota` como `null` si falta): el orden del fichero no cuenta. La subida de versión la comprueba
   quien aprueba la PR; el cargador no lee el historial de git.
6. **Fechas**: `fecha_norma ≤ ultima_actualizacion ≤ consultado`, en `AAAA-MM-DD` exacto.
   `ultima_actualizacion` es obligatoria porque el texto consolidado del BOE siempre la trae y su
   licencia exige mencionarla. El dominio no compara con «hoy»: no tiene reloj.
7. **Atribución** (`citation_attribution`): «Fuente de los datos: Agencia Estatal Boletín Oficial del
   Estado», la URL de la cita, la fecha de consulta, la de última actualización y el aviso
   «Texto consolidado de carácter meramente informativo. Únicamente tienen la consideración de
   oficiales y auténticos los textos publicados en la edición electrónica del Boletín Oficial del
   Estado.». Cualquier vista que muestre una cita muestra su atribución completa.
8. **Capas**: entidad y catálogo en `domain/normative_citation.py` (solo stdlib); port
   `NormativeCatalogSource` y error `NormativeCatalogFileError` en `ports/`; adapter
   `CuratedNormativeCatalogFile` en `adapters/curated_normative/`, con stdlib `json` y sin pydantic,
   cuyos mensajes no repiten el valor rechazado (ADR 0047): nombran el fichero, la posición
   («cita 3») o el id ya validado y el campo, y cuentan las claves desconocidas sin nombrarlas. Un
   fichero ausente es un error; un catálogo sin citas es válido. Todo o nada: un fallo no devuelve
   ninguna cita. Ninguna consulta de usuario lee el BOE: el catálogo es estático. No hay caso de uso
   ni comando en esta historia; #189 inyectará el port.
9. `domain/norm.py` (`Norm`, `Provision`, base legal de las reglas de 0017) no se reutiliza ni se toca:
   no lleva literal, consulta, licencia ni huella, y vive en la tabla `rule`.

### Umbrales y decisiones de producto a revisar con el fundador

No bloquean. Cambiarlos solo exige tocar este ADR y sus tests.

- La redacción exacta del aviso informativo y de la atribución (decisión 7). Sigue las fórmulas del
  aviso legal del BOE; #189 la mostrará junto a su texto fijo, que sí aprueba el fundador.
- Topes de longitud: norma 300, artículo 100, nota 500 y texto 20.000 caracteres.
- El orden de las citas es por `id`, así que el orden de lectura lo decide quien elige los ids (se
  recomienda numerar con ceros: `art-02`, `art-10`).
- El BOCM queda excluido hasta leer una licencia que permita difundir sus textos.

## Consecuencias

- El catálogo es público y solo contiene texto legal, fechas, URLs del BOE y tipos de fuente. Hoy
  está vacío (`version` 1, sin citas): el contenido es de #188.
- Cualquier cambio de una cita, incluso una nueva fecha de consulta sin cambios en el texto, sube la
  versión. Los dossieres generados con la versión anterior siguen siendo reproducibles desde git.
- Si una ley cambia en el BOE, el catálogo no se entera solo: hay que volver a leerla. Comprobar que
  la última actualización sigue vigente es tarea de quien revisa el catálogo, sin red en ejecución.
- Admitir otra fuente (BOCM, normativa local) exige ampliar la lista cerrada de licencias y URLs con
  su licencia leída en el documento primario, y otro ADR o una enmienda a este.
- El BOE pasa a «Publicar» en el resumen de `REGISTRY.md` y tiene su sección en `NOTICE`.
