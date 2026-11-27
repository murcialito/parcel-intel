// Tests de módulo del visor (historia #85). Se lanzan desde pytest (tests/site/nodo.py) con
// `node --test`, sin dependencias. Variables de entorno:
//   VISOR_DIR       copia de los módulos de site/ (con package.json "type": "module")
//   VISOR_FIXTURES  tests/fixtures/visor/datos (sintéticas)
//   VISOR_DISENO    docs/design-system/site/js/estilos-capas.js (original, historia #165)
// Los nombres empiezan por "CA<n>:" o "unidad:" para poder filtrarlos con --test-name-pattern.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

const VISOR_DIR = process.env.VISOR_DIR;
const FIXTURES = process.env.VISOR_FIXTURES;
const DATOS = process.env.VISOR_DATOS; // site/datos publicado (historia #95)
const DISENO = process.env.VISOR_DISENO;
const REFCAT = new RegExp(process.env.VISOR_REFCAT_RE ?? "(?!)"); // CADASTRAL_REFERENCE_RE de #94
if (!VISOR_DIR || !FIXTURES) throw new Error("faltan VISOR_DIR o VISOR_FIXTURES");

const importar = (nombre) => import(pathToFileURL(join(VISOR_DIR, nombre)).href);
const { CONFIG } = await importar("config.js");
const controladorMod = await importar("controlador.js");
const { crearControlador, validarIndice, fichaDe, atribucionesVisibles } = controladorMod;
const { crearMapa, escaparTexto } = await importar("mapa.js");
const estilosMod = await importar("estilos-capas.js");
const { crearVista } = await importar("vista.js");
const { fichaIndicio } = controladorMod;

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
    nodoFichaIndicio(ficha) {
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
  setAttribute(nombre, valor) {
    this.atributos = { ...(this.atributos ?? {}), [nombre]: String(valor) };
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
  for (const id of ["municipio", "mensaje", "aviso-base", "estado-vias_pecuarias", "estado-camino_actual", "estado-discrepancias"]) {
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
  const reg = { mapas: [], tiles: [], geojsons: [], grupos: [], panes: {}, controles: [] };
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
        getPane: (nombre) => reg.panes[nombre],
        createPane(nombre) {
          reg.panes[nombre] = { style: {} };
          return reg.panes[nombre];
        },
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
    layerGroup(capas) {
      const grupo = new Capa("grupo", null, {});
      grupo.capas = capas;
      reg.grupos.push(grupo);
      return grupo;
    },
    geoJSON(geojson, opciones) {
      const capa = new Capa("geojson", geojson, opciones);
      for (const feature of geojson.features) {
        const sub = {
          feature,
          popups: [],
          eventos: {},
          estilos: [],
          frentes: 0,
          estiloInicial: opciones.style ? opciones.style(feature) : null,
          bindPopup(contenido) {
            sub.popups.push(contenido);
            return sub;
          },
          on(evento, fn) {
            sub.eventos[evento] = fn;
            return sub;
          },
          disparar(evento) {
            sub.eventos[evento]?.({});
          },
          setStyle(estilo) {
            sub.estilos.push(estilo);
            return sub;
          },
          bringToFront() {
            sub.frentes += 1;
            return sub;
          },
          get ultimoEstilo() {
            return sub.estilos.length ? sub.estilos[sub.estilos.length - 1] : sub.estiloInicial;
          },
        };
        opciones.onEachFeature?.(feature, sub);
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
    clave: "viasPecuarias",
    alPulsar: () => null,
  });
  mapa.anadirCapa("camino_actual", { type: "FeatureCollection", features: [] }, {
    clave: "caminoActual",
    alPulsar: () => null,
  });
  const [vias, camino] = reg.grupos;
  mapa.mostrarCapa("vias_pecuarias", false);
  assert.equal(m.hasLayer(vias), false);
  assert.equal(m.hasLayer(camino), true);
  mapa.mostrarCapa("vias_pecuarias", true);
  assert.equal(m.hasLayer(vias), true);
  assert.equal(m.hasLayer(camino), true);
  assert.equal(reg.grupos.length, 2, "no se crea ninguna capa nueva");
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
    clave: "viasPecuarias",
    alPulsar: (props) => {
      recibidas.push(props);
      return nodo;
    },
  });
  const [popup] = reg.geojsons[1].subcapas[0].popups; // [0] es el halo
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
    clave: "viasPecuarias",
    alPulsar: () => null,
  });
  const presentesAntes = new Set(m.presentes);
  base.eventos.tileerror({});
  base.eventos.tileerror({});
  assert.equal(fallos.length, 2);
  assert.deepEqual(m.presentes, presentesAntes);
  assert.ok(m.hasLayer(reg.grupos[0]));
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
    clave: "viasPecuarias",
    alPulsar: (props) => fichaDe(VIAS, props),
  });
  const capa = reg.geojsons[1]; // [0] es el halo, [1] la línea
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

// --- historia #95: indicios de discrepancia ---------------------------------------------
// Los nombres empiezan por "H95 CA<n>:" para filtrarlos desde tests/acceptance/test_historia_95.py.

