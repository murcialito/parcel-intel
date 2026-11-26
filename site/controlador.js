// Lógica del visor (historia #85, ADR 0037). Sin imports, sin `document` y sin la librería de
// mapas: el mapa, la carga de JSON y la vista se inyectan. Así se prueba con `node --test`.

const INE = /^\d{5}$/;

function rutaRelativaSegura(ruta) {
  return (
    typeof ruta === "string" &&
    ruta.length > 0 &&
    !ruta.startsWith("/") &&
    !ruta.includes("\\") &&
    !ruta.includes(":") &&
    !ruta.split("/").includes("..")
  );
}

function bboxValido(bbox) {
  if (!Array.isArray(bbox) || bbox.length !== 4) return false;
  if (!bbox.every((n) => typeof n === "number" && Number.isFinite(n))) return false;
  const [oeste, sur, este, norte] = bbox;
  return oeste < este && sur < norte && sur >= -90 && norte <= 90 && oeste >= -180 && este <= 180;
}

// Valida `datos/indice.json` y devuelve la lista de municipios en el orden del índice.
// Lanza Error si la forma no es la del contrato de #84.
export function validarIndice(json) {
  if (json === null || typeof json !== "object" || !Array.isArray(json.municipios)) {
    throw new Error("índice sin lista «municipios»");
  }
  const vistos = new Set();
  return json.municipios.map((m, i) => {
    if (m === null || typeof m !== "object") throw new Error(`municipio ${i}: no es un objeto`);
    if (typeof m.ine !== "string" || !INE.test(m.ine)) throw new Error(`municipio ${i}: ine`);
    if (vistos.has(m.ine)) throw new Error(`municipio ${i}: ine repetido ${m.ine}`);
    vistos.add(m.ine);
    if (typeof m.nombre !== "string" || m.nombre.trim() === "") {
      throw new Error(`municipio ${m.ine}: nombre`);
    }
    if (!bboxValido(m.bbox)) throw new Error(`municipio ${m.ine}: bbox`);
    if (m.capas === null || typeof m.capas !== "object" || Array.isArray(m.capas)) {
      throw new Error(`municipio ${m.ine}: capas`);
    }
    const capas = {};
    for (const [id, ruta] of Object.entries(m.capas)) {
      if (!rutaRelativaSegura(ruta)) throw new Error(`municipio ${m.ine}: ruta de ${id}`);
      capas[id] = ruta;
    }
    return { ine: m.ine, nombre: m.nombre, bbox: [...m.bbox], capas };
  });
}

// Lista completa de atribuciones a mostrar: las del mapa base siempre, y la de cada capa
// solo si está cargada en el mapa y activa.
export function atribucionesVisibles(config, estado) {
  const deCapas = config.capas
    .filter((capa) => {
      const e = estado.capas[capa.id];
      return Boolean(e && e.cargada && e.visible);
    })
    .map((capa) => capa.atribucion);
  return [...config.atribucionesBase, ...deCapas];
}

// Ficha de un trazado: SOLO título y fuente de la capa y, si la capa lo define, el nombre del
// trazado. Cualquier otra propiedad del dato se ignora (CA6).
export function fichaDe(capa, propiedades) {
  const ficha = { titulo: capa.titulo, fuente: capa.fuente };
  if (capa.propiedadNombre && propiedades !== null && typeof propiedades === "object") {
    const nombre = propiedades[capa.propiedadNombre];
    if (typeof nombre === "string" && nombre.trim() !== "") ficha.nombre = nombre.trim();
  }
  return ficha;
}

// Una respuesta que no es un FeatureCollection es fallo, no «vacío».
export function esFeatureCollection(json) {
  return (
    json !== null &&
    typeof json === "object" &&
    json.type === "FeatureCollection" &&
    Array.isArray(json.features)
  );
}

export function mensajeErrorCapa(capa, municipio) {
  return `No se pudo cargar la capa «${capa.titulo}» de ${municipio.nombre}.`;
}

export function crearControlador({ mapa, cargarJson, vista, config }) {
  const estado = { municipios: [], actual: null, peticion: 0, avisoBase: false, capas: {} };
  for (const capa of config.capas) estado.capas[capa.id] = { cargada: false, visible: true };

  function actualizarAtribuciones() {
    mapa.ponerAtribuciones(atribucionesVisibles(config, estado));
  }

  async function cargarCapa(capa, ruta) {
    const json = await cargarJson(config.datos + ruta);
    if (!esFeatureCollection(json)) throw new Error("no es un FeatureCollection");
    return json;
  }

  async function elegirMunicipio(ine) {
    const municipio = estado.municipios.find((m) => m.ine === ine);
    if (!municipio) return;
    const peticion = ++estado.peticion;
    estado.actual = municipio.ine;
    vista.limpiarMensaje();
    vista.seleccionarMunicipio(municipio.ine);
    for (const capa of config.capas) {
      mapa.quitarCapa(capa.id);
      estado.capas[capa.id].cargada = false;
    }
    actualizarAtribuciones();
    mapa.encuadrar(municipio.bbox);

    const pendientes = config.capas.filter((capa) => capa.id in municipio.capas);
    for (const capa of config.capas) {
      // Una capa que el índice no lista no se publicó: #84 no publica capas vacías.
      vista.ponerEstadoCapa(capa.id, capa.id in municipio.capas ? "cargando" : "vacia");
    }
    const resultados = await Promise.allSettled(
      pendientes.map((capa) => cargarCapa(capa, municipio.capas[capa.id])),
    );
    if (peticion !== estado.peticion) return; // otra elección más reciente manda

    const errores = [];
    resultados.forEach((resultado, i) => {
      const capa = pendientes[i];
      if (resultado.status === "rejected") {
        vista.ponerEstadoCapa(capa.id, "error");
        errores.push(mensajeErrorCapa(capa, municipio));
        return;
      }
      const geojson = resultado.value;
      mapa.anadirCapa(capa.id, geojson, {
        estilo: capa.estilo,
        alPulsar: (propiedades) => vista.nodoFicha(fichaDe(capa, propiedades)),
      });
      mapa.mostrarCapa(capa.id, estado.capas[capa.id].visible);
      estado.capas[capa.id].cargada = true;
      vista.ponerEstadoCapa(capa.id, geojson.features.length === 0 ? "vacia" : "ok");
    });
    if (errores.length > 0) vista.mostrarMensaje(errores.join(" "));
    actualizarAtribuciones();
  }

  async function iniciar() {
    mapa.ponerAtribuciones([...config.atribucionesBase]);
    let municipios;
    try {
      municipios = validarIndice(await cargarJson(config.indice));
    } catch {
      vista.mostrarMensaje(config.textos.errorIndice);
      return;
    }
    estado.municipios = municipios;
    vista.ponerMunicipios(municipios.map((m) => ({ ine: m.ine, nombre: m.nombre })));
    if (municipios.length > 0) await elegirMunicipio(municipios[0].ine);
  }

  function cambiarCapa(id, visible) {
    const e = estado.capas[id];
    if (!e) return;
    e.visible = Boolean(visible);
    if (e.cargada) mapa.mostrarCapa(id, e.visible);
    actualizarAtribuciones();
  }

  function falloTesela() {
    if (estado.avisoBase) return;
    estado.avisoBase = true;
    vista.mostrarAvisoBase(config.textos.mapaBaseNoDisponible);
  }

  return { iniciar, elegirMunicipio, cambiarCapa, falloTesela, estado };
}
