// Composición del visor (historia #85, ADR 0037; rediseño #185, ADR 0051): único sitio que junta
// `document`, `fetch`, `location`, mapa.js, controlador.js, vista.js, enlace.js y config.js.

import { CONFIG } from "./config.js";
import { crearControlador } from "./controlador.js";
import { escribirEnlace, leerEnlace } from "./enlace.js";
import { temaDe } from "./estilos-capas.js";
import { crearMapa } from "./mapa.js";
import { crearVista } from "./vista.js";

async function cargarJson(ruta) {
  const respuesta = await fetch(ruta);
  if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status} en ${ruta}`);
  return await respuesta.json(); // JSON inválido → rechazo → error de capa (CA9 de #85)
}

// Único fichero que lee `data-tema` y las preferencias del sistema (#165).
const consulta = globalThis.matchMedia?.("(prefers-color-scheme: dark)");
const temaActual = () =>
  temaDe(document.documentElement.getAttribute("data-tema"), Boolean(consulta?.matches));
const sinMovimiento = Boolean(globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches);
const esMovil = () => Boolean(globalThis.matchMedia?.("(max-width: 899px)")?.matches);

// Lo que tapan los paneles flotantes, para que un encuadre no quede debajo de ellos.
function relleno() {
  const caja = (selector) => document.querySelector(selector)?.getBoundingClientRect();
  if (esMovil()) {
    const barra = caja(".pc-barra");
    const hoja = document.body.dataset.ficha === "abierta" ? caja(".pc-ficha") : caja(".pc-cuerpo");
    return {
      arriba: barra ? barra.bottom : 0,
      abajo: hoja ? Math.max(0, globalThis.innerHeight - hoja.top) : 0,
      izquierda: 0,
      derecha: 0,
    };
  }
  const panel = caja(".pc-panel");
  const ficha = document.body.dataset.ficha === "abierta" ? caja(".pc-ficha") : null;
  return {
    arriba: 0,
    abajo: 0,
    izquierda: panel ? panel.right : 0,
    derecha: ficha ? Math.max(0, globalThis.innerWidth - ficha.left) : 0,
  };
}

// En móvil, la atribución de Leaflet sube por encima de la hoja abierta (ficha o capas): nunca
// queda tapada (CA5 de #185, invariante de atribución visible). `--hoja-alto` es lo que tapa
// la hoja por abajo; `--atribucion-alto`, lo que ocupa la atribución, para que la ficha
// ampliada le deje sitio bajo la barra de búsqueda.
function publicarHojas() {
  const raiz = document.documentElement.style;
  const atribucion = document.querySelector(".leaflet-control-attribution");
  raiz.setProperty("--hoja-alto", `${Math.round(relleno().abajo)}px`);
  raiz.setProperty(
    "--atribucion-alto",
    `${Math.ceil(atribucion?.getBoundingClientRect().height ?? 0)}px`,
  );
}
let pendiente = false;
const vigilarHojas = () => {
  if (pendiente) return;
  pendiente = true;
  requestAnimationFrame(() => {
    pendiente = false;
    publicarHojas();
  });
};

const vista = crearVista(document, CONFIG.textos);
let controlador = null;
const mapa = crearMapa(document.getElementById("mapa"), {
  fondos: CONFIG.fondos,
  fondoInicial: CONFIG.fondoInicial,
  encuadreInicial: CONFIG.espana,
  alFallarTesela: () => controlador?.falloTesela(),
  alPulsarFondo: () => controlador?.cerrarFicha(),
  tema: temaActual(),
  relleno,
  animar: !sinMovimiento,
});
consulta?.addEventListener?.("change", () => mapa.ponerTema(temaActual()));

controlador = crearControlador({
  mapa,
  cargarJson,
  vista,
  config: CONFIG,
  // El enlace se reescribe sin añadir entradas al historial.
  alCambiarEnlace: (estado) => {
    const busqueda = escribirEnlace(estado);
    if (busqueda !== location.search) {
      history.replaceState(null, "", `${location.pathname}${busqueda}${location.hash}`);
    }
  },
});

// --- buscador ---------------------------------------------------------------------------
const entrada = document.getElementById("buscar");
const sugerir = () => {
  const lista = controlador.buscar(entrada.value);
  const n = controlador.estado.municipios.length;
  vista.mostrarSugerencias(lista, CONFIG.textos.sinCoincidencias.replaceAll("{n}", String(n)));
};
vista.conectar({
  alEscribir: sugerir,
  alElegirMunicipio: (ine) => {
    entrada.blur();
    controlador.elegirMunicipio(ine);
  },
  alAcercar: () => {
    if (esMovil()) vista.ampliarFicha(false);
    controlador.acercarSeleccion();
  },
  alCopiarEnlace: async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      vista.avisar(CONFIG.textos.enlaceCopiado);
    } catch {
      vista.avisar(location.href);
    }
  },
});
entrada.addEventListener("input", sugerir);
entrada.addEventListener("focus", sugerir);
entrada.addEventListener("keydown", (evento) => vista.teclaBuscador(evento));
entrada.addEventListener("blur", () => setTimeout(() => vista.cerrarSugerencias(), 120));
entrada.form.addEventListener("submit", (evento) => evento.preventDefault());

// --- panel, capas y fondo -----------------------------------------------------------------
document.getElementById("ver-espana").addEventListener("click", () => controlador.verEspana());
const plegar = document.getElementById("plegar");
plegar.addEventListener("click", () => {
  vista.plegarPanel(plegar.getAttribute("aria-expanded") !== "true");
});
vista.plegarPanel(false);

for (const capa of CONFIG.capas) {
  const casilla = document.getElementById(`capa-${capa.id}`);
  controlador.cambiarCapa(capa.id, casilla.checked);
  casilla.addEventListener("change", (evento) => {
    controlador.cambiarCapa(capa.id, evento.target.checked);
  });
}
for (const fondo of CONFIG.fondos) {
  document.getElementById(`fondo-${fondo.id}`).addEventListener("change", (evento) => {
    if (evento.target.checked) controlador.cambiarFondo(fondo.id);
  });
}

// --- ficha ------------------------------------------------------------------------------
document.getElementById("ficha-cerrar").addEventListener("click", () => controlador.cerrarFicha());
const ampliar = document.getElementById("ficha-ampliar");
ampliar.addEventListener("click", () => {
  vista.ampliarFicha(ampliar.getAttribute("aria-expanded") !== "true");
});
document.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape" && document.body.dataset.ficha === "abierta") {
    controlador.cerrarFicha();
  }
});

// --- atribución por encima de las hojas (móvil) -----------------------------------------------
if (globalThis.ResizeObserver) {
  const tamanos = new ResizeObserver(vigilarHojas);
  for (const selector of [".pc-ficha", ".pc-cuerpo", ".pc-barra", ".leaflet-control-attribution"]) {
    const elemento = document.querySelector(selector);
    if (elemento) tamanos.observe(elemento);
  }
}
new MutationObserver(vigilarHojas).observe(document.body, {
  attributes: true,
  attributeFilter: ["data-ficha", "data-panel"],
});
globalThis.addEventListener("resize", vigilarHojas);
publicarHojas();

controlador.iniciar(leerEnlace(location.search));