const INDICIOS = CONFIG.capas.find((c) => c.id === "discrepancias");
const RUTA_IND = "discrepancias/99001.geojson";
const AVISO = CONFIG.textos.avisoIndicio;

const propsIndicio = (extra = {}) => ({
  tipo: "AUSENTE_EN_FUENTE",
  etiqueta: "Trazado en una fuente y no en otra",
  texto: "Indicio a verificar: texto sintético.",
  aviso: AVISO,
  confianza: "media",
  evidencia: [
    {
      papel: "sujeto",
      fuente: "fuente sintética A",
      anio: 1956,
      origen: "sintetico",
      url: "https://ejemplo.invalid/a",
      fecha_descarga: "2026-11-26",
      licencia: "CC BY 4.0 sintética",
      atribucion: "Atribución sintética A",
    },
    {
      papel: "contraparte",
      fuente: "fuente sintética B",
      anio: null,
      origen: "sintetico",
      url: "http://ejemplo.invalid/b",
      fecha_descarga: "2026-11-25",
      licencia: "CC BY 4.0 sintética B",
      atribucion: "Atribución sintética B",
    },
  ],
  criterio: "criterio_sintetico v3",
  descripcion_criterio: "Descripción sintética del criterio.",
  aviso_omision: null,
  ...extra,
});

const coleccion = (...props) => ({
  type: "FeatureCollection",
  features: props.map((p, i) => ({
    type: "Feature",
    properties: p,
    geometry:
      i % 2 === 0
        ? { type: "LineString", coordinates: [[-3.4, 40.08], [-3.39, 40.09]] }
        : { type: "Polygon", coordinates: [[[-3.4, 40.08], [-3.39, 40.08], [-3.39, 40.09], [-3.4, 40.08]]] },
  })),
});

function indiceConIndicios(sinIndicios = false) {
  return {
    municipios: INDICE.municipios.map((m, i) =>
      i === 0 && !sinIndicios ? { ...m, capas: { ...m.capas, discrepancias: RUTA_IND } } : m,
    ),
  };
}

function cargadorIndicios(respuestaIndicios, sinIndicios = false) {
  const llamadas = [];
  const cargar = async (ruta) => {
    llamadas.push(ruta);
    if (ruta.endsWith("indice.json")) return indiceConIndicios(sinIndicios);
    if (ruta.endsWith(RUTA_IND)) {
      if (respuestaIndicios instanceof Error) throw respuestaIndicios;
      return respuestaIndicios;
    }
    return cargarJsonFixture(ruta);
  };
  return { cargar, llamadas };
}

const hijos = (nodo) => nodo.children.flatMap((h) => [h, ...hijos(h)]);
const enlaces = (nodo) => hijos(nodo).filter((h) => h.tagName === "a");

function nodoDe(propiedades) {
  const vista = crearVista(documentoFalso(), CONFIG.textos);
  return vista.nodoFichaIndicio(fichaIndicio(propiedades, CONFIG));
}

test("H95 CA1: la capa de indicios se carga del índice y se dibuja con estilo distinto", async () => {
  const { cargar, llamadas } = cargadorIndicios(coleccion(propsIndicio()));
  const { mapa } = await iniciado(cargar);
  assert.ok(llamadas.includes(CONFIG.datos + RUTA_IND));
  const dibujada = mapa.r.anadidas.find((a) => a.id === "discrepancias");
  assert.ok(dibujada, "se dibuja");
  assert.equal(INDICIOS.titulo, "Indicios a verificar (no son un dictamen)");
  // Historia #165: el estilo ya no es un objeto plano sino una clave del sistema de diseño.
  // Los indicios usan claves `indicio*`, distintas de las de las otras dos capas, y punteadas.
  const clavesIndicio = Object.values(INDICIOS.estilo.claves);
  assert.deepEqual(clavesIndicio, ["indicioBaja", "indicioMedia", "indicioAlta"]);
  for (const otra of [VIAS, CAMINO]) {
    assert.ok(!clavesIndicio.includes(otra.estilo.clave));
  }
  for (const clave of clavesIndicio) {
    assert.ok(estilosMod.estilo(clave).linea.dashArray, "trazo punteado");
  }
  assert.equal(typeof dibujada.opciones.claveDe, "function");
  // La ficha de un indicio pulsado es la de indicios, no la genérica.
  assert.ok("nodo" in dibujada.opciones.alPulsar(propsIndicio()));
  assert.equal(dibujada.opciones.alPulsar(propsIndicio()).nodo.disponible, true);
});

test("H95 CA2: nace apagada, sin atribución; al marcar y desmarcar aparece y desaparece", async () => {
  const { cargar } = cargadorIndicios(coleccion(propsIndicio()));
  const { mapa, ctl } = await iniciado(cargar);
  const base = [...CONFIG.atribucionesBase];
  assert.equal(mapa.presentes.get("discrepancias"), false);
  assert.equal(mapa.presentes.get("vias_pecuarias"), true);
  assert.equal(mapa.presentes.get("camino_actual"), true);
  assert.deepEqual(ultima(mapa.r.atribuciones), [...base, VIAS.atribucion, CAMINO.atribucion]);
  ctl.cambiarCapa("discrepancias", true);
  assert.equal(mapa.presentes.get("discrepancias"), true);
  assert.deepEqual(ultima(mapa.r.atribuciones), [
    ...base,
    VIAS.atribucion,
    CAMINO.atribucion,
    INDICIOS.atribucion,
  ]);
  ctl.cambiarCapa("discrepancias", false);
  assert.equal(mapa.presentes.get("discrepancias"), false);
  assert.deepEqual(ultima(mapa.r.atribuciones), [...base, VIAS.atribucion, CAMINO.atribucion]);
});

