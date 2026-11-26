// Tests de módulo del visor (historia #85). Se lanzan desde pytest (tests/site/nodo.py) con
// `node --test`, sin dependencias. Variables de entorno:
//   VISOR_DIR       copia de los módulos de site/ (con package.json "type": "module")
//   VISOR_FIXTURES  tests/fixtures/visor/datos (sintéticas)
// Los nombres empiezan por "CA<n>:" o "unidad:" para poder filtrarlos con --test-name-pattern.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

const VISOR_DIR = process.env.VISOR_DIR;
const FIXTURES = process.env.VISOR_FIXTURES;
if (!VISOR_DIR || !FIXTURES) throw new Error("faltan VISOR_DIR o VISOR_FIXTURES");

const importar = (nombre) => import(pathToFileURL(join(VISOR_DIR, nombre)).href);
const { CONFIG } = await importar("config.js");
const controladorMod = await importar("controlador.js");
const { crearControlador, validarIndice, fichaDe, atribucionesVisibles } = controladorMod;
const { crearMapa, escaparTexto } = await importar("mapa.js");
const { crearVista } = await importar("vista.js");

const VIAS = CONFIG.capas.find((c) => c.id === "vias_pecuarias");
const CAMINO = CONFIG.capas.find((c) => c.id === "camino_actual");
const INDICE = JSON.parse(await readFile(join(FIXTURES, "indice.json"), "utf8"));
const [A, B, C, D] = INDICE.municipios;

// --- dobles -----------------------------------------------------------------------------

async function cargarJsonFixture(ruta) {
  const relativa = ruta.replace(/^datos\//, "");
  let texto;
  try {
    texto = await readFile(join(FIXTURES, relativa), "utf8");
  } catch {
    throw new Error(`HTTP 404 en ${ruta}`);
  }
  return JSON.parse(texto); // JSON inválido → SyntaxError, como Response.json()
}

function crearMapaDoble() {
  const r = { anadidas: [], quitadas: [], mostradas: [], encuadres: [], atribuciones: [] };
  const presentes = new Map();
  return {
    r,
    presentes,
    anadirCapa(id, geojson, opciones) {
      r.anadidas.push({ id, geojson, opciones });
      presentes.set(id, true);
    },
    quitarCapa(id) {
      r.quitadas.push(id);
      presentes.delete(id);
    },
    mostrarCapa(id, visible) {
      r.mostradas.push([id, visible]);
      if (presentes.has(id)) presentes.set(id, visible);
    },
    encuadrar(bbox) {
      r.encuadres.push(bbox);
    },
    ponerAtribuciones(textos) {
      r.atribuciones.push([...textos]);
    },
  };
}

function crearVistaDoble() {
  const v = {
    municipios: null,
    seleccionado: null,
    estados: {},
    mensaje: "",
    mensajes: [],
    avisoBase: "",
    ponerMunicipios(lista) {
      v.municipios = lista;
    },
    seleccionarMunicipio(ine) {
      v.seleccionado = ine;
    },
    ponerEstadoCapa(id, estado) {
      v.estados[id] = estado;
    },
    mostrarMensaje(texto) {
      v.mensaje = texto;
      v.mensajes.push(texto);
    },
    limpiarMensaje() {
      v.mensaje = "";
    },
    mostrarAvisoBase(texto) {
      v.avisoBase = texto;
    },
    nodoFicha(ficha) {
      return { nodo: ficha };
    },
  };
  return v;
}

async function iniciado(cargarJson = cargarJsonFixture) {
  const mapa = crearMapaDoble();
  const vista = crearVistaDoble();
  const ctl = crearControlador({ mapa, cargarJson, vista, config: CONFIG });
  await ctl.iniciar();
  return { mapa, vista, ctl };
}

const ultima = (xs) => xs[xs.length - 1];
const anadidasDesde = (mapa, desde) => mapa.r.anadidas.slice(desde);

// Documento falso para vista.js: prohíbe innerHTML.
class ElementoFalso {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.texto = "";
    this.dataset = {};
    this.value = "";
    this.className = "";
  }
  set textContent(valor) {
    this.texto = String(valor);
    this.children = [];
  }
  get textContent() {
    return this.texto + this.children.map((c) => c.textContent).join("");
  }
  set innerHTML(_valor) {
    throw new Error("innerHTML prohibido en el visor");
  }
  set outerHTML(_valor) {
    throw new Error("outerHTML prohibido en el visor");
  }
  insertAdjacentHTML() {
    throw new Error("insertAdjacentHTML prohibido en el visor");
  }
  appendChild(hijo) {
    this.children.push(hijo);
    return hijo;
  }
  replaceChildren(...hijos) {
    this.children = hijos;
    this.texto = "";
  }
}

