// Composición del visor (historia #85, ADR 0037): único sitio que junta `document`, `fetch`,
// mapa.js, controlador.js, vista.js y config.js.

import { CONFIG } from "./config.js";
import { crearControlador } from "./controlador.js";
import { temaDe } from "./estilos-capas.js";
import { crearMapa } from "./mapa.js";
import { crearVista } from "./vista.js";

async function cargarJson(ruta) {
  const respuesta = await fetch(ruta);
  if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status} en ${ruta}`);
  return await respuesta.json(); // JSON inválido → rechazo → error de capa (CA9)
}

// Único fichero que lee `data-tema` y la preferencia del sistema (#165).
const consulta = globalThis.matchMedia?.("(prefers-color-scheme: dark)");
const temaActual = () =>
  temaDe(document.documentElement.getAttribute("data-tema"), Boolean(consulta?.matches));

const vista = crearVista(document, CONFIG.textos);
let controlador = null;
const mapa = crearMapa(document.getElementById("mapa"), {
  teselas: CONFIG.teselas,
  vistaInicial: CONFIG.vistaInicial,
  atribucionesBase: CONFIG.atribucionesBase,
  alFallarTesela: () => controlador?.falloTesela(),
  tema: temaActual(),
});
consulta?.addEventListener?.("change", () => mapa.ponerTema(temaActual()));
controlador = crearControlador({ mapa, cargarJson, vista, config: CONFIG });

document.getElementById("municipio").addEventListener("change", (evento) => {
  controlador.elegirMunicipio(evento.target.value);
});
for (const capa of CONFIG.capas) {
  const casilla = document.getElementById(`capa-${capa.id}`);
  controlador.cambiarCapa(capa.id, casilla.checked);
  casilla.addEventListener("change", (evento) => {
    controlador.cambiarCapa(capa.id, evento.target.checked);
  });
}

controlador.iniciar();