test("H95 CA3: un municipio sin la capa en el índice dice «sin indicios publicados», sin error", async () => {
  const { cargar, llamadas } = cargadorIndicios(coleccion(), true);
  const { mapa, vista } = await iniciado(cargar);
  assert.equal(vista.estados.discrepancias, "sin_indicios");
  assert.equal(vista.mensaje, "");
  assert.ok(!llamadas.some((r) => r.includes("discrepancias")));
  assert.deepEqual(mapa.r.anadidas.map((a) => a.id).sort(), ["camino_actual", "vias_pecuarias"]);
  const doc = documentoFalso();
  crearVista(doc, CONFIG.textos).ponerEstadoCapa("discrepancias", "sin_indicios");
  assert.equal(doc.elementos["estado-discrepancias"].textContent, "sin indicios publicados");
});

test("H95 CA4: un fichero que falla o no es FeatureCollection da error de esa capa; las otras se dibujan", async () => {
  for (const respuesta of [new Error("HTTP 404"), { type: "Feature" }, null]) {
    const { cargar } = cargadorIndicios(respuesta);
    const { mapa, vista } = await iniciado(cargar);
    assert.equal(vista.estados.discrepancias, "error");
    assert.ok(vista.mensaje.includes(INDICIOS.titulo), vista.mensaje);
    assert.deepEqual(mapa.r.anadidas.map((a) => a.id).sort(), ["camino_actual", "vias_pecuarias"]);
  }
  const doc = documentoFalso();
  crearVista(doc, CONFIG.textos).ponerEstadoCapa("discrepancias", "error");
  assert.equal(doc.elementos["estado-discrepancias"].textContent, "no se pudo cargar");
});

test("H95 CA5: la ficha va en orden: etiqueta, texto, confianza, aviso y fuentes", () => {
  const t = nodoDe(propsIndicio()).textContent;
  const orden = [
    "Trazado en una fuente y no en otra",
    "Indicio a verificar: texto sintético.",
    "confianza media",
    AVISO,
    "fuente sintética A",
  ].map((s) => t.indexOf(s));
  assert.ok(orden.every((i) => i >= 0), JSON.stringify(orden));
  assert.deepEqual(orden, [...orden].sort((a, b) => a - b));
  for (const nivel of ["baja", "media", "alta"]) {
    assert.ok(nodoDe(propsIndicio({ confianza: nivel })).textContent.includes(`confianza ${nivel}`));
  }
});

test("H95 CA6: cada fuente con papel, nombre, año, fecha, licencia, atribución y enlace https", () => {
  const nodo = nodoDe(propsIndicio());
  const t = nodo.textContent;
  for (const s of [
    "sujeto: fuente sintética A (1956)",
    "contraparte: fuente sintética B (año no declarado)",
    "2026-11-26",
    "2026-11-25",
    "CC BY 4.0 sintética",
    "Atribución sintética A",
    "Atribución sintética B",
  ]) {
    assert.ok(t.includes(s), s);
  }
  const a = enlaces(nodo);
  assert.equal(a.length, 1, "solo la URL https es un enlace");
  assert.equal(a[0].atributos.href, "https://ejemplo.invalid/a");
  assert.equal(a[0].atributos.rel, "noopener noreferrer");
  assert.ok(t.includes("http://ejemplo.invalid/b"), "la URL no https se muestra como texto");
  for (const url of ["javascript:alert(1)", "//otro.host/x", "HTTPS://x", ""]) {
    const n = nodoDe(propsIndicio({ evidencia: [{ ...propsIndicio().evidencia[0], url }] }));
    assert.equal(enlaces(n).length, 0, url);
  }
});

test("H95 CA7: criterio con versión, su descripción y el aviso de omisión si existe", () => {
  const t = nodoDe(propsIndicio()).textContent;
  assert.ok(t.includes("criterio_sintetico v3"));
  assert.ok(t.includes("Descripción sintética del criterio."));
  const con = nodoDe(propsIndicio({ aviso_omision: "Se omitió una fuente sintética." })).textContent;
  assert.ok(con.includes("Se omitió una fuente sintética."));
  assert.ok(!t.includes("omitió"), "con null no se muestra");
});

test("H95 CA8: el aviso siempre está; sin aviso en la feature se usa el fijo; forma rota solo aviso", () => {
  assert.ok(nodoDe(propsIndicio()).textContent.includes(AVISO));
  assert.equal(fichaIndicio(propsIndicio({ aviso: undefined }), CONFIG).aviso, AVISO);
  assert.equal(fichaIndicio(propsIndicio({ aviso: "  " }), CONFIG).aviso, AVISO);
  const rotas = [
    {},
    null,
    undefined,
    "texto",
    propsIndicio({ texto: undefined }),
    propsIndicio({ evidencia: "no-lista" }),
    propsIndicio({ evidencia: null }),
  ];
  for (const rota of rotas) {
    const nodo = nodoDe(rota);
    assert.ok(nodo.textContent.includes(AVISO), JSON.stringify(rota));
    assert.ok(nodo.textContent.includes("ficha no disponible"), JSON.stringify(rota));
    assert.ok(!nodo.textContent.includes("fuente sintética"));
  }
  assert.doesNotThrow(() => nodoDe(propsIndicio({ evidencia: [null, 3, "x", {}] })));
});