function documentoFalso() {
  const elementos = {};
  for (const id of ["municipio", "mensaje", "aviso-base", "estado-vias_pecuarias", "estado-camino_actual"]) {
    elementos[id] = new ElementoFalso("div");
  }
  return {
    elementos,
    getElementById: (id) => elementos[id] ?? null,
    createElement: (tag) => new ElementoFalso(tag),
  };
}

// L falso para mapa.js: registra llamadas.
function instalarLFalso() {
  const reg = { mapas: [], tiles: [], geojsons: [], controles: [] };
  class Capa {
    constructor(tipo, datos, opciones) {
      Object.assign(this, { tipo, datos, opciones, eventos: {}, popups: [], subcapas: [] });
    }
    on(evento, fn) {
      this.eventos[evento] = fn;
      return this;
    }
    addTo(mapa) {
      mapa.addLayer(this);
      return this;
    }
  }
  globalThis.L = {
    map(contenedor, opciones) {
      const presentes = new Set();
      const m = {
        contenedor,
        opciones,
        presentes,
        vistas: [],
        encuadres: [],
        setView(centro, zoom) {
          m.vistas.push([centro, zoom]);
          return m;
        },
        addLayer(capa) {
          presentes.add(capa);
          return m;
        },
        removeLayer(capa) {
          presentes.delete(capa);
          return m;
        },
        hasLayer: (capa) => presentes.has(capa),
        fitBounds(b) {
          m.encuadres.push(b);
          return m;
        },
      };
      reg.mapas.push(m);
      return m;
    },
    control: {
      attribution(opciones) {
        const c = {
          opciones,
          textos: [],
          addTo(mapa) {
            c.mapa = mapa;
            return c;
          },
          addAttribution(t) {
            c.textos.push(t);
            return c;
          },
          removeAttribution(t) {
            const i = c.textos.indexOf(t);
            if (i >= 0) c.textos.splice(i, 1);
            return c;
          },
        };
        reg.controles.push(c);
        return c;
      },
    },
    tileLayer(url, opciones) {
      const capa = new Capa("tile", url, opciones);
      reg.tiles.push(capa);
      return capa;
    },
    geoJSON(geojson, opciones) {
      const capa = new Capa("geojson", geojson, opciones);
      for (const feature of geojson.features) {
        const sub = {
          feature,
          popups: [],
          bindPopup(contenido) {
            sub.popups.push(contenido);
            return sub;
          },
        };
        opciones.onEachFeature(feature, sub);
        capa.subcapas.push(sub);
      }
      reg.geojsons.push(capa);
      return capa;
    },
  };
  return reg;
}

function mapaReal(opciones = {}) {
  const reg = instalarLFalso();
  const fallos = [];
  const mapa = crearMapa("contenedor", {
    teselas: CONFIG.teselas,
    vistaInicial: CONFIG.vistaInicial,
    atribucionesBase: CONFIG.atribucionesBase,
    alFallarTesela: () => fallos.push(true),
    ...opciones,
  });
  return { reg, mapa, fallos, m: reg.mapas[0], control: reg.controles[0] };
}

const leer = async (ruta) => JSON.parse(await readFile(join(FIXTURES, ruta), "utf8"));

// --- CA2 --------------------------------------------------------------------------------

test("CA2: el selector tiene exactamente los municipios del índice, en su orden", async () => {
  const { vista, mapa } = await iniciado();
  assert.deepEqual(
    vista.municipios,
    INDICE.municipios.map((m) => ({ ine: m.ine, nombre: m.nombre })),
  );
  assert.equal(vista.seleccionado, A.ine);
  assert.deepEqual(ultima(mapa.r.encuadres), A.bbox);
});

test("CA2: elegir un municipio encuadra su bbox", async () => {
  const { vista, mapa, ctl } = await iniciado();
  await ctl.elegirMunicipio(B.ine);
  assert.deepEqual(ultima(mapa.r.encuadres), B.bbox);
  assert.equal(vista.seleccionado, B.ine);
  await ctl.elegirMunicipio(D.ine);
  assert.deepEqual(ultima(mapa.r.encuadres), D.bbox);
});

