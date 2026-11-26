# Conjunto de validación congelado

version: 2
fecha: 2026-11-26
casos_total: 6
casos_ambito: 2
sha256: 677e0003595b9936df17e63b732c2478a69721da961d066c6f1e2dd999b831f8
etiqueta: validacion-v2
motivo: Solo se añade tramo_linea a los casos localizables, porque sin geometría la medición de cobertura (historia #110/#111) no tiene casos evaluables; texto, fuente y fecha de todos los casos quedan intactos. Línea añadida: aranjuez-camino-de-ocana-a-la-barca, de unos 151 m, dibujada de forma aproximada en el extremo noreste de la vía pecuaria Colada de Toledo, siguiendo la dirección de la vía pecuaria Descansadero Caz de las Aves (capa de vías pecuarias de la Comunidad de Madrid, IDEM, ya cacheada en el repo; consultada el 2026-11-26), que es donde la fuente sitúa el corte por el canal; su origen es esa capa pública y no procede del polígono de ninguna finca. aranjuez-camino-de-las-infantas queda sin tramo_linea porque ninguna cartografía pública consultada (vías pecuarias, red del IGN, ortofoto PNOA) permite localizarlo con fiabilidad. Los 4 casos de la Comunidad quedan fuera de las capas derivadas y sin geometría.

No ajustar umbrales de detección antes de esta fecha; cualquier cambio de casos exige una nueva versión con motivo.