test("H95 CA9: el marcado HTML de los datos se ve como texto y nada usa innerHTML", () => {
  const html = "<img src=x onerror=alert(1)>";
  const nodo = nodoDe(
    propsIndicio({
      etiqueta: html,
      texto: `texto ${html}`,
      evidencia: [{ ...propsIndicio().evidencia[0], fuente: html, atribucion: html, url: html }],
    }),
  ); // el documento falso lanza si algo toca innerHTML/outerHTML/insertAdjacentHTML
  assert.ok(nodo.textContent.includes(html));
  assert.equal(enlaces(nodo).length, 0);
  assert.ok(!hijos(nodo).some((h) => h.tagName === "img"));
});

test("H95 CA10: las fichas del GeoJSON real no llevan refcat ni propiedades fuera de la lista blanca", async () => {
  const real = JSON.parse(await readFile(join(DATOS, "discrepancias", "28043.geojson"), "utf8"));
  assert.ok(real.features.length > 0);
  for (const f of real.features) {
    const trampa = { ...f.properties, titular: "Persona Inventada", refcat: "99999A00100001", id: "x" };
    const ficha = fichaIndicio(trampa, CONFIG);
    const t = nodoDe(trampa).textContent;
    assert.ok(!REFCAT.test(t), t);
    assert.ok(!t.includes("Persona Inventada") && !t.includes("99999A00100001"));
    assert.ok(!JSON.stringify(ficha).includes("Persona Inventada"));
    assert.deepEqual(Object.keys(ficha).sort(), [
      "aviso",
      "avisoOmision",
      "confianza",
      "criterio",
      "descripcionCriterio",
      "disponible",
      "etiqueta",
      "evidencia",
      "texto",
    ]);
    assert.ok(t.includes(f.properties.texto) && t.includes(f.properties.aviso));
  }
  assert.ok(REFCAT.test("99999A00100001"), "el patrón de refcat no está vacío");
});

test("H95 CA12: al cambiar de municipio los indicios del anterior se quitan y manda la última petición", async () => {
  const { cargar } = cargadorIndicios(coleccion(propsIndicio()));
  const { mapa, ctl } = await iniciado(cargar);
  assert.equal(mapa.presentes.has("discrepancias"), true);
  await ctl.elegirMunicipio(B.ine);
  assert.equal(mapa.presentes.has("discrepancias"), false);
  assert.ok(mapa.r.quitadas.includes("discrepancias"));

  const esperas = [];
  const lenta = (ruta) => {
    if (ruta.endsWith("indice.json")) return Promise.resolve(indiceConIndicios());
    if (ruta.endsWith(RUTA_IND)) {
      return new Promise((resolve) => esperas.push(() => resolve(coleccion(propsIndicio()))));
    }
    return cargarJsonFixture(ruta);
  };
  const m = crearMapaDoble();
  const vista = crearVistaDoble();
  const ctl2 = crearControlador({ mapa: m, cargarJson: lenta, vista, config: CONFIG });
  const inicio = ctl2.iniciar();
  await new Promise((r) => setImmediate(r));
  await ctl2.elegirMunicipio(B.ine);
  for (const soltar of esperas.splice(0)) soltar();
  await inicio;
  assert.ok(!m.r.anadidas.some((a) => a.id === "discrepancias"), "el indicio tardío no se mezcla");
});

test("H95 CA13: cada atribución del sidecar publicado sale en alguna ficha o en la capa", async () => {
  const real = JSON.parse(await readFile(join(DATOS, "discrepancias", "28043.geojson"), "utf8"));
  const sidecar = JSON.parse(
    await readFile(join(DATOS, "discrepancias", "28043.geojson.procedencia.json"), "utf8"),
  );
  const visible = [INDICIOS.atribucion, ...real.features.map((f) => nodoDe(f.properties).textContent)];
  assert.ok(sidecar.atribucion.length > 0);
  for (const a of sidecar.atribucion) {
    assert.ok(visible.some((t) => t.includes(a)), a);
  }
  assert.equal(sidecar.aviso, AVISO);
});

test("unidad: visibleInicial manda; sin él una capa nace encendida", async () => {
  const { ctl } = await iniciado();
  assert.equal(ctl.estado.capas.discrepancias.visible, false);
  assert.equal(ctl.estado.capas.vias_pecuarias.visible, true);
  assert.equal(ctl.estado.capas.camino_actual.visible, true);
});

// --- Historia #165: estilos de capa del sistema de diseño -------------------------------------