test("CA2: mapa.js encuadra [oeste, sur, este, norte] como [[sur, oeste], [norte, este]]", () => {
  const { mapa, m } = mapaReal();
  mapa.encuadrar(A.bbox);
  const [oeste, sur, este, norte] = A.bbox;
  assert.deepEqual(ultima(m.encuadres), [
    [sur, oeste],
    [norte, este],
  ]);
});

test("CA2: vista.js llena el selector con una opción por municipio, por textContent", () => {
  const doc = documentoFalso();
  const vista = crearVista(doc, CONFIG.textos);
  vista.ponerMunicipios(INDICE.municipios.map((m) => ({ ine: m.ine, nombre: m.nombre })));
  const opciones = doc.elementos.municipio.children;
  assert.deepEqual(
    opciones.map((o) => [o.tagName, o.value, o.textContent]),
    INDICE.municipios.map((m) => ["option", m.ine, m.nombre]),
  );
});

// --- CA3 --------------------------------------------------------------------------------

test("CA3: desactivar una capa solo la oculta a ella y no recarga ni quita la otra", async () => {
  const { mapa, ctl } = await iniciado();
  const anadidas = mapa.r.anadidas.length;
  const quitadas = mapa.r.quitadas.length;
  ctl.cambiarCapa("vias_pecuarias", false);
  assert.deepEqual(ultima(mapa.r.mostradas), ["vias_pecuarias", false]);
  assert.equal(mapa.presentes.get("vias_pecuarias"), false);
  assert.equal(mapa.presentes.get("camino_actual"), true);
  ctl.cambiarCapa("vias_pecuarias", true);
  assert.deepEqual(ultima(mapa.r.mostradas), ["vias_pecuarias", true]);
  assert.equal(mapa.presentes.get("vias_pecuarias"), true);
  assert.equal(mapa.r.anadidas.length, anadidas, "no se recarga ninguna capa");
  assert.equal(mapa.r.quitadas.length, quitadas, "no se quita ninguna capa");
});

test("CA3: la visibilidad elegida se conserva al cambiar de municipio", async () => {
  const { mapa, ctl } = await iniciado();
  ctl.cambiarCapa("camino_actual", false);
  await ctl.elegirMunicipio(B.ine);
  assert.equal(mapa.presentes.get("camino_actual"), false);
  assert.equal(mapa.presentes.get("vias_pecuarias"), true);
});

test("CA3: mapa.js mostrarCapa quita y repone solo esa capa", () => {
  const { mapa, reg, m } = mapaReal();
  mapa.anadirCapa("vias_pecuarias", { type: "FeatureCollection", features: [] }, {
    estilo: VIAS.estilo,
    alPulsar: () => null,
  });
  mapa.anadirCapa("camino_actual", { type: "FeatureCollection", features: [] }, {
    estilo: CAMINO.estilo,
    alPulsar: () => null,
  });
  const [vias, camino] = reg.geojsons;
  mapa.mostrarCapa("vias_pecuarias", false);
  assert.equal(m.hasLayer(vias), false);
  assert.equal(m.hasLayer(camino), true);
  mapa.mostrarCapa("vias_pecuarias", true);
  assert.equal(m.hasLayer(vias), true);
  assert.equal(m.hasLayer(camino), true);
  assert.equal(reg.geojsons.length, 2, "no se crea ninguna capa nueva");
});

// --- CA4 --------------------------------------------------------------------------------

test("CA4: la atribución de una capa se ve solo mientras está activa; la base, siempre", async () => {
  const { mapa, ctl } = await iniciado();
  const base = [...CONFIG.atribucionesBase];
  assert.deepEqual(ultima(mapa.r.atribuciones), [...base, VIAS.atribucion, CAMINO.atribucion]);
  ctl.cambiarCapa("vias_pecuarias", false);
  assert.deepEqual(ultima(mapa.r.atribuciones), [...base, CAMINO.atribucion]);
  ctl.cambiarCapa("camino_actual", false);
  assert.deepEqual(ultima(mapa.r.atribuciones), base);
  ctl.cambiarCapa("vias_pecuarias", true);
  assert.deepEqual(ultima(mapa.r.atribuciones), [...base, VIAS.atribucion]);
  for (const lista of mapa.r.atribuciones) {
    assert.deepEqual(lista.slice(0, base.length), base, "la base está siempre");
  }
});

