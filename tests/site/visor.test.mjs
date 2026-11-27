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
const { crearControlador, validarIndice, fichaDe, atribucionesVisibles, filtrarMunicipios, normalizar } = controladorMod;
const { crearMapa, escaparTexto } = await importar("mapa.js");
const estilosMod = await importar("estilos-capas.js");
const { crearVista } = await importar("vista.js");
const { leerEnlace, escribirEnlace } = await importar("enlace.js");
const { fichaIndicio } = controladorMod;

const VIAS = CONFIG.capas.find((c) => c.id === "vias_pecuarias");
// Historia #185: las atribuciones del mapa base son las del fondo activo. Con un municipio
// abierto el fondo es la ortofoto, y la cobertura está dibujada.
const MAPA = CONFIG.fondos.find((f) => f.id === "mapa");
const ORTO = CONFIG.fondos.find((f) => f.id === "ortofoto");
const BASE_MUNICIPIO = [...ORTO.atribuciones, CONFIG.cobertura.atribucion];
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
    // Historia #185: fondo, selección, encuadre de un trazado y cobertura.
    ponerFondo(id) {
      r.fondos = [...(r.fondos ?? []), id];
    },
    seleccionar(capaId, id) {
      r.selecciones = [...(r.selecciones ?? []), [capaId, id]];
      return true;
    },
    deseleccionar() {
      r.deselecciones = (r.deselecciones ?? 0) + 1;
    },
    encuadrarRasgo(capaId, id) {
      r.encuadresRasgo = [...(r.encuadresRasgo ?? []), [capaId, id]];
    },
    ponerCobertura(geojson, opciones) {
      r.cobertura = { geojson, opciones };
    },
    resaltarMunicipio(ine) {
      r.resaltados = [...(r.resaltados ?? []), ine];
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
    resumenes: {},
    ponerResumenCapa(id, resumen) {
      v.resumenes[id] = resumen;
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
    // Historia #185: la ficha va a un panel; el doble guarda el modelo abierto.
    fichas: [],
    ficha: null,
    abrirFicha(modelo) {
      v.ficha = modelo;
      v.fichas.push(modelo);
    },
    cerrarFicha() {
      v.ficha = null;
    },
    recuentos: {},
    ponerRecuentoCapa(id, n) {
      v.recuentos[id] = n;
    },
    marcadas: {},
    marcarCapa(id, visible) {
      v.marcadas[id] = visible;
    },
    ponerFondo(id) {
      v.fondo = id;
    },
    ponerResumenCobertura(texto) {
      v.resumenCobertura = texto;
    },
    nodoEtiquetaHito(texto) {
      return { etiqueta: texto };
    },
  };
  return v;
}

// Desde #185 el visor abre en la vista de España; los tests que parten de un municipio
// abierto eligen el primero del índice, como hacía antes `iniciar()`.
async function iniciado(cargarJson = cargarJsonFixture) {
  const mapa = crearMapaDoble();
  const vista = crearVistaDoble();
  const ctl = crearControlador({ mapa, cargarJson, vista, config: CONFIG });
  await ctl.iniciar();
  if (ctl.estado.municipios.length > 0) await ctl.elegirMunicipio(ctl.estado.municipios[0].ine);
  return { mapa, vista, ctl };
}

