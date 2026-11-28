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

// Tamaño legible en español («812 bytes», «12,3 KB», «1,4 MB»).
export function tamanoLegible(bytes) {
  if (bytes < 1024) return `${bytes} bytes`;
  const unidad = bytes < 1024 * 1024 ? [1024, "KB"] : [1024 * 1024, "MB"];
  return `${(bytes / unidad[0]).toFixed(1).replace(".", ",")} ${unidad[1]}`;
}

// Valida `datos/kit/indice.json` (historia #223, contrato de #213). A diferencia de
// `validarIndice`, DESCARTA en vez de lanzar: una entrada con `ine` no válido o repetido, una
// clave fuera de `config.kit.formatos`, una ruta no segura o unos bytes que no sean un entero
// no negativo se ignoran, y nunca llegan a un enlace. Una entrada sin ningún fichero válido
// también se descarta. Lanza Error solo si el documento no tiene la forma básica.
export function validarIndiceKit(json, config) {
  if (json === null || typeof json !== "object" || !Array.isArray(json.municipios)) {
    throw new Error("índice del kit sin lista «municipios»");
  }
  const formatos = config.kit.formatos;
  const idsCapa = new Set(config.capas.map((c) => c.id));
  const nombres = (lista) =>
    Array.isArray(lista) ? lista.filter((id) => typeof id === "string" && idsCapa.has(id)) : [];
  const kit = new Map();
  for (const m of json.municipios) {
    if (m === null || typeof m !== "object") continue;
    if (typeof m.ine !== "string" || !INE.test(m.ine) || kit.has(m.ine)) continue;
    if (m.ficheros === null || typeof m.ficheros !== "object" || Array.isArray(m.ficheros)) continue;
    const ficheros = [];
    for (const [clave, fichero] of Object.entries(m.ficheros)) {
      if (!Object.hasOwn(formatos, clave)) continue;
      if (fichero === null || typeof fichero !== "object") continue;
      if (!rutaRelativaSegura(fichero.ruta)) continue;
      if (!Number.isInteger(fichero.bytes) || fichero.bytes < 0) continue;
      ficheros.push({ clave, ruta: fichero.ruta, bytes: fichero.bytes });
    }
    if (ficheros.length === 0) continue;
    // El orden es el de la lista blanca, no el del fichero.
    ficheros.sort((a, b) => Object.keys(formatos).indexOf(a.clave) - Object.keys(formatos).indexOf(b.clave));
    kit.set(m.ine, {
      ine: m.ine,
      capas: nombres(m.capas),
      capasNoPublicadas: nombres(m.capas_no_publicadas),
      ficheros,
    });
  }
  return kit;
}

// Modelo de la sección «Kit de campo» para la vista, o null si el municipio no tiene kit.
export function modeloKit(entrada, municipio, config) {
  if (!entrada) return null;
  const nombreCapa = (id) => config.capas.find((c) => c.id === id)?.kitNombre ?? id;
  return {
    municipio: municipio.nombre,
    capas: entrada.capas.map(nombreCapa),
    capasNoPublicadas: entrada.capasNoPublicadas.map(nombreCapa),
    enlaces: entrada.ficheros.map((f) => ({
      clave: f.clave,
      href: config.kit.base + f.ruta,
      archivo: `${entrada.ine}-${f.ruta.split("/").at(-1)}`,
      rotulo: config.kit.formatos[f.clave].replaceAll("{tamano}", tamanoLegible(f.bytes)),
    })),
  };
}

// Lista completa de atribuciones a mostrar: las del fondo activo siempre, la de la cobertura
// si está dibujada, y la de cada capa solo si está cargada en el mapa y activa.
export function atribucionesVisibles(config, estado) {
  const fondo = config.fondos.find((f) => f.id === estado.fondo) ?? config.fondos[0];
  const deCapas = config.capas
    .filter((capa) => {
      const e = estado.capas[capa.id];
      return Boolean(e && e.cargada && e.visible);
    })
    .map((capa) => capa.atribucion);
  const cobertura = estado.cobertura ? [config.cobertura.atribucion] : [];
  return [...fondo.atribuciones, ...cobertura, ...deCapas];
}