test("CA4: una capa que no carga no muestra su atribución", async () => {
  const { mapa, ctl } = await iniciado();
  await ctl.elegirMunicipio(C.ine); // vías pecuarias de C da 404
  assert.deepEqual(ultima(mapa.r.atribuciones), [...CONFIG.atribucionesBase, CAMINO.atribucion]);
});

test("CA4: mapa.js sustituye la lista entera de atribuciones, sin prefijo de Leaflet", () => {
  const { mapa, control, m } = mapaReal();
  assert.equal(m.opciones.attributionControl, false);
  assert.deepEqual(control.opciones, { prefix: false });
  assert.equal(control.mapa, m);
  assert.deepEqual(control.textos, [...CONFIG.atribucionesBase]);
  mapa.ponerAtribuciones([...CONFIG.atribucionesBase, VIAS.atribucion]);
  assert.deepEqual(control.textos, [...CONFIG.atribucionesBase, VIAS.atribucion]);
  mapa.ponerAtribuciones([...CONFIG.atribucionesBase]);
  assert.deepEqual(control.textos, [...CONFIG.atribucionesBase]);
});

test("CA4: mapa.js pasa las atribuciones como texto plano (escapado)", () => {
  const { mapa, control } = mapaReal();
  mapa.ponerAtribuciones(["<a href='x'>enlace</a> & más"]);
  assert.deepEqual(control.textos, ["&lt;a href=&#39;x&#39;&gt;enlace&lt;/a&gt; &amp; más"]);
  assert.equal(escaparTexto(VIAS.atribucion), VIAS.atribucion);
  assert.equal(escaparTexto(CAMINO.atribucion), CAMINO.atribucion);
});

// --- CA6 --------------------------------------------------------------------------------

const TRAMPA = {
  nombre: "<b>Cordel</b> de prueba",
  titular: "Persona Inventada S.L.",
  refcat: "99999A00100001",
  propietario: "Persona Inventada",
  tipo: "<b>Cordel</b>",
  descripcion: "tramo cortado ilegalmente",
  html: "<img src=x onerror=alert(1)>",
};

test("CA6: la ficha solo lleva título, fuente y, en vías pecuarias, el nombre", () => {
  assert.deepEqual(fichaDe(VIAS, TRAMPA), {
    titulo: VIAS.titulo,
    fuente: VIAS.fuente,
    nombre: TRAMPA.nombre,
  });
  assert.deepEqual(fichaDe(CAMINO, TRAMPA), { titulo: CAMINO.titulo, fuente: CAMINO.fuente });
  assert.deepEqual(fichaDe(VIAS, { titular: "x" }), { titulo: VIAS.titulo, fuente: VIAS.fuente });
  assert.deepEqual(fichaDe(VIAS, null), { titulo: VIAS.titulo, fuente: VIAS.fuente });
  assert.deepEqual(fichaDe(VIAS, { nombre: 7 }), { titulo: VIAS.titulo, fuente: VIAS.fuente });
});

test("CA6: el popup del controlador nunca lleva propietarios, refcat ni textos de corte", async () => {
  const { mapa } = await iniciado();
  for (const { id, opciones } of mapa.r.anadidas) {
    const { nodo } = opciones.alPulsar(TRAMPA);
    const texto = JSON.stringify(nodo);
    for (const prohibido of ["Persona Inventada", "99999A00100001", "cortado", "ilegal", "onerror"]) {
      assert.ok(!texto.includes(prohibido), `${id}: ${prohibido}`);
    }
    assert.deepEqual(Object.keys(nodo).sort(), id === "vias_pecuarias"
      ? ["fuente", "nombre", "titulo"]
      : ["fuente", "titulo"]);
  }
  for (const capa of CONFIG.capas) {
    for (const texto of [capa.titulo, capa.fuente]) {
      assert.doesNotMatch(texto, /cort|ilegal|propiet|titular|catastr/i);
    }
  }
});