// Pulsa el trazado `i` de la capa `id` en el doble del mapa: abre su ficha en la vista doble.
function pulsar(mapa, id, i = 0) {
  const anadida = mapa.r.anadidas.filter((a) => a.id === id).at(-1);
  const feature = anadida.geojson.features[i];
  anadida.opciones.alPulsar(feature.properties ?? {}, feature.id === undefined ? null : String(feature.id));
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
  getAttribute(nombre) {
    return this.atributos?.[nombre] ?? null;
  }
  removeAttribute(nombre) {
    if (this.atributos) delete this.atributos[nombre];
  }
  addEventListener(tipo, f) {
    this.oyentes = { ...(this.oyentes ?? {}), [tipo]: f };
  }
  disparar(tipo) {
    this.oyentes?.[tipo]?.();
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
  const capas = ["vias_pecuarias", "camino_actual", "discrepancias", "candidatos"];
  for (const id of [
    "mensaje", "aviso-base", "resumen-candidatos",
    // Historia #185: buscador, ámbito, ficha en panel, hoja móvil y aviso flotante.
    "buscar", "sugerencias", "ambito-nombre", "ambito-resumen", "ver-espana", "plegar",
    "ficha", "ficha-tipo", "ficha-titulo", "ficha-cuerpo", "ficha-ampliar", "aviso-flotante",
    "fondo-mapa", "fondo-ortofoto",
    ...capas.flatMap((c) => [`estado-${c}`, `recuento-${c}`, `capa-${c}`]),
  ]) {
    elementos[id] = new ElementoFalso("div");
  }
  return {
    elementos,
    getElementById: (id) => elementos[id] ?? null,
    createElement: (tag) => new ElementoFalso(tag),
    createElementNS: (ns, tag) => {
      const e = new ElementoFalso(tag);
      e.espacio = ns;
      return e;
    },
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
    setStyle(estilo) {
      this.estilos = [...(this.estilos ?? []), estilo];
      return this;
    }
  }
  globalThis.L = {
    DomEvent: { stopPropagation() {} },
    marker(centro, opciones) {
      const capa = new Capa("marker", centro, opciones);
      reg.marcadores = [...(reg.marcadores ?? []), capa];
      return capa;
    },
    divIcon(opciones) {
      return { divIcon: opciones };
    },
    map(contenedor, opciones) {
      const presentes = new Set();
      const m = {
        contenedor,
        opciones,
        presentes,
        vistas: [],
        encuadres: [],
        eventos: {},
        zoom: 6,
        on(evento, fn) {
          m.eventos[evento] = fn;
          return m;
        },
        getZoom: () => m.zoom,
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
        fitBounds(b, opcionesEncuadre) {
          m.encuadres.push(b);
          m.opcionesEncuadres = [...(m.opcionesEncuadres ?? []), opcionesEncuadre];
          return m;
        },
      };
      reg.mapas.push(m);
      return m;
    },
    control: {
      zoom(opciones) {
        return { opciones, addTo() { return this; } };
      },
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
      // Un Feature suelto (el velo de la cobertura, #185) es una colección de uno.
      const features = geojson.type === "Feature" ? [geojson] : geojson.features;
      for (const feature of features) {
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
          getBounds() {
            return { rasgo: feature.id };
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
    fondos: CONFIG.fondos,
    fondoInicial: CONFIG.fondoInicial,
    encuadreInicial: CONFIG.espana,
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

test("CA2: vista.js llena las sugerencias del buscador con una opción por municipio, por textContent", () => {
  const doc = documentoFalso();
  const vista = crearVista(doc, CONFIG.textos);
  vista.ponerMunicipios(INDICE.municipios.map((m) => ({ ine: m.ine, nombre: m.nombre })));
  // Historia #185: el selector es un buscador (combobox) cuyas sugerencias son opciones ARIA.
  vista.mostrarSugerencias(INDICE.municipios.map((m) => ({ ine: m.ine, nombre: m.nombre })));
  const opciones = doc.elementos.sugerencias.children;
  assert.deepEqual(
    opciones.map((o) => [o.tagName, o.getAttribute("role"), o.dataset.ine, o.textContent]),
    INDICE.municipios.map((m) => ["li", "option", m.ine, m.nombre]),
  );
  assert.equal(doc.elementos.buscar.getAttribute("aria-expanded"), "true");
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
  const base = [...BASE_MUNICIPIO];
  assert.deepEqual(ultima(mapa.r.atribuciones), [...base, VIAS.atribucion, CAMINO.atribucion]);
  ctl.cambiarCapa("vias_pecuarias", false);
  assert.deepEqual(ultima(mapa.r.atribuciones), [...base, CAMINO.atribucion]);
  ctl.cambiarCapa("camino_actual", false);
  assert.deepEqual(ultima(mapa.r.atribuciones), base);
  ctl.cambiarCapa("vias_pecuarias", true);
  assert.deepEqual(ultima(mapa.r.atribuciones), [...base, VIAS.atribucion]);
  // El fondo está siempre: el de la vista de España al arrancar, la ortofoto en un municipio.
  for (const lista of mapa.r.atribuciones) {
    const fondo = lista[0] === MAPA.atribuciones[0] ? MAPA : ORTO;
    assert.deepEqual(lista.slice(0, fondo.atribuciones.length), [...fondo.atribuciones], "el fondo está siempre");
  }
});

test("CA4: una capa que no carga no muestra su atribución", async () => {
  const { mapa, ctl } = await iniciado();
  await ctl.elegirMunicipio(C.ine); // vías pecuarias de C da 404
  assert.deepEqual(ultima(mapa.r.atribuciones), [...BASE_MUNICIPIO, CAMINO.atribucion]);
});

test("CA4: mapa.js sustituye la lista entera de atribuciones, sin prefijo de Leaflet", () => {
  const { mapa, control, m } = mapaReal();
  assert.equal(m.opciones.attributionControl, false);
  assert.deepEqual(control.opciones, { prefix: false, position: "bottomright" });
  assert.equal(control.mapa, m);
  // Antes de pedir teselas ya está la atribución del fondo inicial (#185: el mapa gris).
  assert.deepEqual(control.textos, [...MAPA.atribuciones]);
  mapa.ponerAtribuciones([...BASE_MUNICIPIO, VIAS.atribucion]);
  assert.deepEqual(control.textos, [...BASE_MUNICIPIO, VIAS.atribucion]);
  mapa.ponerAtribuciones([...BASE_MUNICIPIO]);
  assert.deepEqual(control.textos, [...BASE_MUNICIPIO]);
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

test("CA6: la ficha del controlador nunca lleva propietarios, refcat ni textos de corte", async () => {
  // Historia #185: sin popups; al pulsar, el controlador abre la ficha en el panel de la vista.
  const { mapa, vista } = await iniciado();
  for (const { id, opciones } of mapa.r.anadidas) {
    opciones.alPulsar(TRAMPA, null);
    const nodo = vista.ficha.ficha;
    const texto = JSON.stringify(vista.ficha);
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
  // Historia #185: la ficha de una vía pecuaria va al panel (nombre en el título).
  vista.abrirFicha({ tipo: "trazado", capaId: "vias_pecuarias", id: null, nombreCapa: VIAS.nombre, ficha: fichaDe(VIAS, TRAMPA), atribucion: VIAS.atribucion }); // innerHTML lanzaría
  const nodo = panelDe(doc);
  assert.ok(nodo.textContent.includes("<b>Cordel</b> de prueba"), "el marcado queda como texto");
  assert.ok(nodo.textContent.includes(VIAS.titulo));
  assert.ok(nodo.textContent.includes(VIAS.fuente));
  for (const prohibido of ["Persona Inventada", "99999A00100001", "cortado"]) {
    assert.ok(!nodo.textContent.includes(prohibido));
  }
});

test("CA6: mapa.js no abre popups: al pulsar llama a alPulsar con las propiedades y el id", () => {
  // Historia #185: la ficha va en un panel; mapa.js no inserta ningún contenido propio.
  const { mapa, reg } = mapaReal();
  const recibidas = [];
  mapa.anadirCapa("vias_pecuarias", {
    type: "FeatureCollection",
    features: [{ type: "Feature", id: "abc", properties: TRAMPA, geometry: null }],
  }, {
    clave: "viasPecuarias",
    alPulsar: (props, id) => recibidas.push([props, id]),
  });
  const sub = reg.geojsons[1].subcapas[0]; // [0] es el halo
  assert.equal(sub.popups.length, 0, "sin bindPopup");
  sub.disparar("click");
  assert.deepEqual(recibidas, [[TRAMPA, "abc"]]);
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
  // Historia #185: un fondo por entrada de config.js; arranca el de la vista de España.
  assert.deepEqual(reg.tiles.map((t) => t.datos), CONFIG.fondos.map((f) => f.url));
  const base = reg.tiles.find((t) => t.datos === MAPA.url);
  assert.ok(m.hasLayer(base));
  assert.ok(!m.hasLayer(reg.tiles.find((t) => t.datos === ORTO.url)));
  assert.equal(base.opciones.maxZoom, 19);
  assert.equal(base.opciones.minZoom, 5);
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

test("CA14: mapa.js da una única ficha por trazado multiparte, igual en todas sus partes", async () => {
  const { mapa, reg } = mapaReal();
  const vias = await leer(A.capas.vias_pecuarias);
  const fichas = [];
  mapa.anadirCapa("vias_pecuarias", vias, {
    clave: "viasPecuarias",
    alPulsar: (props) => fichas.push(fichaDe(VIAS, props)),
  });
  const capa = reg.geojsons[1]; // [0] es el halo, [1] la línea
  assert.equal(capa.datos, vias, "el GeoJSON llega sin trocear");
  assert.equal(capa.subcapas.length, vias.features.length, "una capa por trazado");
  const multi = capa.subcapas.find((s) => s.feature.geometry.type === "MultiPolygon");
  // Historia #185: sin popups; un solo layer y un solo clic para todas las partes.
  assert.equal(multi.popups.length, 0);
  multi.disparar("click");
  assert.deepEqual(fichas, [{
    titulo: VIAS.titulo,
    fuente: VIAS.fuente,
    nombre: "Vereda sintética multiparte",
  }]);
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
  // Solo el fondo de la vista de España: sin cobertura ni capas.
  assert.deepEqual(mapa.r.atribuciones, [[...MAPA.atribuciones]]);
});

test("unidad: una elección antigua que termina tarde no pisa la más reciente", async () => {
  const esperas = [];
  const cargar = (ruta) => {
    if (ruta.endsWith("indice.json")) return Promise.resolve(INDICE);
    if (ruta.endsWith("cobertura.geojson")) return cargarJsonFixture(ruta); // #185
    return new Promise((resolve, reject) => {
      esperas.push(() => cargarJsonFixture(ruta).then(resolve, reject));
    });
  };
  const mapa = crearMapaDoble();
  const vista = crearVistaDoble();
  const ctl = crearControlador({ mapa, cargarJson: cargar, vista, config: CONFIG });
  // Desde #185 `iniciar()` abre España; el enlace `?municipio=` hace que elija A.
  const inicio = ctl.iniciar({ municipio: A.ine }); // sus cargas quedan pendientes
  // Se espera a que A haya pedido sus dos capas (antes van el índice y la cobertura).
  for (let i = 0; i < 100 && esperas.length < 2; i += 1) await new Promise((r) => setImmediate(r));
  assert.equal(esperas.length, 2);
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
    fondo: "ortofoto",
    cobertura: false,
    capas: {
      vias_pecuarias: { cargada: true, visible: false },
      camino_actual: { cargada: false, visible: true },
    },
  };
  assert.deepEqual(atribucionesVisibles(CONFIG, estado), [...ORTO.atribuciones]);
  // Historia #185: con la cobertura dibujada se añade su atribución; el fondo manda la base.
  assert.deepEqual(
    atribucionesVisibles(CONFIG, { ...estado, fondo: "mapa", cobertura: true }),
    [...MAPA.atribuciones, CONFIG.cobertura.atribucion],
  );
});

test("unidad: crearMapa falla con un mensaje claro si la librería no está cargada", () => {
  delete globalThis.L;
  assert.throws(() => crearMapa("x", { fondos: CONFIG.fondos }), /no está cargada/);
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

// Historia #185: la ficha se pinta en un panel; su texto es el de la cabecera (tipo y título,
// con la etiqueta) y el del cuerpo. `panelDe` los junta en un nodo para leerlos en orden.
function panelDe(doc) {
  const panel = new ElementoFalso("aside");
  panel.children = ["ficha-tipo", "ficha-titulo", "ficha-cuerpo"].map((id) => doc.elementos[id]);
  return panel;
}

function nodoDe(propiedades, comparacion = null) {
  const doc = documentoFalso();
  const vista = crearVista(doc, CONFIG.textos);
  vista.abrirFicha({
    tipo: "indicio",
    capaId: "discrepancias",
    id: null,
    nombreCapa: "Indicio a verificar",
    ficha: fichaIndicio(propiedades, CONFIG),
    comparacion,
  });
  return panelDe(doc);
}

test("H95 CA1: la capa de indicios se carga del índice y se dibuja con estilo distinto", async () => {
  const { cargar, llamadas } = cargadorIndicios(coleccion(propsIndicio()));
  const { mapa, vista } = await iniciado(cargar);
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
  // La ficha de un indicio pulsado es la de indicios, no la genérica (#185: va al panel).
  dibujada.opciones.alPulsar(propsIndicio(), "0123456789abcdef");
  assert.equal(vista.ficha.tipo, "indicio");
  assert.equal(vista.ficha.ficha.disponible, true);
});

test("H95 CA2: nace apagada, sin atribución; al marcar y desmarcar aparece y desaparece", async () => {
  const { cargar } = cargadorIndicios(coleccion(propsIndicio()));
  const { mapa, ctl } = await iniciado(cargar);
  const base = [...BASE_MUNICIPIO];
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
  // #171 añade la clave `candidato`, que no existe en el sistema de diseño original: se compara
  // todo lo que el original define y se comprueba que `candidato` es lo único añadido.
  const sinPropia = (o) => Object.fromEntries(Object.entries(plano(o)).filter(([k]) => k !== "candidato"));
  const sinCandidato = (porTema) => Object.fromEntries(Object.entries(plano(porTema)).map(([t, v]) => [t, typeof v === "object" ? sinPropia(v) : v]));
  assert.deepEqual(sinCandidato(BASE), plano(original.BASE));
  assert.deepEqual(sinCandidato(ESTILOS), plano(original.ESTILOS));
  assert.deepEqual([...CLAVES].filter((c) => !(c in original.BASE.claro)), ["candidato"]);
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

test("H165 CA3: una sola selección en todo el mapa; mouseout no la suelta y cerrar la ficha sí", () => {
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
  // Historia #185: sin popups; cerrar la ficha llama a `deseleccionar`, que suelta la selección.
  mapa.deseleccionar();
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
  const mapa = crearMapa("contenedor", { fondos: CONFIG.fondos, tema: "claro" });
  const { cargar } = cargadorIndicios(indiciosConConfianzas());
  const doc = documentoFalso();
  const vista = crearVista(doc, CONFIG.textos);
  const ctl = crearControlador({ mapa, cargarJson: cargar, vista, config: CONFIG });
  await ctl.iniciar({ municipio: INDICE.municipios[0].ine });
  // Historia #185: antes de las capas, la cobertura dibuja tres GeoJSON (velo, halo y bordes).
  const trazados = reg.geojsons.filter((g) => !String(g.opciones.pane).startsWith("pc-cobertura"));
  assert.equal(trazados.length, 6, "tres capas, dos dibujos cada una");
  const [viasH, viasL, camH, camL, indH, indL] = trazados;

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
  // Historia #185: en el panel de la ficha, no en un popup.
  assert.equal(indL.subcapas[0].popups.length, 0);
  indL.subcapas[0].disparar("click");
  const cuerpo = doc.elementos["ficha-cuerpo"];
  assert.equal(cuerpo.children.length, 1);
  assert.ok(cuerpo.children[0].children.length > 0);
  assert.equal(doc.elementos.ficha.getAttribute("hidden"), null, "el panel se abre");
  viasL.subcapas[0].disparar("click");
  assert.equal(typeof doc.elementos["ficha-cuerpo"].children[0], "object");
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
  assert.deepEqual([...CLAVES], ["viasPecuarias", "caminoActual", "trazadoHistorico", "indicioBaja", "indicioMedia", "indicioAlta", "candidato"]);
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
  // Un MultiPolygon de dos partes es un solo trazado: un clic y una selección (#185: sin popup).
  assert.equal(typeof mpol.linea.eventos.click, "function");
  assert.equal(mpol.linea.popups.length, 0);
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
  assert.deepEqual(CONFIG.capas.map((c) => [c.id, c.orden]), [["vias_pecuarias", 10], ["camino_actual", 30], ["discrepancias", 40], ["candidatos", 50]]);
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

// --- Historia #166: estados de capa en el panel ------------------------------------------

test("H166 CA4: en carga, una barra aria-hidden y el texto; textContent es el de config.js", () => {
  const doc = documentoFalso();
  const vista = crearVista(doc, CONFIG.textos);
  vista.ponerEstadoCapa("vias_pecuarias", "cargando");
  const el = doc.elementos["estado-vias_pecuarias"];
  assert.equal(el.dataset.estado, "cargando");
  assert.equal(el.textContent, CONFIG.textos.cargando);
  assert.equal(el.textContent, "cargando…");
  assert.equal(el.children.length, 2);
  const [barra, texto] = el.children;
  assert.equal(barra.className, "pc-progreso");
  assert.equal(barra.atributos["aria-hidden"], "true");
  assert.equal(barra.children.length, 1);
  assert.equal(barra.children[0].tagName, "i");
  assert.equal(texto.tagName, "span");
});

test("H166 CA4: vacía y error llevan solo el texto, sin barra, y el estado anterior se limpia", () => {
  const doc = documentoFalso();
  const vista = crearVista(doc, CONFIG.textos);
  vista.ponerEstadoCapa("vias_pecuarias", "cargando");
  vista.ponerEstadoCapa("vias_pecuarias", "vacia");
  const el = doc.elementos["estado-vias_pecuarias"];
  assert.equal(el.dataset.estado, "vacia");
  assert.equal(el.textContent, CONFIG.textos.sinTrazados);
  assert.ok(el.children.every((c) => c.className !== "pc-progreso"));
  vista.ponerEstadoCapa("vias_pecuarias", "error");
  assert.equal(el.dataset.estado, "error");
  assert.equal(el.textContent, CONFIG.textos.errorCapa);
  assert.equal(el.children.length, 1);
  vista.ponerEstadoCapa("discrepancias", "sin_indicios");
  assert.equal(doc.elementos["estado-discrepancias"].textContent, CONFIG.textos.sinIndicios);
  vista.ponerEstadoCapa("vias_pecuarias", "ok");
  assert.equal(el.textContent, "");
  assert.equal(el.children.length, 0);
  assert.equal(el.dataset.estado, "ok");
});

test("H166 CA4: el error de una capa deja las otras dibujadas y en ok", async () => {
  const cargar = async (ruta) =>
    ruta.endsWith("indice.json") ? INDICE : ruta.includes("vias_pecuarias") ? { type: "Feature" } : cargarJsonFixture(ruta);
  const { mapa, vista } = await iniciado(cargar);
  assert.equal(vista.estados.vias_pecuarias, "error");
  assert.equal(vista.estados.camino_actual, "ok");
  assert.ok(mapa.r.anadidas.some((a) => a.id === "camino_actual"));
  assert.ok(!mapa.r.anadidas.some((a) => a.id === "vias_pecuarias"));
});

// --- Historia #171: tramos a verificar (capa `candidatos`) ------------------------------------
// Nombres «H171 CA<n>:». Fixture sintética generada con el sink de #170 (tests/fixtures/site).

const CANDIDATOS = CONFIG.capas.find((c) => c.id === "candidatos");
const RUTA_CAND = "candidatos/99001.geojson";
const PUBLICADO = JSON.parse(await readFile(process.env.VISOR_CANDIDATOS, "utf8"));
const copia = (x) => JSON.parse(JSON.stringify(x));
const TODAS = ["camino_actual", "vias_pecuarias"];

function cargadorCandidatos(respuesta, { enIndice = true } = {}) {
  const llamadas = [];
  const cargar = async (ruta) => {
    llamadas.push(ruta);
    if (ruta.endsWith("indice.json")) {
      return {
        municipios: INDICE.municipios.map((m, i) =>
          i === 0 && enIndice ? { ...m, capas: { ...m.capas, candidatos: RUTA_CAND } } : m,
        ),
      };
    }
    if (ruta.endsWith(RUTA_CAND)) {
      if (respuesta instanceof Error) throw respuesta;
      return respuesta;
    }
    return cargarJsonFixture(ruta);
  };
  return { cargar, llamadas };
}

const nodoCand = (propiedades) => nodoDe(propiedades);

test("H171 CA1: la capa está en el panel con su título, apagada, y su atribución solo si activa y cargada", async () => {
  assert.equal(CANDIDATOS.titulo, "Tramos a verificar (no son un dictamen)");
  assert.equal(CANDIDATOS.visibleInicial, false);
  const { cargar, llamadas } = cargadorCandidatos(copia(PUBLICADO));
  const { mapa, ctl } = await iniciado(cargar);
  assert.ok(llamadas.includes(CONFIG.datos + RUTA_CAND));
  assert.equal(mapa.presentes.get("candidatos"), false, "dibujada pero apagada");
  const base = [...BASE_MUNICIPIO, VIAS.atribucion, CAMINO.atribucion];
  assert.deepEqual(ultima(mapa.r.atribuciones), base);
  ctl.cambiarCapa("candidatos", true);
  assert.deepEqual(ultima(mapa.r.atribuciones), [...base, CANDIDATOS.atribucion]);
  ctl.cambiarCapa("candidatos", false);
  assert.deepEqual(ultima(mapa.r.atribuciones), base);
  // Activa pero sin cargar (municipio sin la capa): no aporta atribución.
  const sin = cargadorCandidatos(copia(PUBLICADO), { enIndice: false });
  const r = await iniciado(sin.cargar);
  r.ctl.cambiarCapa("candidatos", true);
  assert.deepEqual(ultima(r.mapa.r.atribuciones), base);
});

test("H171 CA2: la ficha muestra etiqueta, texto, aviso, confianza y fuentes; nada fuera de la lista blanca", async () => {
  const { cargar } = cargadorCandidatos(copia(PUBLICADO));
  const { mapa, vista } = await iniciado(cargar);
  const dibujada = mapa.r.anadidas.find((a) => a.id === "candidatos");
  assert.deepEqual(
    dibujada.geojson.features.map((f) => f.geometry.type),
    ["LineString", "MultiLineString", "LineString"],
  );
  assert.equal(dibujada.opciones.clave, "candidato");
  assert.equal(dibujada.opciones.orden, 50);
  for (const f of PUBLICADO.features) {
    const trampa = { ...f.properties, id: f.id, titular: "Persona Inventada", refcat: "99999A00100001" };
    dibujada.opciones.alPulsar(trampa, f.id);
    const ficha = vista.ficha.ficha; // #185: el modelo que el controlador manda al panel
    assert.equal(ficha.disponible, true);
    const t = nodoCand(trampa).textContent;
    const p = f.properties;
    const orden = [p.etiqueta, p.texto, `confianza ${p.confianza}`, p.aviso, `${p.evidencia[0].papel}: ${p.evidencia[0].fuente}`].map((s) => t.indexOf(s));
    assert.ok(orden.every((i) => i >= 0), JSON.stringify(orden));
    assert.deepEqual(orden, [...orden].sort((a, b) => a - b));
    for (const e of p.evidencia) {
      for (const s of [e.papel, e.fuente, e.fecha_descarga, e.licencia, e.atribucion]) assert.ok(t.includes(s), s);
      assert.ok(t.includes("año no declarado"), "anio null");
    }
    assert.ok(t.includes("Dirección General del Catastro"), "el Catastro va atribuido");
    for (const prohibido of [f.id, "Persona Inventada", "99999A00100001", "Criterio:"]) {
      assert.ok(!t.includes(prohibido), prohibido);
    }
    assert.ok(!JSON.stringify(ficha).includes(f.id));
    assert.deepEqual(Object.keys(ficha).sort(), [
      "aviso", "avisoOmision", "confianza", "criterio", "descripcionCriterio",
      "disponible", "etiqueta", "evidencia", "texto",
    ]);
    const a = enlaces(nodoCand(trampa));
    assert.equal(a.length, p.evidencia.length, "las URL https son enlaces");
  }
  // Sin aviso en el feature se usa el fijo de config.js.
  const { aviso: _quitado, ...sinAviso } = PUBLICADO.features[0].properties;
  assert.equal(fichaIndicio(sinAviso, CONFIG).aviso, CONFIG.textos.avisoIndicio);
  // Una URL no https no es enlace.
  const ev = { ...PUBLICADO.features[0].properties.evidencia[0], url: "http://ejemplo.invalid/x" };
  assert.equal(enlaces(nodoCand({ ...PUBLICADO.features[0].properties, evidencia: [ev] })).length, 0);
});

test("H171 CA3: el resumen muestra las cuatro frases y «revisado a mano» tal cual, en orden", async () => {
  const { cargar } = cargadorCandidatos(copia(PUBLICADO));
  const { vista } = await iniciado(cargar);
  assert.deepEqual(vista.resumenes.candidatos, {
    frases: PUBLICADO.properties.medicion.texto,
    revisadoAMano: PUBLICADO.properties.revisado_a_mano,
  });
  // Una fixture con frases distintas se ve igual: el visor no recalcula nada.
  const otro = copia(PUBLICADO);
  otro.properties.medicion.texto = ["Uno <b>x</b>.", "Dos 99 %.", "Tres.", "Cuatro 1/1."];
  otro.properties.medicion.cobertura = "0 %"; // cifras que NO deben usarse
  otro.properties.revisado_a_mano = "Marca distinta.";
  const r = await iniciado(cargadorCandidatos(otro).cargar);
  assert.deepEqual(r.vista.resumenes.candidatos, { frases: otro.properties.medicion.texto, revisadoAMano: "Marca distinta." });
  // La vista real las pone con textContent y en orden.
  const doc = documentoFalso();
  const vista2 = crearVista(doc, CONFIG.textos);
  vista2.ponerResumenCapa("candidatos", r.vista.resumenes.candidatos);
  const cont = doc.elementos["resumen-candidatos"];
  assert.deepEqual(cont.children.map((c) => c.textContent), [...otro.properties.medicion.texto, "Marca distinta."]);
  assert.ok(cont.children.every((c) => c.tagName === "p"));
  vista2.ponerResumenCapa("candidatos", null);
  assert.equal(cont.children.length, 0);
});

test("H171 CA4: fichero roto o sin medición da error de esa capa, sin tramos y sin resumen; las demás siguen", async () => {
  const sinMedicion = copia(PUBLICADO);
  delete sinMedicion.properties.medicion;
  const treintas = copia(PUBLICADO);
  treintas.properties.medicion.texto = treintas.properties.medicion.texto.slice(0, 3);
  const vacia = copia(PUBLICADO);
  vacia.properties.medicion.texto[2] = "  ";
  const sinMarca = copia(PUBLICADO);
  sinMarca.properties.revisado_a_mano = "";
  const sinProps = copia(PUBLICADO);
  delete sinProps.properties;
  const noCadena = copia(PUBLICADO);
  noCadena.properties.medicion.texto[0] = 4;
  const rotas = [new Error("HTTP 404"), { type: "Feature" }, null, sinMedicion, treintas, vacia, sinMarca, sinProps, noCadena];
  for (const respuesta of rotas) {
    const { mapa, vista } = await iniciado(cargadorCandidatos(respuesta).cargar);
    assert.equal(vista.estados.candidatos, "error");
    assert.ok(vista.mensaje.includes(CANDIDATOS.titulo), vista.mensaje);
    assert.equal(vista.resumenes.candidatos ?? null, null, "sin resumen");
    assert.deepEqual(mapa.r.anadidas.map((a) => a.id).sort(), TODAS, "ningún tramo");
  }
  assert.throws(() => resumenMedicionDe({}), /medición/);
});

const resumenMedicionDe = controladorMod.resumenMedicion;

test("H171 CA5: un municipio sin la capa en el índice dice «sin tramos a verificar publicados», sin error ni petición", async () => {
  const { cargar, llamadas } = cargadorCandidatos(copia(PUBLICADO), { enIndice: false });
  const { mapa, vista } = await iniciado(cargar);
  assert.equal(vista.estados.candidatos, "sin_candidatos");
  assert.equal(vista.mensaje, "");
  assert.ok(!llamadas.some((r) => r.includes("candidatos")));
  assert.deepEqual(mapa.r.anadidas.map((a) => a.id).sort(), TODAS);
  const doc = documentoFalso();
  crearVista(doc, CONFIG.textos).ponerEstadoCapa("candidatos", "sin_candidatos");
  assert.equal(doc.elementos["estado-candidatos"].textContent, "sin tramos a verificar publicados");
  assert.equal(CONFIG.textos.sinCandidatos, "sin tramos a verificar publicados");
});

test("H171 CA6: un fichero con cero tramos muestra el mismo estado vacío y no muestra el resumen", async () => {
  const vacio = copia(PUBLICADO);
  vacio.features = [];
  const { mapa, vista } = await iniciado(cargadorCandidatos(vacio).cargar);
  assert.equal(vista.estados.candidatos, "sin_candidatos");
  assert.equal(vista.mensaje, "");
  assert.equal(vista.resumenes.candidatos, null);
  assert.ok(!mapa.r.anadidas.some((a) => a.id === "candidatos"));
});

test("H171: al cambiar de municipio se quita la capa y el resumen", async () => {
  const { cargar } = cargadorCandidatos(copia(PUBLICADO));
  const { mapa, vista, ctl } = await iniciado(cargar);
  assert.ok(vista.resumenes.candidatos);
  await ctl.elegirMunicipio(B.ine);
  assert.equal(vista.resumenes.candidatos, null);
  assert.equal(mapa.presentes.has("candidatos"), false);
  assert.equal(vista.estados.candidatos, "sin_candidatos");
});

test("H171 CA7: la clave candidato se distingue de las demás, con tema oscuro, halo y orden por encima de los indicios", () => {
  assert.ok(CLAVES.includes("candidato"));
  assert.equal(CANDIDATOS.estilo.clave, "candidato");
  const n = (clave, tema = "claro") => estilo(clave, "normal", tema);
  const mio = n("candidato");
  const otras = ["viasPecuarias", "caminoActual", "indicioBaja", "indicioMedia", "indicioAlta"];
  for (const clave of otras) {
    const o = n(clave);
    assert.ok(o.linea.color !== mio.linea.color && o.linea.dashArray !== mio.linea.dashArray, clave);
  }
  assert.ok(mio.linea.dashArray, "con patrón, no solo color");
  assert.notEqual(n("candidato", "oscuro").linea.color, mio.linea.color);
  assert.ok(mio.halo.weight > mio.linea.weight && mio.halo.opacity > 0);
  assert.equal(mio.halo.dashArray, mio.linea.dashArray);
  assert.ok(CANDIDATOS.orden > INDICIOS.orden);
  const { mapa, reg } = mapaReal();
  dibujar(mapa, reg, "discrepancias", coleccionDe(), { clave: "indicioBaja", orden: INDICIOS.orden });
  dibujar(mapa, reg, "candidatos", copia(PUBLICADO), { clave: "candidato", orden: CANDIDATOS.orden });
  assert.ok(Number(reg.panes["pc-capa-candidatos"].style.zIndex) > Number(reg.panes["pc-capa-discrepancias"].style.zIndex));
});

test("H171 CA7: MultiLineString es un solo trazado con un único clic", () => {
  const { mapa, reg } = mapaReal();
  const trazados = dibujar(mapa, reg, "candidatos", copia(PUBLICADO), { clave: "candidato", orden: 50 });
  assert.equal(trazados.length, 3);
  assert.equal(typeof trazados[1].linea.eventos.click, "function");
  assert.equal(trazados[1].linea.popups.length, 0);
  assert.equal(trazados[1].linea.ultimoEstilo.fill, false);
});

test("H171 CA8: ningún texto del visor ni de la fixture lleva palabras vetadas ni referencias catastrales", () => {
  const vetadas = JSON.parse(process.env.VISOR_BANNED_WORDS ?? "[]");
  assert.ok(vetadas.length > 0, "la lista de palabras vetadas no está vacía");
  const textos = [
    CANDIDATOS.titulo, CANDIDATOS.fuente, CANDIDATOS.atribucion, CONFIG.textos.sinCandidatos,
    ...Object.values(PUBLICADO.properties).filter((v) => typeof v === "string"),
    ...PUBLICADO.properties.medicion.texto, ...PUBLICADO.properties.atribucion,
    ...PUBLICADO.features.map((f) => nodoCand(f.properties).textContent),
  ];
  for (const t of textos) {
    assert.ok(!REFCAT.test(t), t);
    for (const palabra of vetadas) assert.ok(!t.toLowerCase().includes(palabra), `${palabra}: ${t}`);
  }
});

// --- Historia #178: imágenes de comparación en la ficha (nombres «H178 CA<n>:») -------------

const PUBLICADO_IMG = JSON.parse(await readFile(process.env.VISOR_CANDIDATOS_IMG, "utf8"));
const CON_IMG = PUBLICADO_IMG.features[0].properties;
const SIN_IMG = PUBLICADO_IMG.features[1].properties;
const NOTAS = PUBLICADO_IMG.properties.comparacion;

// Ficha tal como la arma el controlador al pulsar un tramo del fichero publicado.
async function fichaPulsada(publicado, propiedades) {
  const { cargar } = cargadorCandidatos(copia(publicado));
  const mapa = crearMapaDoble();
  const doc = documentoFalso();
  const vista = crearVista(doc, CONFIG.textos);
  const ctl = crearControlador({ mapa, cargarJson: cargar, vista, config: CONFIG });
  await ctl.iniciar({ municipio: INDICE.municipios[0].ine });
  const dibujada = mapa.r.anadidas.find((a) => a.id === "candidatos");
  // Historia #185: la ficha se pinta en el panel; se devuelve su cuerpo.
  dibujada.opciones.alPulsar(propiedades, null);
  return doc.elementos["ficha-cuerpo"];
}
const porTag = (nodo, tag) => hijos(nodo).filter((h) => h.tagName === tag);
const porClase = (nodo, clase) => hijos(nodo).filter((h) => h.className === clase);

test("H178 CA1: imágenes en orden cronológico con periodo, atribución, lazy y URL publicada", async () => {
  // Se desordenan en la entrada para comprobar el orden cronológico.
  const props = copia(CON_IMG);
  props.imagenes_comparacion[0].imagenes.reverse();
  const ficha = await fichaPulsada(PUBLICADO_IMG, props);
  const imgs = porTag(ficha, "img");
  assert.equal(imgs.length, 2);
  assert.deepEqual(
    imgs.map((i) => i.atributos.src),
    CON_IMG.imagenes_comparacion[0].imagenes.map((i) => i.url),
  );
  for (const i of imgs) assert.equal(i.atributos.loading, "lazy");
  const texto = ficha.textContent;
  for (const i of CON_IMG.imagenes_comparacion[0].imagenes) {
    assert.ok(texto.includes(i.periodo), i.periodo);
    assert.ok(texto.includes(i.atribucion), i.atribucion);
    assert.ok(i.atribucion.startsWith("Obra derivada de "));
  }
  assert.ok(texto.indexOf("1997-1999") < texto.indexOf("2023"));
  assert.equal(imgs[0].atributos.alt, "Ortofoto de 1997-1999 con el tramo a verificar marcado");
});

test("H178 CA2: el trazo es un svg con viewBox y una polyline por parte, con createElementNS; se oculta con un control", async () => {
  const ficha = await fichaPulsada(PUBLICADO_IMG, copia(CON_IMG));
  // #185: la ficha también lleva la muestra de la confianza (otro svg); se cuentan los trazos.
  const svgs = porTag(ficha, "svg").filter((n) => n.atributos?.class === "pc-comparacion__trazo");
  assert.equal(svgs.length, 2);
  const [v] = CON_IMG.imagenes_comparacion;
  for (const svg of svgs) {
    assert.equal(svg.espacio, "http://www.w3.org/2000/svg");
    assert.equal(svg.atributos.viewBox, `0 0 ${v.ancho_px} ${v.alto_px}`);
    const lineas = porTag(svg, "polyline");
    assert.equal(lineas.length, v.trazo_px.length);
    assert.equal(lineas[0].espacio, "http://www.w3.org/2000/svg");
    assert.equal(lineas[0].atributos.points, "120,320 520,320");
    assert.equal(lineas[1].atributos.points, "520,330 560,400");
  }
  const [control] = porTag(ficha, "button").filter((b) => b.atributos?.["aria-pressed"] !== undefined);
  assert.equal(control.atributos.type, "button");
  assert.equal(control.atributos["aria-pressed"], "true");
  assert.ok(control.textContent.length > 0, "tiene nombre accesible");
  control.disparar("click");
  assert.equal(control.atributos["aria-pressed"], "false");
  for (const svg of svgs) assert.equal(svg.atributos.hidden, "");
  control.disparar("click");
  for (const svg of svgs) assert.equal(svg.atributos.hidden, undefined);
});

test("H178 CA2: el documento falso prohíbe innerHTML y la vista no lo usa", async () => {
  const fuente = await readFile(join(VISOR_DIR, "vista.js"), "utf8");
  assert.ok(!/innerHTML|outerHTML|insertAdjacentHTML/.test(fuente.replace(/\/\/.*$/gm, "")));
  assert.ok(fuente.includes("createElementNS"));
});

test("H178 CA3: una imagen que falla dice «imagen no disponible», conserva la atribución y el resto de la ficha", async () => {
  const ficha = await fichaPulsada(PUBLICADO_IMG, copia(CON_IMG));
  const [primera] = porTag(ficha, "img");
  primera.disparar("error");
  const lienzos = porClase(ficha, "pc-comparacion__lienzo");
  assert.equal(lienzos[0].textContent, NOTAS.no_disponible);
  assert.equal(porTag(lienzos[0], "img").length, 0);
  assert.equal(porTag(lienzos[1], "img").length, 1, "la otra imagen sigue");
  const [figura] = porClase(ficha, "pc-comparacion__imagen");
  assert.ok(figura.textContent.includes(CON_IMG.imagenes_comparacion[0].imagenes[0].atribucion));
  assert.ok(ficha.textContent.includes(CON_IMG.texto), "el resto de la ficha sigue");
  assert.ok(ficha.textContent.includes(CON_IMG.aviso));
});

test("H178 CA3: una URL que no es https no se carga y se dice no disponible", async () => {
  const props = copia(CON_IMG);
  props.imagenes_comparacion[0].imagenes[0].url = "javascript:alert(1)";
  const ficha = await fichaPulsada(PUBLICADO_IMG, props);
  assert.equal(porTag(ficha, "img").length, 1);
  assert.ok(ficha.textContent.includes(NOTAS.no_disponible));
});

test("H178 CA4: huecos, franjas omitidas y nota de quién sirve las imágenes, con el texto publicado", async () => {
  const ficha = await fichaPulsada(PUBLICADO_IMG, copia(CON_IMG));
  const texto = ficha.textContent;
  assert.ok(texto.includes(NOTAS.huecos[0].texto));
  assert.ok(texto.includes("sin cobertura de ese vuelo"));
  assert.ok(texto.includes(CON_IMG.imagenes_comparacion[0].omitidas[0].franja));
  assert.ok(texto.includes(NOTAS.servidas_por));
  // Sin recomponer: un texto distinto en el fichero se ve igual.
  const otro = copia(PUBLICADO_IMG);
  otro.properties.comparacion.huecos[0].texto = "Texto de hueco distinto.";
  const props = copia(otro.features[0].properties);
  props.imagenes_comparacion[0].omitidas[0].texto = "Omitida distinta.";
  const f2 = await fichaPulsada(otro, props);
  assert.ok(f2.textContent.includes("Texto de hueco distinto."));
  assert.ok(f2.textContent.includes("Omitida distinta."));
});

test("H178 CA5: un tramo sin imagenes_comparacion, o con un campo roto, se ve como antes y sin error", async () => {
  // #185: se compara el cuerpo de la ficha (la cabecera lleva la etiqueta en los dos casos).
  const cuerpoDe = (props) => nodoDe(props).children[2];
  const antes = cuerpoDe(SIN_IMG).textContent;
  const ficha = await fichaPulsada(PUBLICADO_IMG, copia(SIN_IMG));
  assert.equal(ficha.textContent, antes);
  assert.equal(porTag(ficha, "img").length, 0);
  assert.equal(porTag(ficha, "button").filter((b) => b.atributos?.["aria-pressed"] !== undefined).length, 0);
  // Un fichero anterior a #172 (sin bloque `comparacion`) tampoco da error.
  const viejo = copia(PUBLICADO);
  assert.equal((await fichaPulsada(viejo, copia(viejo.features[0].properties))).textContent, cuerpoDe(viejo.features[0].properties).textContent);
  for (const roto of [null, {}, "x", [], [null], [{}], [{ ancho_px: 0, alto_px: 5, imagenes: [] }]]) {
    const p = { ...copia(SIN_IMG), imagenes_comparacion: roto };
    assert.equal((await fichaPulsada(PUBLICADO_IMG, p)).textContent, antes);
  }
});

test("H178 CA6: ningún texto nuevo del visor ni del fichero lleva palabras vetadas ni referencias catastrales", async () => {
  const vetadas = JSON.parse(process.env.VISOR_BANNED_WORDS ?? "[]");
  assert.ok(vetadas.length > 0);
  const ficha = await fichaPulsada(PUBLICADO_IMG, copia(CON_IMG));
  const textos = [
    CONFIG.textos.tituloComparacion, CONFIG.textos.mostrarTrazo, CONFIG.textos.imagenNoDisponible,
    ficha.textContent, JSON.stringify(PUBLICADO_IMG.properties.comparacion),
    JSON.stringify(CON_IMG.imagenes_comparacion),
  ];
  for (const t of textos) {
    assert.ok(!REFCAT.test(t), t);
    for (const palabra of vetadas) assert.ok(!t.toLowerCase().includes(palabra), `${palabra}: ${t}`);
  }
});

// --- Historia #185: rediseño del visor ------------------------------------------------------

const ID_A = "0123456789abcdef";
const ID_B = "fedcba9876543210";
const conIds = (col, ...ids) => ({ ...col, features: col.features.map((f, i) => ({ ...f, id: ids[i] })) });

test("H185 CA1: al arrancar sin enlace se ve España con el fondo gris, la cobertura y su resumen", async () => {
  const mapa = crearMapaDoble();
  const vista = crearVistaDoble();
  const ctl = crearControlador({ mapa, cargarJson: cargarJsonFixture, vista, config: CONFIG });
  await ctl.iniciar();
  assert.equal(ctl.estado.actual, null);
  assert.deepEqual(ultima(mapa.r.encuadres), CONFIG.espana);
  assert.equal(ultima(mapa.r.fondos), "mapa");
  assert.equal(mapa.r.anadidas.length, 0, "ninguna capa de trazados sin municipio");
  assert.equal(mapa.r.cobertura.geojson.features.length, INDICE.municipios.length);
  assert.deepEqual(mapa.r.cobertura.opciones.etiqueta, { etiqueta: `Primer hito · ${INDICE.municipios.length} municipios` });
  assert.equal(vista.resumenCobertura, CONFIG.textos.resumenCobertura.replace("{n}", String(INDICE.municipios.length)));
  for (const capa of CONFIG.capas) assert.equal(vista.estados[capa.id], "sin_municipio");
  assert.deepEqual(ultima(mapa.r.atribuciones), [...MAPA.atribuciones, CONFIG.cobertura.atribucion]);
});

test("H185 CA1: si la cobertura no carga, el visor sigue y lo dice sin error de capa", async () => {
  const cargar = (ruta) => (ruta.endsWith("cobertura.geojson") ? Promise.reject(new Error("404")) : cargarJsonFixture(ruta));
  const mapa = crearMapaDoble();
  const vista = crearVistaDoble();
  const ctl = crearControlador({ mapa, cargarJson: cargar, vista, config: CONFIG });
  await ctl.iniciar();
  assert.equal(vista.avisoBase, CONFIG.textos.errorCobertura);
  assert.equal(mapa.r.cobertura, undefined);
  assert.deepEqual(ultima(mapa.r.atribuciones), [...MAPA.atribuciones]);
  await ctl.elegirMunicipio(A.ine);
  assert.ok(mapa.r.anadidas.some((a) => a.id === "vias_pecuarias"));
});

test("H185 CA2: pulsar un municipio cubierto o la etiqueta del hito lo abre o lo encuadra", async () => {
  const mapa = crearMapaDoble();
  const vista = crearVistaDoble();
  const ctl = crearControlador({ mapa, cargarJson: cargarJsonFixture, vista, config: CONFIG });
  await ctl.iniciar();
  mapa.r.cobertura.opciones.alPulsarEtiqueta();
  const cajas = INDICE.municipios.map((m) => m.bbox);
  assert.deepEqual(ultima(mapa.r.encuadres), [
    Math.min(...cajas.map((b) => b[0])), Math.min(...cajas.map((b) => b[1])),
    Math.max(...cajas.map((b) => b[2])), Math.max(...cajas.map((b) => b[3])),
  ]);
  assert.equal(ctl.estado.actual, null, "la etiqueta no abre ningún municipio");
  await mapa.r.cobertura.opciones.alPulsarMunicipio(B.ine);
  assert.equal(ctl.estado.actual, B.ine);
  assert.deepEqual(ultima(mapa.r.encuadres), B.bbox);
  assert.equal(ultima(mapa.r.resaltados), B.ine);
  assert.equal(vista.seleccionado, B.ine);
});

test("H185 CA2: al entrar en un municipio pasa a ortofoto salvo que la persona haya elegido fondo", async () => {
  const { mapa, ctl } = await iniciado();
  assert.equal(ultima(mapa.r.fondos), "ortofoto");
  ctl.verEspana();
  assert.equal(ultima(mapa.r.fondos), "mapa");
  assert.deepEqual(ultima(mapa.r.encuadres), CONFIG.espana);
  assert.equal(mapa.r.anadidas.filter((a) => a.id === "vias_pecuarias").length, 1);
  assert.equal(ultima(mapa.r.resaltados), null);
  ctl.cambiarFondo("mapa");
  await ctl.elegirMunicipio(B.ine);
  assert.equal(ultima(mapa.r.fondos), "mapa", "la elección de la persona manda");
  assert.equal(ctl.estado.fondo, "mapa");
});

test("H185 CA2: el buscador encuentra sin tildes ni mayúsculas y solo municipios con datos", () => {
  const lista = [{ ine: "28052", nombre: "Chinchón" }, { ine: "28043", nombre: "Colmenar de Oreja" }, { ine: "28013", nombre: "Aranjuez" }];
  assert.equal(normalizar("  ChInChÓn "), "chinchon");
  assert.deepEqual(filtrarMunicipios(lista, "chin").map((m) => m.ine), ["28052"]);
  assert.deepEqual(filtrarMunicipios(lista, "OREJA").map((m) => m.ine), ["28043"]);
  assert.deepEqual(filtrarMunicipios(lista, "c").map((m) => m.ine), ["28052", "28043"], "primero los que empiezan");
  assert.deepEqual(filtrarMunicipios(lista, "").map((m) => m.ine), ["28052", "28043", "28013"]);
  assert.deepEqual(filtrarMunicipios(lista, "Madrid"), []);
});

test("H185 CA2: el buscador es un combobox accesible: flechas, Intro, Escape y aviso sin cobertura", () => {
  const doc = documentoFalso();
  const vista = crearVista(doc, CONFIG.textos);
  const elegidos = [];
  vista.conectar({ alElegirMunicipio: (ine) => elegidos.push(ine) });
  const lista = INDICE.municipios.map((m) => ({ ine: m.ine, nombre: m.nombre }));
  vista.mostrarSugerencias(lista);
  const tecla = (key) => vista.teclaBuscador({ key, preventDefault() {} });
  tecla("ArrowDown");
  tecla("ArrowDown");
  assert.equal(doc.elementos.buscar.getAttribute("aria-activedescendant"), `sugerencia-${B.ine}`);
  assert.equal(doc.elementos.sugerencias.children[1].getAttribute("aria-selected"), "true");
  tecla("Enter");
  assert.deepEqual(elegidos, [B.ine]);
  assert.equal(doc.elementos.buscar.value, B.nombre);
  assert.equal(doc.elementos.buscar.getAttribute("aria-expanded"), "false");
  assert.equal(doc.elementos.sugerencias.getAttribute("hidden"), "");
  vista.mostrarSugerencias([], "Aún sin cobertura.");
  assert.equal(doc.elementos.sugerencias.children[0].textContent, "Aún sin cobertura.");
  assert.equal(doc.elementos.sugerencias.children[0].getAttribute("role"), "presentation");
  tecla("Escape");
  assert.equal(doc.elementos.sugerencias.children.length, 0);
});

test("H185 CA3: pulsar un indicio abre su ficha en el panel; cerrarla suelta la selección y el enlace", async () => {
  const enlaces = [];
  const { cargar } = cargadorIndicios(conIds(coleccion(propsIndicio(), propsIndicio({ confianza: "alta" })), ID_A, ID_B));
  const mapa = crearMapaDoble();
  const vista = crearVistaDoble();
  const ctl = crearControlador({ mapa, cargarJson: cargar, vista, config: CONFIG, alCambiarEnlace: (e) => enlaces.push(e) });
  await ctl.iniciar({ municipio: A.ine });
  pulsar(mapa, "discrepancias", 1);
  assert.equal(vista.ficha.tipo, "indicio");
  assert.equal(vista.ficha.nombreCapa, INDICIOS.nombre);
  assert.equal(vista.ficha.ficha.confianza, "confianza alta");
  assert.deepEqual(ultima(enlaces), { municipio: A.ine, tramo: ID_B });
  ctl.cerrarFicha();
  assert.equal(vista.ficha, null);
  assert.equal(mapa.r.deselecciones, 1);
  assert.deepEqual(ultima(enlaces), { municipio: A.ine, tramo: null });
  // Una vía pecuaria abre su ficha corta y no pone tramo en el enlace.
  pulsar(mapa, "vias_pecuarias", 0);
  assert.equal(vista.ficha.tipo, "trazado");
  assert.equal(vista.ficha.atribucion, VIAS.atribucion);
  assert.deepEqual(ultima(enlaces), { municipio: A.ine, tramo: null });
  // Apagar la capa del trazado abierto cierra su ficha.
  ctl.cambiarCapa("vias_pecuarias", false);
  assert.equal(vista.ficha, null);
});

test("H185 CA3: la ficha pone primero el resumen y el aviso sin plegar; fuentes, imágenes y criterio se pliegan", () => {
  const panel = nodoDe(propsIndicio());
  const [tipo, titulo, cuerpo] = panel.children;
  assert.equal(tipo.textContent, "Indicio a verificar");
  assert.equal(titulo.textContent, "Trazado en una fuente y no en otra");
  const ficha = cuerpo.children[0];
  const etiquetas = ficha.children.map((n) => n.tagName);
  const plegables = ficha.children.filter((n) => n.tagName === "details");
  assert.deepEqual(plegables.map((d) => d.children[0].textContent), [`${CONFIG.textos.fuentes} (2)`, CONFIG.textos.comoSeCalcula]);
  const aviso = ficha.children.find((n) => n.className === "ficha-aviso");
  assert.equal(aviso.textContent, AVISO, "el aviso va fuera de todo plegable");
  assert.ok(etiquetas.indexOf("details") > ficha.children.indexOf(aviso));
  // Las URL https son enlaces con texto corto; la URL entera queda en href y title.
  const [enlace] = hijos(ficha).filter((h) => h.tagName === "a");
  assert.equal(enlace.textContent, CONFIG.textos.abrirConsulta);
  assert.equal(enlace.atributos.href, "https://ejemplo.invalid/a");
  assert.equal(enlace.atributos.title, "https://ejemplo.invalid/a");
  assert.equal(enlace.atributos.rel, "noopener noreferrer");
  // Ficha no disponible: el aviso sigue, sin plegables.
  const rota = nodoDe({}).children[2].children[0];
  assert.ok(rota.textContent.includes(AVISO));
  assert.equal(rota.children.filter((n) => n.tagName === "details").length, 0);
});

test("H185 CA3: los botones de la ficha acercan y copian el enlace; ampliar cambia aria-expanded", () => {
  const doc = documentoFalso();
  const vista = crearVista(doc, CONFIG.textos);
  const llamadas = [];
  vista.conectar({ alAcercar: () => llamadas.push("acercar"), alCopiarEnlace: () => llamadas.push("copiar") });
  vista.abrirFicha({ tipo: "indicio", capaId: "discrepancias", id: ID_A, nombreCapa: "Indicio a verificar", ficha: fichaIndicio(propsIndicio(), CONFIG), comparacion: null });
  const botones = hijos(doc.elementos["ficha-cuerpo"]).filter((h) => h.tagName === "button");
  assert.deepEqual(botones.map((b) => b.textContent), [CONFIG.textos.acercar, CONFIG.textos.copiarEnlace]);
  for (const b of botones) b.disparar("click");
  assert.deepEqual(llamadas, ["acercar", "copiar"]);
  vista.ampliarFicha(true);
  assert.equal(doc.elementos["ficha-ampliar"].getAttribute("aria-expanded"), "true");
  vista.cerrarFicha();
  assert.equal(doc.elementos.ficha.getAttribute("hidden"), "");
  assert.equal(doc.elementos["ficha-cuerpo"].children.length, 0);
});

test("H185 CA4: el enlace se lee y se escribe con municipio y tramo validados", () => {
  assert.deepEqual(leerEnlace("?municipio=28043&tramo=4bb7d47423d242f7"), { municipio: "28043", tramo: "4bb7d47423d242f7" });
  assert.deepEqual(leerEnlace(""), { municipio: null, tramo: null });
  assert.deepEqual(leerEnlace("?municipio=2804"), { municipio: null, tramo: null });
  assert.deepEqual(leerEnlace("?tramo=4bb7d47423d242f7"), { municipio: null, tramo: null }, "tramo sin municipio no vale");
  assert.deepEqual(leerEnlace("?municipio=28043&tramo=<script>"), { municipio: "28043", tramo: null });
  assert.equal(escribirEnlace({ municipio: "28043", tramo: "4bb7d47423d242f7" }), "?municipio=28043&tramo=4bb7d47423d242f7");
  assert.equal(escribirEnlace({ municipio: "28043", tramo: null }), "?municipio=28043");
  assert.equal(escribirEnlace({ municipio: null, tramo: "4bb7d47423d242f7" }), "");
  assert.equal(escribirEnlace(), "");
});

test("H185 CA4: un enlace con tramo abre el municipio, enciende su capa, lo selecciona y abre la ficha", async () => {
  const { cargar } = cargadorIndicios(conIds(coleccion(propsIndicio(), propsIndicio({ confianza: "alta" })), ID_A, ID_B));
  const mapa = crearMapaDoble();
  const vista = crearVistaDoble();
  const ctl = crearControlador({ mapa, cargarJson: cargar, vista, config: CONFIG });
  await ctl.iniciar({ municipio: A.ine, tramo: ID_B });
  assert.equal(ctl.estado.actual, A.ine);
  assert.equal(ctl.estado.capas.discrepancias.visible, true, "la capa nace apagada pero el enlace la enciende");
  assert.equal(vista.marcadas.discrepancias, true);
  assert.deepEqual(ultima(mapa.r.selecciones), ["discrepancias", ID_B]);
  assert.deepEqual(ultima(mapa.r.encuadresRasgo), ["discrepancias", ID_B]);
  assert.equal(vista.ficha.ficha.confianza, "confianza alta");
});

test("H185 CA4: un tramo que ya no está abre el municipio y lo dice; un municipio desconocido abre España", async () => {
  const { cargar } = cargadorIndicios(conIds(coleccion(propsIndicio()), ID_A));
  const mapa = crearMapaDoble();
  const vista = crearVistaDoble();
  const ctl = crearControlador({ mapa, cargarJson: cargar, vista, config: CONFIG });
  await ctl.iniciar({ municipio: A.ine, tramo: ID_B });
  assert.equal(ctl.estado.actual, A.ine);
  assert.equal(vista.ficha, null);
  assert.equal(vista.mensaje, CONFIG.textos.tramoNoPublicado);
  assert.equal(ctl.estado.capas.discrepancias.visible, false, "no se enciende nada");
  const otro = crearControlador({ mapa: crearMapaDoble(), cargarJson: cargarJsonFixture, vista: crearVistaDoble(), config: CONFIG });
  await otro.iniciar({ municipio: "99999" });
  assert.equal(otro.estado.actual, null);
});

test("H185: mapa.js dibuja el velo con un hueco por municipio, sus bordes y la etiqueta solo a escala pequeña", async () => {
  const { mapa, reg, m } = mapaReal();
  const cobertura = await leer("cobertura.geojson");
  const pulsados = [];
  mapa.ponerCobertura(cobertura, { etiqueta: { textContent: "Primer hito" }, zoomEtiqueta: 9, alPulsarMunicipio: (ine) => pulsados.push(ine), alPulsarEtiqueta: () => pulsados.push("hito") });
  const [velo, halo, bordes] = reg.geojsons;
  assert.equal(velo.opciones.pane, "pc-cobertura-velo");
  assert.equal(velo.opciones.interactive, false);
  assert.equal(velo.datos.geometry.coordinates.length, 1 + cobertura.features.length, "mundo + un hueco por municipio");
  assert.equal(reg.panes["pc-cobertura-velo"].style.zIndex, "350");
  assert.ok(Number(reg.panes["pc-cobertura"].style.zIndex) < 400, "por debajo de las capas de trazados");
  assert.equal(halo.opciones.interactive, false);
  bordes.subcapas[1].disparar("click");
  assert.deepEqual(pulsados, [B.ine]);
  const [etiqueta] = reg.marcadores;
  assert.ok(m.hasLayer(etiqueta), "zoom 6 < 9: se ve la etiqueta");
  m.zoom = 12;
  m.eventos.zoomend();
  assert.ok(!m.hasLayer(etiqueta), "acercado: los contornos bastan");
  etiqueta.eventos.click({});
  assert.deepEqual(pulsados, [B.ine, "hito"]);
});

test("H185: mapa.js cambia de fondo sin duplicar teselas y selecciona un trazado por id", () => {
  const { mapa, reg, m } = mapaReal();
  const [gris, orto] = reg.tiles;
  mapa.ponerFondo("ortofoto");
  assert.ok(m.hasLayer(orto) && !m.hasLayer(gris));
  mapa.ponerFondo("ortofoto");
  mapa.ponerFondo("mapa");
  assert.ok(m.hasLayer(gris) && !m.hasLayer(orto));
  assert.throws(() => mapa.ponerFondo("satelite"), /Fondo desconocido/);
  const [t] = dibujar(mapa, reg, "discrepancias", coleccionDe({ ...feat(lineaDe(SEGMENTO)), id: ID_A }), { claveDe: () => "indicioAlta", orden: 40 });
  assert.equal(mapa.seleccionar("discrepancias", ID_B), false);
  assert.equal(mapa.seleccionar("discrepancias", ID_A), true);
  assert.equal(t.halo.ultimoEstilo.color, BASE.seleccionHalo.claro);
  mapa.encuadrarRasgo("discrepancias", ID_A);
  assert.deepEqual(ultima(m.encuadres), { rasgo: ID_A });
  mapa.deseleccionar();
  assert.deepEqual(t.linea.ultimoEstilo, estiloTrazado("indicioAlta", "normal", "claro", false).linea);
});

test("H185 CA5: ningún texto nuevo del visor lleva palabras vetadas ni referencias catastrales", () => {
  const vetadas = JSON.parse(process.env.VISOR_BANNED_WORDS ?? "[]");
  const textos = Object.values(CONFIG.textos).filter((t) => typeof t === "string");
  textos.push(...CONFIG.capas.map((c) => c.nombre), ...CONFIG.fondos.map((f) => f.titulo));
  for (const t of textos) {
    for (const v of vetadas) assert.ok(!normalizar(t).includes(normalizar(v)), `${v} en «${t}»`);
    assert.doesNotMatch(t, REFCAT);
  }
});