const { BASE, ESTILOS, CLAVES, RELLENO, estilo, estiloTrazado, temaDe } = estilosMod;
const ESTADOS = ["normal", "hover", "seleccionado"];
const TEMAS = ["claro", "oscuro"];
const plano = (x) => JSON.parse(JSON.stringify(x)); // quita el prototipo de otro contexto de vm

async function cargarOriginalDiseno() {
  const vm = await import("node:vm");
  const codigo = await readFile(DISENO, "utf8");
  const ventana = {};
  // `document` falso: el original solo lo lee en temaActual(), que aquí no se llama.
  vm.runInNewContext(codigo, { window: ventana, document: {} });
  return ventana.PasoComunEstilos;
}

const lineaDe = (coords) => ({ type: "LineString", coordinates: coords });
const cuadro = {
  type: "Polygon",
  coordinates: [[[-3.4, 40.08], [-3.39, 40.08], [-3.39, 40.09], [-3.4, 40.08]]],
};
const feat = (geometry, properties = {}) => ({ type: "Feature", properties, geometry });
const coleccionDe = (...features) => ({ type: "FeatureCollection", features });
const SEGMENTO = [[-3.4, 40.08], [-3.39, 40.09]];

// Capa dibujada con el L falso: devuelve el halo y la línea de cada trazado.
function dibujar(mapa, reg, id, geojson, opciones) {
  const desde = reg.geojsons.length;
  mapa.anadirCapa(id, geojson, { alPulsar: () => null, ...opciones });
  const [capaHalo, capaLinea] = reg.geojsons.slice(desde);
  return capaLinea.subcapas.map((linea, i) => ({ linea, halo: capaHalo.subcapas[i] }));
}

test("H165 CA1: estilo() es idéntico al del sistema de diseño en todas las combinaciones", async () => {
  const original = await cargarOriginalDiseno();
  assert.deepEqual(plano(BASE), plano(original.BASE));
  assert.deepEqual(plano(ESTILOS), plano(original.ESTILOS));
  for (const clave of ["viasPecuarias", "caminoActual", "trazadoHistorico", "indicioBaja", "indicioMedia", "indicioAlta"]) {
    for (const e of ESTADOS) {
      for (const t of TEMAS) {
        assert.deepEqual(plano(estilo(clave, e, t)), plano(original.estilo(clave, e, t)), `${clave} ${e} ${t}`);
      }
    }
  }
  assert.throws(() => estilo("noExiste", "normal", "claro"), Error);
  assert.throws(() => estilo("viasPecuarias", "noExiste", "claro"), Error);
  assert.throws(() => estilo("viasPecuarias", "normal", "noExiste"), Error);
});

test("H165 CA2: las familias se distinguen por trazo y los indicios crecen con la confianza", () => {
  const n = (clave) => estilo(clave, "normal", "claro").linea;
  const familias = ["viasPecuarias", "caminoActual", "trazadoHistorico", "indicioMedia"].map((c) => {
    const { weight, dashArray } = n(c);
    return JSON.stringify([weight, dashArray]);
  });
  assert.equal(new Set(familias).size, 4, "pares (weight, dashArray) distintos dos a dos");
  assert.equal(n("viasPecuarias").dashArray, null);
  assert.equal(n("caminoActual").dashArray, null);
  assert.ok(n("viasPecuarias").weight > n("caminoActual").weight, "banda ancha frente a línea fina");
  const hueco = (c) => Number(n(c).dashArray.split(" ")[1]);
  const [baja, media, alta] = ["indicioBaja", "indicioMedia", "indicioAlta"];
  assert.ok(n(baja).weight < n(media).weight && n(media).weight < n(alta).weight);
  assert.ok(n(baja).opacity < n(media).opacity && n(media).opacity < n(alta).opacity);
  assert.ok(hueco(baja) > hueco(media) && hueco(media) > hueco(alta));
});

test("H165 CA3: hover engorda y conserva el halo; seleccionar pinta el halo de selección", () => {
  for (const t of TEMAS) {
    const normal = estilo("caminoActual", "normal", t);
    const hover = estilo("caminoActual", "hover", t);
    const sel = estilo("caminoActual", "seleccionado", t);
    assert.ok(hover.linea.weight > normal.linea.weight && hover.halo.weight > normal.halo.weight);
    assert.equal(hover.halo.color, normal.halo.color);
    assert.equal(sel.halo.color, BASE.seleccionHalo[t]);
    assert.ok(sel.linea.weight > normal.linea.weight);
  }
  assert.equal(BASE.seleccionHalo.claro, "#ffffff");
  assert.equal(BASE.seleccionHalo.oscuro, "#e8ebe8");
});