test("CA6: vista.js inserta la ficha como texto, nunca como HTML", () => {
  const doc = documentoFalso();
  const vista = crearVista(doc, CONFIG.textos);
  const nodo = vista.nodoFicha(fichaDe(VIAS, TRAMPA)); // innerHTML lanzaría
  assert.ok(nodo.textContent.includes("<b>Cordel</b> de prueba"), "el marcado queda como texto");
  assert.ok(nodo.textContent.includes(VIAS.titulo));
  assert.ok(nodo.textContent.includes(VIAS.fuente));
  for (const prohibido of ["Persona Inventada", "99999A00100001", "cortado"]) {
    assert.ok(!nodo.textContent.includes(prohibido));
  }
});

test("CA6: mapa.js enlaza el popup con una función que devuelve el nodo de alPulsar", () => {
  const { mapa, reg } = mapaReal();
  const recibidas = [];
  const nodo = { soyUnNodo: true };
  mapa.anadirCapa("vias_pecuarias", {
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: TRAMPA, geometry: null }],
  }, {
    estilo: VIAS.estilo,
    alPulsar: (props) => {
      recibidas.push(props);
      return nodo;
    },
  });
  const [popup] = reg.geojsons[0].subcapas[0].popups;
  assert.equal(typeof popup, "function", "nunca una cadena HTML");
  assert.equal(popup(), nodo);
  assert.deepEqual(recibidas, [TRAMPA]);
});

// --- CA9 --------------------------------------------------------------------------------

test("CA9: una capa con 404 da un error que nombra capa y municipio; la otra se dibuja", async () => {
  const { mapa, vista, ctl } = await iniciado();
  const desde = mapa.r.anadidas.length;
  await ctl.elegirMunicipio(C.ine);
  assert.ok(vista.mensaje.includes(VIAS.titulo), vista.mensaje);
  assert.ok(vista.mensaje.includes(C.nombre), vista.mensaje);
  assert.equal(vista.estados.vias_pecuarias, "error");
  assert.equal(vista.estados.camino_actual, "ok");
  assert.deepEqual(anadidasDesde(mapa, desde).map((a) => a.id), ["camino_actual"]);
});

test("CA9: un JSON inválido da error de esa capa; la otra se dibuja", async () => {
  const { mapa, vista, ctl } = await iniciado();
  const desde = mapa.r.anadidas.length;
  await ctl.elegirMunicipio(D.ine);
  assert.ok(vista.mensaje.includes(CAMINO.titulo), vista.mensaje);
  assert.ok(vista.mensaje.includes(D.nombre), vista.mensaje);
  assert.equal(vista.estados.camino_actual, "error");
  assert.equal(vista.estados.vias_pecuarias, "ok");
  assert.deepEqual(anadidasDesde(mapa, desde).map((a) => a.id), ["vias_pecuarias"]);
});

test("CA9: elegir otro municipio funciona y borra el mensaje", async () => {
  const { mapa, vista, ctl } = await iniciado();
  await ctl.elegirMunicipio(C.ine);
  assert.notEqual(vista.mensaje, "");
  const desde = mapa.r.anadidas.length;
  await ctl.elegirMunicipio(A.ine);
  assert.equal(vista.mensaje, "");
  assert.deepEqual(anadidasDesde(mapa, desde).map((a) => a.id).sort(), [
    "camino_actual",
    "vias_pecuarias",
  ]);
  assert.equal(vista.estados.vias_pecuarias, "ok");
});

test("CA9: un JSON válido que no es FeatureCollection es fallo, no vacío", async () => {
  const cargar = async (ruta) =>
    ruta.endsWith("indice.json") ? INDICE : ruta.includes("vias_pecuarias") ? { type: "Feature" } : cargarJsonFixture(ruta);
  const { vista } = await iniciado(cargar);
  assert.equal(vista.estados.vias_pecuarias, "error");
  assert.ok(vista.mensaje.includes(VIAS.titulo));
});

test("CA9: vista.js escribe el mensaje en su región y lo limpia", () => {
  const doc = documentoFalso();
  const vista = crearVista(doc, CONFIG.textos);
  vista.mostrarMensaje("No se pudo cargar la capa «X» de Y.");
  assert.equal(doc.elementos.mensaje.textContent, "No se pudo cargar la capa «X» de Y.");
  vista.limpiarMensaje();
  assert.equal(doc.elementos.mensaje.textContent, "");
  vista.ponerEstadoCapa("vias_pecuarias", "error");
  assert.equal(doc.elementos["estado-vias_pecuarias"].textContent, CONFIG.textos.errorCapa);
});