// Texto sin tildes ni mayúsculas, para buscar «chinchon» y encontrar «Chinchón».
export function normalizar(texto) {
  return String(texto)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

// Municipios cubiertos que casan con lo escrito: primero los que empiezan por ello, luego los
// que lo contienen; sin texto, todos en el orden del índice.
export function filtrarMunicipios(municipios, consulta) {
  const q = normalizar(consulta ?? "");
  if (q === "") return [...municipios];
  const empiezan = [];
  const contienen = [];
  for (const m of municipios) {
    const nombre = normalizar(m.nombre);
    if (nombre.startsWith(q) || m.ine === q) empiezan.push(m);
    else if (nombre.includes(q)) contienen.push(m);
  }
  return [...empiezan, ...contienen];
}

// Sustituye «{n}» en una plantilla de config.js.
export function conNumero(plantilla, n) {
  return String(plantilla).replaceAll("{n}", String(n));
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

const CONFIANZAS = new Set(["baja", "media", "alta"]);

const texto = (valor) => (typeof valor === "string" ? valor : "");

// Ficha de un indicio de discrepancia (historia #95, ADR 0044 §2). Lista blanca cerrada: toda
// otra propiedad del dato se ignora. No redacta ni calcula nada: copia lo ya redactado en #16.
// El aviso va SIEMPRE: el de la feature o, si falta, el fijo de config.js. Una feature sin la
// forma esperada devuelve solo el aviso y `disponible: false`. Pura: se prueba sin DOM.
export function fichaIndicio(propiedades, config) {
  const aviso =
    propiedades !== null &&
    typeof propiedades === "object" &&
    typeof propiedades.aviso === "string" &&
    propiedades.aviso.trim() !== ""
      ? propiedades.aviso
      : config.textos.avisoIndicio;
  const p = propiedades;
  if (
    p === null ||
    typeof p !== "object" ||
    typeof p.texto !== "string" ||
    p.texto.trim() === "" ||
    !Array.isArray(p.evidencia)
  ) {
    return { aviso, disponible: false };
  }
  const evidencia = p.evidencia
    .filter((e) => e !== null && typeof e === "object")
    .map((e) => ({
      papel: texto(e.papel),
      fuente: texto(e.fuente),
      anio: typeof e.anio === "number" ? String(e.anio) : config.textos.anioNoDeclarado,
      fechaDescarga: texto(e.fecha_descarga),
      licencia: texto(e.licencia),
      atribucion: texto(e.atribucion),
      url: texto(e.url),
    }));
  return {
    aviso,
    disponible: true,
    etiqueta: texto(p.etiqueta),
    texto: p.texto,
    confianza: CONFIANZAS.has(p.confianza) ? `confianza ${p.confianza}` : "",
    evidencia,
    criterio: texto(p.criterio),
    descripcionCriterio: texto(p.descripcion_criterio),
    avisoOmision: typeof p.aviso_omision === "string" && p.aviso_omision.trim() !== ""
      ? p.aviso_omision
      : null,
  };
}

// Imágenes de comparación de un tramo a verificar (historia #178, ADR 0042 §6, ADR 0049). Pura y
// tolerante: no redacta nada, copia lo publicado en #172. Un campo ausente (fichero anterior a
// #172) o sin ninguna ventana válida da `null` y la ficha queda como antes.
const numeroPositivo = (n) => typeof n === "number" && Number.isFinite(n) && n > 0;
const punto = (p) =>
  Array.isArray(p) && p.length === 2 && p.every((n) => typeof n === "number" && Number.isFinite(n));

function ventanaComparacion(v) {
  if (v === null || typeof v !== "object") return null;
  if (!numeroPositivo(v.ancho_px) || !numeroPositivo(v.alto_px)) return null;
  const partes = (Array.isArray(v.trazo_px) ? v.trazo_px : [])
    .filter((parte) => Array.isArray(parte) && parte.length >= 2 && parte.every(punto))
    .map((parte) => parte.map(([x, y]) => `${x},${y}`).join(" "));
  const imagenes = (Array.isArray(v.imagenes) ? v.imagenes : [])
    .filter((i) => i !== null && typeof i === "object")
    .map((i, orden) => ({
      url: texto(i.url),
      periodo: texto(i.periodo),
      atribucion: texto(i.atribucion),
      alt: texto(i.texto_alternativo),
      // Aviso obligatorio de la fuente (IDEM, historia #208); cadena vacía si no lo lleva.
      aviso: texto(i.aviso_fuente),
      inicio: Number.parseInt(texto(i.periodo), 10),
      orden,
    }))
    // Cronológico por el año con que empieza el periodo; a igualdad o sin año, el del fichero.
    .sort((a, b) => (a.inicio - b.inicio || 0) || a.orden - b.orden)
    .map(({ url, periodo, atribucion, alt, aviso }) => ({ url, periodo, atribucion, alt, aviso }));
  const omitidas = (Array.isArray(v.omitidas) ? v.omitidas : [])
    .filter((o) => o !== null && typeof o === "object" && cadenaNoVacia(o.texto))
    .map((o) => ({ franja: texto(o.franja), texto: o.texto }));
  if (imagenes.length === 0 && omitidas.length === 0) return null;
  return { ancho: v.ancho_px, alto: v.alto_px, partes, imagenes, omitidas };
}

// `notas` es el bloque `comparacion` de la colección (o null): huecos, quién sirve las
// imágenes y el texto de «imagen no disponible», todo tal cual.
export function notasComparacion(propiedadesColeccion) {
  const c = propiedadesColeccion?.comparacion;
  if (c === null || typeof c !== "object") return null;
  return {
    huecos: (Array.isArray(c.huecos) ? c.huecos : [])
      .map((h) => texto(h?.texto))
      .filter((t) => t.trim() !== ""),
    servidasPor: texto(c.servidas_por),
    noDisponible: texto(c.no_disponible),
  };
}

export function fichaComparacion(propiedades, notas, config) {
  const crudas = propiedades?.imagenes_comparacion;
  if (!Array.isArray(crudas)) return null;
  const ventanas = crudas.map(ventanaComparacion).filter((v) => v !== null);
  if (ventanas.length === 0) return null;
  return {
    ventanas,
    huecos: notas?.huecos ?? [],
    servidasPor: notas?.servidasPor ?? "",
    noDisponible: cadenaNoVacia(notas?.noDisponible)
      ? notas.noDisponible
      : config.textos.imagenNoDisponible,
  };
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

// Opciones de estilo que `mapa.anadirCapa` espera, a partir de la descripción de `config.js`
// (#165): `{ clave }` fija o `{ claveDe }`, que elige la clave por una propiedad del trazado.
export function opcionesDeEstilo(capa) {
  const { clave, porPropiedad, claves, defecto } = capa.estilo;
  if (clave !== undefined) return { clave };
  return {
    claveDe: (propiedades) => {
      const valor = propiedades?.[porPropiedad];
      return typeof valor === "string" && Object.hasOwn(claves, valor) ? claves[valor] : defecto;
    },
  };
}

const cadenaNoVacia = (valor) => typeof valor === "string" && valor.trim() !== "";

// Resumen de la medición de la capa de tramos a verificar (historia #171, ADR 0048). Valida la
// forma y devuelve las frases y la marca tal cual vienen: no calcula ni reformula cifras.
// Lanza Error si falta `medicion.texto` (cuatro cadenas no vacías) o `revisado_a_mano`.
export function resumenMedicion(propiedadesColeccion) {
  const p = propiedadesColeccion;
  const frases = p?.medicion?.texto;
  if (
    !Array.isArray(frases) ||
    frases.length !== 4 ||
    !frases.every(cadenaNoVacia) ||
    !cadenaNoVacia(p.revisado_a_mano)
  ) {
    throw new Error("sin medición o sin «revisado a mano»");
  }
  return { frases: [...frases], revisadoAMano: p.revisado_a_mano };
}

export function crearControlador({ mapa, cargarJson, vista, config, alCambiarEnlace }) {
  const estado = {
    municipios: [],
    actual: null, // ine del municipio abierto; null = vista de España
    peticion: 0,
    avisoBase: false,
    capas: {},
    datos: {}, // id de capa -> GeoJSON cargado del municipio actual
    seleccion: null, // { capaId, id }
    fondo: config.fondoInicial,
    fondoElegido: false, // la persona eligió fondo: ya no se cambia solo
    cobertura: false,
    kit: new Map(), // ine -> entrada validada del índice del kit (#223)
  };
  for (const capa of config.capas) {
    estado.capas[capa.id] = { cargada: false, visible: capa.visibleInicial ?? true };
  }
  // Los tipos con la ficha de #94/#169 (misma forma, `fichaIndicio`).
  const esIndicio = (capa) => capa.tipo === "indicio" || capa.tipo === "candidato";
  const esCandidato = (capa) => capa.tipo === "candidato";
  const estadoVacio = (capa) =>
    esCandidato(capa) ? "sin_candidatos" : esIndicio(capa) ? "sin_indicios" : "vacia";
  const capaPorId = (id) => config.capas.find((c) => c.id === id);

  function actualizarAtribuciones() {
    const lista = atribucionesVisibles(config, estado);
    mapa.ponerAtribuciones(lista);
    vista.ponerAtribuciones?.(lista); // pie de las hojas en móvil (#185)
  }

  // Sección «Kit de campo» del municipio actual; sin kit (o en España) se vacía (#223).
  function mostrarKit() {
    const municipio = estado.municipios.find((m) => m.ine === estado.actual);
    vista.ponerKit?.(municipio ? modeloKit(estado.kit.get(municipio.ine), municipio, config) : null);
  }

  // El kit es un extra: si falta, no es válido o tarda, el visor sigue y solo se avisa en consola.
  async function cargarKit() {
    try {
      estado.kit = validarIndiceKit(await cargarJson(config.kit.indice), config);
    } catch (error) {
      console.warn("Kit de campo no disponible:", error?.message ?? error);
    }
  }

  function avisarEnlace() {
    if (typeof alCambiarEnlace !== "function") return;
    const tramo =
      estado.seleccion && esIndicio(capaPorId(estado.seleccion.capaId)) ? estado.seleccion.id : null;
    alCambiarEnlace({ municipio: estado.actual, tramo });
  }

  function ponerFondo(id, porPersona = false) {
    if (!config.fondos.some((f) => f.id === id)) return;
    if (porPersona) estado.fondoElegido = true;
    estado.fondo = id;
    mapa.ponerFondo(id);
    vista.ponerFondo?.(id);
    actualizarAtribuciones();
  }

  async function cargarCapa(capa, ruta) {
    const json = await cargarJson(config.datos + ruta);
    if (!esFeatureCollection(json)) throw new Error("no es un FeatureCollection");
    // Sin medición no se enseña ningún tramo: la capa va a error (CA4 de #171).
    const resumen = esCandidato(capa) ? resumenMedicion(json.properties) : null;
    return { json, resumen };
  }

  // Modelo de la ficha de un trazado, para el panel (historia #185). Los indicios y tramos
  // llevan la ficha de #94/#169 y los tramos además sus imágenes de comparación (#178).
  function modeloFicha(capa, json, propiedades, id) {
    if (esIndicio(capa)) {
      const notas = esCandidato(capa) ? notasComparacion(json?.properties) : null;
      return {
        tipo: capa.tipo,
        capaId: capa.id,
        id,
        nombreCapa: capa.nombre ?? capa.titulo,
        ficha: fichaIndicio(propiedades, config),
        comparacion: esCandidato(capa) ? fichaComparacion(propiedades, notas, config) : null,
      };
    }
    return {
      tipo: "trazado",
      capaId: capa.id,
      id,
      nombreCapa: capa.nombre ?? capa.titulo,
      ficha: fichaDe(capa, propiedades),
      atribucion: capa.atribucion,
    };
  }

  function abrirFicha(capa, propiedades, id) {
    estado.seleccion = { capaId: capa.id, id };
    vista.abrirFicha(modeloFicha(capa, estado.datos[capa.id], propiedades, id));
    avisarEnlace();
  }

  function cerrarFicha() {
    if (estado.seleccion === null) return;
    estado.seleccion = null;
    mapa.deseleccionar();
    vista.cerrarFicha();
    avisarEnlace();
  }

  function quitarCapasDelMunicipio() {
    for (const capa of config.capas) {
      mapa.quitarCapa(capa.id);
      estado.capas[capa.id].cargada = false;
      delete estado.datos[capa.id];
      if (esCandidato(capa)) vista.ponerResumenCapa(capa.id, null);
      vista.ponerRecuentoCapa?.(capa.id, null);
    }
  }

  function verEspana() {
    ++estado.peticion; // anula cargas en curso
    if (estado.seleccion !== null) {
      estado.seleccion = null;
      vista.cerrarFicha();
    }
    estado.actual = null;
    vista.limpiarMensaje();
    quitarCapasDelMunicipio();
    for (const capa of config.capas) vista.ponerEstadoCapa(capa.id, "sin_municipio");
    vista.seleccionarMunicipio(null);
    mostrarKit();
    mapa.resaltarMunicipio?.(null);
    if (!estado.fondoElegido) ponerFondo(config.fondoInicial);
    actualizarAtribuciones();
    mapa.encuadrar(config.espana);
    avisarEnlace();
  }

  // Encuadra los municipios cubiertos sin abrir ninguno (etiqueta del primer hito).
  function verHito() {
    if (estado.municipios.length === 0) return;
    const cajas = estado.municipios.map((m) => m.bbox);
    mapa.encuadrar([
      Math.min(...cajas.map((b) => b[0])),
      Math.min(...cajas.map((b) => b[1])),
      Math.max(...cajas.map((b) => b[2])),
      Math.max(...cajas.map((b) => b[3])),
    ]);
  }

  // `tramo`: id de un indicio o tramo a verificar que abrir al terminar de cargar (enlace).
  async function elegirMunicipio(ine, { tramo = null } = {}) {
    const municipio = estado.municipios.find((m) => m.ine === ine);
    if (!municipio) return;
    if (estado.actual === municipio.ine && tramo === null) {
      cerrarFicha();
      return;
    }
    const peticion = ++estado.peticion;
    if (estado.seleccion !== null) {
      estado.seleccion = null;
      vista.cerrarFicha();
    }
    estado.actual = municipio.ine;
    vista.limpiarMensaje();
    vista.seleccionarMunicipio(municipio.ine, municipio.nombre);
    mostrarKit();
    mapa.resaltarMunicipio?.(municipio.ine);
    quitarCapasDelMunicipio();
    if (!estado.fondoElegido) ponerFondo(config.fondoMunicipio);
    actualizarAtribuciones();
    mapa.encuadrar(municipio.bbox);
    avisarEnlace();

    const pendientes = config.capas.filter((capa) => capa.id in municipio.capas);
    for (const capa of config.capas) {
      // Una capa que el índice no lista no se publicó: #84 no publica capas vacías.
      vista.ponerEstadoCapa(capa.id, capa.id in municipio.capas ? "cargando" : estadoVacio(capa));
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
      const { json: geojson, resumen } = resultado.value;
      // Cero tramos: el mismo estado vacío y sin resumen (CA6 de #171); nada que dibujar.
      if (esCandidato(capa) && geojson.features.length === 0) {
        vista.ponerEstadoCapa(capa.id, estadoVacio(capa));
        return;
      }
      estado.datos[capa.id] = geojson;
      mapa.anadirCapa(capa.id, geojson, {
        ...opcionesDeEstilo(capa),
        orden: capa.orden,
        alPulsar: (propiedades, id) => abrirFicha(capa, propiedades, id),
      });
      mapa.mostrarCapa(capa.id, estado.capas[capa.id].visible);
      estado.capas[capa.id].cargada = true;
      vista.ponerEstadoCapa(capa.id, geojson.features.length === 0 ? estadoVacio(capa) : "ok");
      vista.ponerRecuentoCapa?.(capa.id, geojson.features.length);
      if (resumen) vista.ponerResumenCapa(capa.id, resumen);
    });
    if (errores.length > 0) vista.mostrarMensaje(errores.join(" "));
    actualizarAtribuciones();
    if (tramo !== null) abrirTramo(tramo);
  }

  // Abre por id un indicio o tramo del municipio actual; enciende su capa si estaba apagada.
  function abrirTramo(id) {
    for (const capa of config.capas.filter(esIndicio)) {
      const json = estado.datos[capa.id];
      const feature = json?.features.find((f) => String(f.id) === String(id));
      if (!feature) continue;
      if (!estado.capas[capa.id].visible) {
        cambiarCapa(capa.id, true);
        vista.marcarCapa?.(capa.id, true);
      }
      mapa.seleccionar(capa.id, String(id));
      // Primero la ficha: así el encuadre ya cuenta con el panel o la hoja que ocupa.
      abrirFicha(capa, feature.properties ?? {}, String(id));
      mapa.encuadrarRasgo?.(capa.id, String(id));
      return true;
    }
    vista.mostrarMensaje(config.textos.tramoNoPublicado);
    avisarEnlace();
    return false;
  }

  function acercarSeleccion() {
    if (estado.seleccion) mapa.encuadrarRasgo?.(estado.seleccion.capaId, estado.seleccion.id);
  }

  async function iniciar({ municipio = null, tramo = null } = {}) {
    actualizarAtribuciones();
    const kitCargado = cargarKit(); // en paralelo al índice; nunca rechaza
    let municipios;
    try {
      municipios = validarIndice(await cargarJson(config.indice));
    } catch {
      vista.mostrarMensaje(config.textos.errorIndice);
      return;
    }
    estado.municipios = municipios;
    vista.ponerMunicipios(municipios.map((m) => ({ ine: m.ine, nombre: m.nombre })));
    vista.ponerResumenCobertura?.(conNumero(config.textos.resumenCobertura, municipios.length));
    await cargarCobertura();
    await kitCargado;
    if (municipio !== null && municipios.some((m) => m.ine === municipio)) {
      await elegirMunicipio(municipio, { tramo });
    } else {
      verEspana();
    }
  }

  async function cargarCobertura() {
    let json;
    try {
      json = await cargarJson(config.cobertura.ruta);
      if (!esFeatureCollection(json)) throw new Error("no es un FeatureCollection");
    } catch {
      vista.mostrarAvisoBase(config.textos.errorCobertura);
      return;
    }
    mapa.ponerCobertura?.(json, {
      etiqueta: vista.nodoEtiquetaHito?.(
        conNumero(config.textos.etiquetaHito, estado.municipios.length),
      ),
      zoomEtiqueta: config.cobertura.zoomEtiqueta,
      alPulsarMunicipio: (ine) => elegirMunicipio(ine),
      alPulsarEtiqueta: verHito,
    });
    estado.cobertura = true;
    actualizarAtribuciones();
  }

  function cambiarCapa(id, visible) {
    const e = estado.capas[id];
    if (!e) return;
    e.visible = Boolean(visible);
    if (e.cargada) mapa.mostrarCapa(id, e.visible);
    if (!e.visible && estado.seleccion?.capaId === id) cerrarFicha();
    actualizarAtribuciones();
  }

  function buscar(texto) {
    return filtrarMunicipios(estado.municipios, texto).map((m) => ({ ine: m.ine, nombre: m.nombre }));
  }

  function falloTesela() {
    if (estado.avisoBase) return;
    estado.avisoBase = true;
    vista.mostrarAvisoBase(config.textos.mapaBaseNoDisponible);
  }

  return {
    iniciar,
    elegirMunicipio,
    verEspana,
    verHito,
    cambiarCapa,
    cambiarFondo: (id) => ponerFondo(id, true),
    cerrarFicha,
    acercarSeleccion,
    buscar,
    falloTesela,
    estado,
  };
}