test("H165 CA3: una sola selección en todo el mapa; mouseout no la suelta y cerrar el popup sí", () => {
  const { mapa, reg } = mapaReal();
  const [a] = dibujar(mapa, reg, "vias_pecuarias", coleccionDe(feat(lineaDe(SEGMENTO))), { clave: "viasPecuarias", orden: 10 });
  const [b] = dibujar(mapa, reg, "camino_actual", coleccionDe(feat(lineaDe(SEGMENTO))), { clave: "caminoActual", orden: 30 });
  const sel = (clave) => estiloTrazado(clave, "seleccionado", "claro", false);
  const nor = (clave) => estiloTrazado(clave, "normal", "claro", false);

  a.linea.disparar("mouseover");
  assert.deepEqual(a.linea.ultimoEstilo, estiloTrazado("viasPecuarias", "hover", "claro", false).linea);
  assert.equal(a.halo.ultimoEstilo.color, nor("viasPecuarias").halo.color, "el halo conserva su color");
  a.linea.disparar("mouseout");
  assert.deepEqual(a.linea.ultimoEstilo, nor("viasPecuarias").linea);

  a.linea.disparar("click");
  assert.deepEqual(a.linea.ultimoEstilo, sel("viasPecuarias").linea);
  assert.equal(a.halo.ultimoEstilo.color, BASE.seleccionHalo.claro);
  assert.equal(a.halo.frentes, 1);
  assert.equal(a.linea.frentes, 1);

  b.linea.disparar("click");
  assert.deepEqual(b.linea.ultimoEstilo, sel("caminoActual").linea);
  assert.deepEqual(a.linea.ultimoEstilo, nor("viasPecuarias").linea, "A vuelve a normal");
  assert.deepEqual(a.halo.ultimoEstilo, nor("viasPecuarias").halo);

  b.linea.disparar("mouseover");
  b.linea.disparar("mouseout");
  assert.deepEqual(b.linea.ultimoEstilo, sel("caminoActual").linea, "mouseout no la suelta");
  a.linea.disparar("popupclose");
  assert.deepEqual(b.linea.ultimoEstilo, sel("caminoActual").linea, "cerrar el popup de otro no la suelta");
  b.linea.disparar("popupclose");
  assert.deepEqual(b.linea.ultimoEstilo, nor("caminoActual").linea);
  assert.deepEqual(b.halo.ultimoEstilo, nor("caminoActual").halo);
});

// `propsIndicio` trae una confianza por defecto: aquí se quita para probar la propiedad ausente.
function sinConfianza(extra) {
  const props = propsIndicio(extra);
  if (!("confianza" in extra)) delete props.confianza;
  return props;
}

function indiciosConConfianzas() {
  const confianzas = [{ confianza: "baja" }, { confianza: "media" }, { confianza: "alta" }, { confianza: null }, { confianza: "ALTA" }, {}];
  return coleccionDe(...confianzas.map((c, i) => feat(i % 2 === 0 ? lineaDe(SEGMENTO) : cuadro, sinConfianza(c))));
}

test("H165 CA4: cada capa usa su clave, con halo debajo y línea encima en el mismo pane", async () => {
  const reg = instalarLFalso();
  const mapa = crearMapa("contenedor", { teselas: CONFIG.teselas, tema: "claro" });
  const { cargar } = cargadorIndicios(indiciosConConfianzas());
  const vista = crearVista(documentoFalso(), CONFIG.textos);
  const ctl = crearControlador({ mapa, cargarJson: cargar, vista, config: CONFIG });
  await ctl.iniciar();
  assert.equal(reg.geojsons.length, 6, "tres capas, dos dibujos cada una");
  const [viasH, viasL, camH, camL, indH, indL] = reg.geojsons;

  for (const [halo, linea] of [[viasH, viasL], [camH, camL], [indH, indL]]) {
    assert.equal(halo.opciones.interactive, false);
    assert.notEqual(linea.opciones.interactive, false);
    assert.equal(halo.opciones.pane, linea.opciones.pane, "mismo pane");
    assert.ok(reg.geojsons.indexOf(halo) < reg.geojsons.indexOf(linea), "el halo se añade antes");
    assert.equal(halo.subcapas.length, linea.subcapas.length);
  }
  const poli = (f) => ["Polygon", "MultiPolygon"].includes(f.geometry?.type);
  for (const s of viasL.subcapas) {
    assert.deepEqual(s.estiloInicial, estiloTrazado("viasPecuarias", "normal", "claro", poli(s.feature)).linea);
  }
  for (const s of camL.subcapas) {
    assert.deepEqual(s.estiloInicial, estiloTrazado("caminoActual", "normal", "claro", poli(s.feature)).linea);
  }
  const esperadas = ["indicioBaja", "indicioMedia", "indicioAlta", "indicioBaja", "indicioBaja", "indicioBaja"];
  indL.subcapas.forEach((s, i) => {
    assert.deepEqual(s.estiloInicial, estiloTrazado(esperadas[i], "normal", "claro", poli(s.feature)).linea, `indicio ${i}`);
  });
  // Pulsar sigue mostrando la ficha: un nodo construido con textContent, no una cadena HTML.
  const popup = indL.subcapas[0].popups[0];
  assert.equal(typeof popup, "function");
  const nodo = popup();
  assert.equal(typeof nodo, "object");
  assert.ok(nodo.children.length > 0);
  assert.equal(typeof viasL.subcapas[0].popups[0](), "object");
});

test("H165 CA4: anadirCapa exige exactamente una clave válida o claveDe", () => {
  const { mapa } = mapaReal();
  const vacio = coleccionDe();
  assert.throws(() => mapa.anadirCapa("x", vacio, { alPulsar: () => null }), Error);
  assert.throws(() => mapa.anadirCapa("x", vacio, { clave: "viasPecuarias", claveDe: () => "caminoActual", alPulsar: () => null }), Error);
  assert.throws(() => mapa.anadirCapa("x", vacio, { clave: "noExiste", alPulsar: () => null }), Error);
});