// --- CA10 -------------------------------------------------------------------------------

test("CA10: el mapa base usa la URL de config.js y un fallo de tesela no quita capas", () => {
  const { mapa, reg, m, fallos } = mapaReal();
  const [base] = reg.tiles;
  assert.equal(base.datos, CONFIG.teselas.url);
  assert.equal(base.opciones.maxZoom, 19);
  assert.equal(base.opciones.minZoom, 6);
  assert.equal(base.opciones.crossOrigin, false);
  mapa.anadirCapa("vias_pecuarias", { type: "FeatureCollection", features: [] }, {
    estilo: VIAS.estilo,
    alPulsar: () => null,
  });
  const presentesAntes = new Set(m.presentes);
  base.eventos.tileerror({});
  base.eventos.tileerror({});
  assert.equal(fallos.length, 2);
  assert.deepEqual(m.presentes, presentesAntes);
  assert.ok(m.hasLayer(reg.geojsons[0]));
});

test("CA10: el controlador avisa una vez del mapa base caído sin tocar las capas", async () => {
  const { mapa, vista, ctl } = await iniciado();
  const r = JSON.stringify(mapa.r);
  ctl.falloTesela();
  ctl.falloTesela();
  assert.equal(vista.avisoBase, CONFIG.textos.mapaBaseNoDisponible);
  assert.equal(JSON.stringify(mapa.r), r, "ninguna llamada al mapa");
  assert.equal(vista.mensaje, "", "no se confunde con el error de capa");
});

// --- CA13 -------------------------------------------------------------------------------

test("CA13: una capa vacía no es error, indica «sin trazados» y su interruptor funciona", async () => {
  const { mapa, vista, ctl } = await iniciado();
  await ctl.elegirMunicipio(B.ine);
  assert.equal(vista.mensaje, "");
  assert.equal(vista.estados.vias_pecuarias, "vacia");
  assert.equal(vista.estados.camino_actual, "ok");
  ctl.cambiarCapa("vias_pecuarias", false);
  assert.deepEqual(ultima(mapa.r.mostradas), ["vias_pecuarias", false]);
  ctl.cambiarCapa("vias_pecuarias", true);
  assert.deepEqual(ultima(mapa.r.mostradas), ["vias_pecuarias", true]);
});

test("CA13: una capa que el índice no lista se trata como vacía, sin error", async () => {
  const indice = { municipios: [{ ...A, capas: { camino_actual: A.capas.camino_actual } }] };
  const cargar = async (ruta) => (ruta.endsWith("indice.json") ? indice : cargarJsonFixture(ruta));
  const { vista, ctl, mapa } = await iniciado(cargar);
  assert.equal(vista.mensaje, "");
  assert.equal(vista.estados.vias_pecuarias, "vacia");
  ctl.cambiarCapa("vias_pecuarias", false); // no falla aunque no esté en el mapa
  assert.deepEqual(mapa.r.anadidas.map((a) => a.id), ["camino_actual"]);
});

test("CA13: vista.js muestra «sin trazados de esta capa en el municipio»", () => {
  const doc = documentoFalso();
  const vista = crearVista(doc, CONFIG.textos);
  vista.ponerEstadoCapa("vias_pecuarias", "vacia");
  assert.equal(
    doc.elementos["estado-vias_pecuarias"].textContent,
    "sin trazados de esta capa en el municipio",
  );
  vista.ponerEstadoCapa("vias_pecuarias", "ok");
  assert.equal(doc.elementos["estado-vias_pecuarias"].textContent, "");
});

// --- CA14 -------------------------------------------------------------------------------

test("CA14: un MultiPolygon y un MultiLineString de 2 partes llegan enteros al mapa", async () => {
  const { mapa } = await iniciado();
  const vias = mapa.r.anadidas.find((a) => a.id === "vias_pecuarias").geojson;
  const camino = mapa.r.anadidas.find((a) => a.id === "camino_actual").geojson;
  const multiPol = vias.features.find((f) => f.geometry.type === "MultiPolygon");
  const multiLin = camino.features.find((f) => f.geometry.type === "MultiLineString");
  assert.equal(multiPol.geometry.coordinates.length, 2);
  assert.equal(multiLin.geometry.coordinates.length, 2);
  assert.deepEqual(vias, await leer(A.capas.vias_pecuarias));
  assert.deepEqual(camino, await leer(A.capas.camino_actual));
});