test("H165 CA4: opcionesDeEstilo traduce config.js; confianza desconocida da indicioBaja", () => {
  const { opcionesDeEstilo } = controladorMod;
  assert.deepEqual(opcionesDeEstilo(VIAS), { clave: "viasPecuarias" });
  assert.deepEqual(opcionesDeEstilo(CAMINO), { clave: "caminoActual" });
  const { claveDe } = opcionesDeEstilo(INDICIOS);
  assert.equal(claveDe({ confianza: "baja" }), "indicioBaja");
  assert.equal(claveDe({ confianza: "media" }), "indicioMedia");
  assert.equal(claveDe({ confianza: "alta" }), "indicioAlta");
  for (const raro of [{ confianza: null }, { confianza: "ALTA" }, {}, null, undefined, { confianza: "__proto__" }, { confianza: "toString" }]) {
    assert.equal(claveDe(raro), "indicioBaja", JSON.stringify(raro));
  }
});

test("H165 CA6: el módulo exporta lo acordado, congelado, y estilo() devuelve copias", () => {
  assert.deepEqual([...CLAVES], ["viasPecuarias", "caminoActual", "trazadoHistorico", "indicioBaja", "indicioMedia", "indicioAlta"]);
  for (const nombre of ["BASE", "ESTILOS", "CLAVES", "RELLENO", "estilo", "estiloTrazado", "temaDe"]) {
    assert.ok(nombre in estilosMod, nombre);
  }
  const congelado = (o) => Object.isFrozen(o) && Object.values(o).every((v) => v === null || typeof v !== "object" || congelado(v));
  assert.ok(congelado(BASE), "BASE congelado en profundidad");
  assert.deepEqual({ ...RELLENO }, { viasPecuarias: 0.15, indicioBaja: 0.1, indicioMedia: 0.1, indicioAlta: 0.1 });
  for (const clave of CLAVES) assert.ok(ESTILOS.claro[clave].normal.linea && ESTILOS.oscuro[clave].seleccionado.halo, clave);
  const primero = estilo("indicioAlta", "hover", "oscuro");
  primero.linea.weight = 999;
  primero.halo.color = "rojo";
  const segundo = estilo("indicioAlta", "hover", "oscuro");
  assert.notEqual(segundo.linea.weight, 999);
  assert.notEqual(segundo.halo.color, "rojo");
  assert.equal(BASE.oscuro.indicioAlta.weight, 9);
});

test("H165 CA7: un polígono lleva halo sin relleno y línea con relleno tenue; las líneas, sin relleno", () => {
  const { mapa, reg } = mapaReal();
  const multi = { type: "MultiPolygon", coordinates: [cuadro.coordinates, cuadro.coordinates] };
  const multiLinea = { type: "MultiLineString", coordinates: [SEGMENTO, [[-3.3, 40.08], [-3.29, 40.09]]] };
  const trazados = dibujar(mapa, reg, "vias_pecuarias", coleccionDe(feat(cuadro), feat(multi), feat(lineaDe(SEGMENTO)), feat(multiLinea)), { clave: "viasPecuarias", orden: 10 });
  const [pol, mpol, lin, mlin] = trazados;
  for (const t of [pol, mpol]) {
    const normal = t.linea.ultimoEstilo;
    assert.equal(t.halo.ultimoEstilo.fill, false);
    assert.equal(normal.fill, true);
    assert.equal(normal.fillColor, normal.color);
    assert.equal(normal.fillOpacity, RELLENO.viasPecuarias);
    t.linea.disparar("mouseover");
    assert.equal(t.linea.ultimoEstilo.fillOpacity, RELLENO.viasPecuarias + 0.1);
    assert.equal(t.halo.ultimoEstilo.fill, false);
    t.linea.disparar("mouseout");
    t.linea.disparar("click");
    assert.equal(t.linea.ultimoEstilo.fillOpacity, RELLENO.viasPecuarias + 0.1);
    assert.equal(t.linea.ultimoEstilo.fill, true);
    assert.equal(t.halo.ultimoEstilo.fill, false);
  }
  for (const t of [lin, mlin]) {
    assert.equal(t.linea.ultimoEstilo.fill, false);
    assert.equal(t.halo.ultimoEstilo.fill, false);
  }
  // Un MultiPolygon de dos partes es un solo trazado: un popup y una selección.
  assert.equal(mpol.linea.popups.length, 1);
  assert.equal(trazados.length, 4);
  mpol.linea.disparar("click");
  pol.linea.disparar("click");
  assert.equal(mpol.linea.ultimoEstilo.fillOpacity, RELLENO.viasPecuarias, "la anterior vuelve a normal");
  // Indicios de la misma forma.
  const ind = dibujar(mapa, reg, "discrepancias", coleccionDe(feat(cuadro, { confianza: "alta" })), { claveDe: () => "indicioAlta", orden: 40 });
  assert.equal(ind[0].linea.ultimoEstilo.fillOpacity, RELLENO.indicioAlta);
  assert.equal(ind[0].halo.ultimoEstilo.fill, false);
  // Una clave sin relleno (camino actual) nunca rellena.
  assert.equal(estiloTrazado("caminoActual", "normal", "claro", true).linea.fill, false);
});

test("H165 CA8: cada capa tiene su pane con zIndex 400 + orden, sea cual sea el orden de carga", () => {
  const { mapa, reg } = mapaReal();
  dibujar(mapa, reg, "camino_actual", coleccionDe(), { clave: "caminoActual", orden: 30 });
  dibujar(mapa, reg, "vias_pecuarias", coleccionDe(), { clave: "viasPecuarias", orden: 10 });
  dibujar(mapa, reg, "discrepancias", coleccionDe(), { claveDe: () => "indicioBaja", orden: 40 });
  const z = (id) => Number(reg.panes["pc-capa-" + id].style.zIndex);
  assert.equal(reg.panes["pc-capa-vias_pecuarias"].style.zIndex, "410");
  assert.equal(z("camino_actual"), 430);
  assert.equal(z("discrepancias"), 440);
  assert.ok(z("vias_pecuarias") < z("camino_actual") && z("camino_actual") < z("discrepancias"));
  for (const capa of reg.geojsons) assert.ok(capa.opciones.pane.startsWith("pc-capa-"));
  assert.deepEqual(CONFIG.capas.map((c) => [c.id, c.orden]), [["vias_pecuarias", 10], ["camino_actual", 30], ["discrepancias", 40]]);
  // Volver a dibujar una capa reutiliza su pane.
  const antes = reg.panes["pc-capa-camino_actual"];
  dibujar(mapa, reg, "camino_actual", coleccionDe(), { clave: "caminoActual", orden: 30 });
  assert.equal(reg.panes["pc-capa-camino_actual"], antes);
});

test("H165 CA9: quitar una capa suelta la selección; ponerTema reestila todo y conserva la selección", () => {
  const { mapa, reg } = mapaReal();
  const [a] = dibujar(mapa, reg, "vias_pecuarias", coleccionDe(feat(cuadro)), { clave: "viasPecuarias", orden: 10 });
  a.linea.disparar("click");
  mapa.quitarCapa("vias_pecuarias");
  const llamadas = a.linea.estilos.length + a.halo.estilos.length;
  const [b] = dibujar(mapa, reg, "vias_pecuarias", coleccionDe(feat(cuadro)), { clave: "viasPecuarias", orden: 10 });
  b.linea.disparar("click");
  assert.equal(a.linea.estilos.length + a.halo.estilos.length, llamadas, "no se restaura el trazado quitado");
  assert.deepEqual(b.linea.ultimoEstilo, estiloTrazado("viasPecuarias", "seleccionado", "claro", true).linea);

  const [c] = dibujar(mapa, reg, "camino_actual", coleccionDe(feat(lineaDe(SEGMENTO))), { clave: "caminoActual", orden: 30 });
  mapa.ponerTema("oscuro");
  assert.deepEqual(b.linea.ultimoEstilo, estiloTrazado("viasPecuarias", "seleccionado", "oscuro", true).linea, "sigue seleccionado");
  assert.equal(b.halo.ultimoEstilo.color, BASE.seleccionHalo.oscuro);
  assert.deepEqual(c.linea.ultimoEstilo, estiloTrazado("caminoActual", "normal", "oscuro", false).linea);
  assert.deepEqual(c.halo.ultimoEstilo, estiloTrazado("caminoActual", "normal", "oscuro", false).halo);
  // Una capa añadida después usa el tema vigente.
  const [d] = dibujar(mapa, reg, "discrepancias", coleccionDe(feat(cuadro, { confianza: "media" })), { claveDe: () => "indicioMedia", orden: 40 });
  assert.equal(d.linea.ultimoEstilo.color, BASE.oscuro.indicioMedia.color);
});

test("H165 CA10: temaDe — el forzado gana; si no, la preferencia del sistema", () => {
  assert.equal(temaDe("claro", true), "claro");
  assert.equal(temaDe("oscuro", false), "oscuro");
  assert.equal(temaDe(null, true), "oscuro");
  assert.equal(temaDe(undefined, false), "claro");
  assert.equal(temaDe("otro", true), "oscuro");
  assert.equal(temaDe("", false), "claro");
});

test("H165 CA10: crearMapa recibe el tema inicial", () => {
  const { mapa, reg } = mapaReal({ tema: "oscuro" });
  const [t] = dibujar(mapa, reg, "camino_actual", coleccionDe(feat(lineaDe(SEGMENTO))), { clave: "caminoActual" });
  assert.equal(t.linea.ultimoEstilo.color, BASE.oscuro.caminoActual.color);
});

test("H165 CA11: config.js sin colores y con claves del sistema de diseño", () => {
  assert.ok(!/#[0-9a-fA-F]{6}\b/.test(JSON.stringify(CONFIG.capas)));
  for (const capa of CONFIG.capas) {
    assert.equal(typeof capa.orden, "number");
    const e = capa.estilo;
    const nombradas = e.clave !== undefined ? [e.clave] : [...Object.values(e.claves), e.defecto];
    for (const clave of nombradas) assert.ok(CLAVES.includes(clave), clave);
  }
});