test("CA14: mapa.js da un único popup por trazado multiparte, igual en todas sus partes", async () => {
  const { mapa, reg } = mapaReal();
  const vias = await leer(A.capas.vias_pecuarias);
  mapa.anadirCapa("vias_pecuarias", vias, {
    estilo: VIAS.estilo,
    alPulsar: (props) => fichaDe(VIAS, props),
  });
  const capa = reg.geojsons[0];
  assert.equal(capa.datos, vias, "el GeoJSON llega sin trocear");
  assert.equal(capa.subcapas.length, vias.features.length, "una capa por trazado");
  const multi = capa.subcapas.find((s) => s.feature.geometry.type === "MultiPolygon");
  assert.equal(multi.popups.length, 1);
  assert.deepEqual(multi.popups[0](), {
    titulo: VIAS.titulo,
    fuente: VIAS.fuente,
    nombre: "Vereda sintética multiparte",
  });
});

// --- unidades ---------------------------------------------------------------------------

test("unidad: validarIndice conserva el orden y rechaza formas inválidas", () => {
  assert.deepEqual(validarIndice(INDICE).map((m) => m.ine), ["99001", "99002", "99003", "99004"]);
  const malos = [
    null,
    {},
    { municipios: {} },
    { municipios: [{ ...A, ine: "28" }] },
    { municipios: [A, A] },
    { municipios: [{ ...A, nombre: "" }] },
    { municipios: [{ ...A, bbox: [1, 2, 3] }] },
    { municipios: [{ ...A, bbox: [-3.3, 40.0, -3.4, 40.1] }] },
    { municipios: [{ ...A, capas: { vias_pecuarias: "https://otro.host/x.geojson" } }] },
    { municipios: [{ ...A, capas: { vias_pecuarias: "../x.geojson" } }] },
    { municipios: [{ ...A, capas: { vias_pecuarias: "/x.geojson" } }] },
  ];
  for (const malo of malos) assert.throws(() => validarIndice(malo), JSON.stringify(malo));
});

test("unidad: un índice que no carga muestra un error y no deja el selector a medias", async () => {
  const cargar = async () => {
    throw new Error("HTTP 404");
  };
  const { vista, mapa } = await iniciado(cargar);
  assert.equal(vista.mensaje, CONFIG.textos.errorIndice);
  assert.equal(vista.municipios, null);
  assert.deepEqual(mapa.r.atribuciones, [[...CONFIG.atribucionesBase]]);
});

test("unidad: una elección antigua que termina tarde no pisa la más reciente", async () => {
  const esperas = [];
  const cargar = (ruta) => {
    if (ruta.endsWith("indice.json")) return Promise.resolve(INDICE);
    return new Promise((resolve, reject) => {
      esperas.push(() => cargarJsonFixture(ruta).then(resolve, reject));
    });
  };
  const mapa = crearMapaDoble();
  const vista = crearVistaDoble();
  const ctl = crearControlador({ mapa, cargarJson: cargar, vista, config: CONFIG });
  const inicio = ctl.iniciar(); // elige A; sus cargas quedan pendientes
  await new Promise((r) => setImmediate(r));
  const deA = esperas.splice(0);
  const eleccionC = ctl.elegirMunicipio(C.ine);
  await new Promise((r) => setImmediate(r));
  for (const soltar of esperas.splice(0)) soltar();
  await eleccionC;
  for (const soltar of deA) soltar();
  await inicio;
  assert.deepEqual(mapa.r.anadidas.map((a) => a.geojson.properties.municipio), ["99003"]);
  assert.ok(vista.mensaje.includes(C.nombre));
});

test("unidad: atribucionesVisibles exige capa cargada y visible", () => {
  const estado = {
    capas: {
      vias_pecuarias: { cargada: true, visible: false },
      camino_actual: { cargada: false, visible: true },
    },
  };
  assert.deepEqual(atribucionesVisibles(CONFIG, estado), [...CONFIG.atribucionesBase]);
});

test("unidad: crearMapa falla con un mensaje claro si la librería no está cargada", () => {
  delete globalThis.L;
  assert.throws(() => crearMapa("x", { teselas: CONFIG.teselas }), /no está cargada/);
});
