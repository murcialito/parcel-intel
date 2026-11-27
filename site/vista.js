// Vista del visor (historia #85; rediseño #185): el único módulo, junto con app.js, que toca el
// DOM. Recibe el `document` por inyección (se prueba con un documento falso en Node).
// Todo texto que viene de datos se inserta con `textContent`, nunca como HTML (CA6 de #85).

// Solo `https:` seguido de dos barras y algo más (en minúsculas, sin espacios).
const ENLACE_SEGURO = /^https:\/\/\S/;

// Espacio de nombres de SVG: un identificador, no una URL que se pida. Partido en dos para que
// el escáner de URL absolutas de #85 (CA1) no lo tome por un recurso externo.
const SVG_NS = "http:" + "//www.w3.org/2000/svg";

export function crearVista(documento, textos) {
  const porId = (id) => {
    const elemento = documento.getElementById(id);
    if (!elemento) throw new Error(`falta el elemento #${id}`);
    return elemento;
  };
  const mensaje = porId("mensaje");
  const avisoBase = porId("aviso-base");

  const TEXTO_ESTADO = {
    ok: "",
    cargando: textos.cargando,
    vacia: textos.sinTrazados,
    sin_indicios: textos.sinIndicios,
    sin_candidatos: textos.sinCandidatos,
    sin_municipio: textos.sinMunicipio,
    error: textos.errorCapa,
  };

  // Acciones que la ficha y el buscador llaman; las conecta app.js.
  let acciones = {};
  function conectar(nuevas) {
    acciones = { ...acciones, ...nuevas };
  }

  function crear(tag, clase, texto) {
    const e = documento.createElement(tag);
    if (clase) e.className = clase;
    if (texto !== undefined) e.textContent = texto;
    return e;
  }
  const parrafo = (clase, contenido) => crear("p", clase, contenido);

  // --- buscador ------------------------------------------------------------------------
  let municipios = [];
  let sugeridas = [];
  let activa = -1;

  function ponerMunicipios(lista) {
    municipios = lista.map(({ ine, nombre }) => ({ ine, nombre }));
  }

  function cerrarSugerencias() {
    const lista = porId("sugerencias");
    const entrada = porId("buscar");
    lista.replaceChildren();
    lista.setAttribute("hidden", "");
    entrada.setAttribute("aria-expanded", "false");
    entrada.removeAttribute("aria-activedescendant");
    sugeridas = [];
    activa = -1;
  }

  // `lista`: municipios que casan; vacía, se dice que aún no hay cobertura (`sinCoincidencias`).
  function mostrarSugerencias(lista, sinCoincidencias = "") {
    const contenedor = porId("sugerencias");
    const entrada = porId("buscar");
    contenedor.replaceChildren();
    sugeridas = lista;
    activa = -1;
    entrada.removeAttribute("aria-activedescendant");
    if (lista.length === 0) {
      const li = crear("li", "pc-sugerencias__vacio", sinCoincidencias);
      li.setAttribute("role", "presentation");
      contenedor.appendChild(li);
    }
    lista.forEach(({ ine, nombre }, i) => {
      const li = crear("li", "pc-sugerencias__opcion", nombre);
      li.setAttribute("role", "option");
      li.setAttribute("id", `sugerencia-${ine}`);
      li.setAttribute("aria-selected", "false");
      li.dataset.ine = ine;
      // `mousedown` y no `click`: elige antes de que el campo pierda el foco.
      li.addEventListener("mousedown", (evento) => {
        evento?.preventDefault?.();
        elegir(i);
      });
      contenedor.appendChild(li);
    });
    contenedor.removeAttribute("hidden");
    entrada.setAttribute("aria-expanded", "true");
  }

  function marcarActiva(i) {
    const opciones = Array.from(porId("sugerencias").children).filter((li) => li.dataset?.ine);
    activa = i;
    opciones.forEach((li, j) => li.setAttribute("aria-selected", String(j === i)));
    const entrada = porId("buscar");
    if (i >= 0 && opciones[i]) {
      entrada.setAttribute("aria-activedescendant", opciones[i].getAttribute("id"));
      opciones[i].scrollIntoView?.({ block: "nearest" });
    } else {
      entrada.removeAttribute("aria-activedescendant");
    }
  }

  function elegir(i) {
    const m = sugeridas[i];
    if (!m) return;
    cerrarSugerencias();
    porId("buscar").value = m.nombre;
    acciones.alElegirMunicipio?.(m.ine);
  }

  // Teclado del combobox (patrón ARIA «combobox con lista»): flechas, Intro y Escape.
  function teclaBuscador(evento) {
    const total = sugeridas.length;
    if (evento.key === "ArrowDown") {
      evento.preventDefault?.();
      if (porId("buscar").getAttribute("aria-expanded") !== "true") acciones.alEscribir?.(porId("buscar").value);
      else if (total > 0) marcarActiva((activa + 1) % total);
    } else if (evento.key === "ArrowUp") {
      evento.preventDefault?.();
      if (total > 0) marcarActiva(activa <= 0 ? total - 1 : activa - 1);
    } else if (evento.key === "Enter") {
      evento.preventDefault?.();
      if (total > 0) elegir(activa >= 0 ? activa : 0);
    } else if (evento.key === "Escape") {
      cerrarSugerencias();
    }
  }

  // --- municipio y cobertura -----------------------------------------------------------
  function seleccionarMunicipio(ine, nombre = "") {
    const enEspana = ine === null || ine === undefined;
    porId("ambito-nombre").textContent = enEspana ? textos.espana : nombre;
    const boton = porId("ver-espana");
    if (enEspana) boton.setAttribute("hidden", "");
    else boton.removeAttribute("hidden");
    porId("buscar").value = enEspana ? "" : nombre;
    documento.body?.setAttribute?.("data-ambito", enEspana ? "espana" : "municipio");
  }

  function ponerResumenCobertura(texto) {
    porId("ambito-resumen").textContent = texto;
  }

  // Etiqueta del primer hito sobre el mapa de España: un nodo de texto, no HTML.
  function nodoEtiquetaHito(texto) {
    const nodo = crear("span", "pc-hito__texto", texto);
    return nodo;
  }

  // --- capas ---------------------------------------------------------------------------
  // Resumen de la medición bajo la capa de tramos a verificar (historia #171): las frases y la
  // marca «revisado a mano» tal cual, con textContent. `null` lo vacía. Desde #185 (feedback del
  // fundador) la marca queda a la vista y las frases se pliegan en «Cómo se ha medido», para ver
  // todas las capas a la vez sin desplazar el panel.
  function ponerResumenCapa(id, resumen) {
    const contenedor = porId(`resumen-${id}`);
    contenedor.replaceChildren();
    if (resumen === null) return;
    contenedor.appendChild(parrafo("pc-capa__revisado", resumen.revisadoAMano));
    const plegable = detalle(textos.comoSeMide, "pc-medicion");
    for (const frase of resumen.frases) plegable.appendChild(parrafo("", frase));
    contenedor.appendChild(plegable);
  }

  function ponerRecuentoCapa(id, n) {
    const elemento = documento.getElementById(`recuento-${id}`);
    if (elemento) elemento.textContent = typeof n === "number" && n > 0 ? String(n) : "";
  }

  function ponerEstadoCapa(id, estado) {
    const elemento = porId(`estado-${id}`);
    const texto = TEXTO_ESTADO[estado] ?? "";
    elemento.replaceChildren();
    // En carga, una barra decorativa (`aria-hidden`) antes del texto (historia #166, CA4).
    if (estado === "cargando") {
      const progreso = crear("div", "pc-progreso");
      progreso.setAttribute("aria-hidden", "true");
      progreso.appendChild(documento.createElement("i"));
      elemento.appendChild(progreso);
    }
    if (texto !== "") elemento.appendChild(crear("span", "", texto));
    elemento.dataset.estado = estado;
  }

  function marcarCapa(id, visible) {
    const casilla = documento.getElementById(`capa-${id}`);
    if (casilla) casilla.checked = Boolean(visible);
  }

  function ponerFondo(id) {
    const radio = documento.getElementById(`fondo-${id}`);
    if (radio) radio.checked = true;
  }

  // --- kit de campo (historia #223) ----------------------------------------------------
  // Sección del panel con los enlaces de descarga del municipio actual. `null` la oculta y la
  // vacía. Todo con createElement/textContent; el `href` viene de `config.kit.base` + una ruta ya
  // validada por el controlador, nunca de una URL del dato.
  function ponerKit(modelo) {
    const seccion = porId("kit-campo");
    const cuerpo = porId("kit-cuerpo");
    cuerpo.replaceChildren();
    if (modelo === null) {
      seccion.setAttribute("hidden", "");
      return;
    }
    const aviso = crear("p", "pc-kit__aviso");
    aviso.appendChild(
      crear("strong", "", textos.kitAvisoTitulo.replaceAll("{municipio}", modelo.municipio)),
    );
    aviso.appendChild(crear("span", "", ` ${textos.kitAvisoCuerpo}`));
    cuerpo.appendChild(aviso);
    cuerpo.appendChild(parrafo("ficha-aviso", textos.avisoIndicio));

    const lista = crear("ul", "pc-kit__enlaces");
    for (const e of modelo.enlaces) {
      const item = documento.createElement("li");
      const enlace = crear("a", "pc-boton", e.rotulo);
      enlace.setAttribute("href", e.href);
      enlace.setAttribute("download", e.archivo);
      item.appendChild(enlace);
      lista.appendChild(item);
    }
    cuerpo.appendChild(lista);
    if (modelo.capas.length > 0) {
      cuerpo.appendChild(parrafo("pc-kit__capas", `${textos.kitIncluye}: ${modelo.capas.join(", ")}.`));
    }
    if (modelo.capasNoPublicadas.length > 0) {
      cuerpo.appendChild(
        parrafo("pc-kit__capas", `${textos.kitSinPublicar}: ${modelo.capasNoPublicadas.join(", ")}.`),
      );
    }
    seccion.removeAttribute("hidden");
  }

  // --- mensajes ------------------------------------------------------------------------
  function mostrarMensaje(texto) {
    mensaje.textContent = texto;
  }

  function limpiarMensaje() {
    mensaje.textContent = "";
  }

  // Móvil: las hojas tapan el pie del mapa, así que repiten en su pie fijo las atribuciones
  // visibles (revisión de #185). Texto plano, la misma lista que el control del mapa.
  function ponerAtribuciones(lista) {
    const texto = lista.join(" · ");
    for (const id of ["panel-atribucion", "ficha-atribucion"]) {
      const elemento = documento.getElementById(id);
      if (elemento) elemento.textContent = texto;
    }
  }

  function mostrarAvisoBase(texto) {
    avisoBase.textContent = texto;
  }

  let temporizador = null;
  function avisar(texto) {
    const toast = documento.getElementById("aviso-flotante");
    if (!toast) return;
    toast.textContent = texto;
    if (temporizador !== null) globalThis.clearTimeout?.(temporizador);
    temporizador = globalThis.setTimeout?.(() => {
      toast.textContent = "";
    }, 2500) ?? null;
  }

  // --- ficha ---------------------------------------------------------------------------
  // Ficha de un trazado de referencia (vía pecuaria, camino actual): fuente y atribución.
  function nodoFicha({ titulo, fuente, nombre }, atribucion = "") {
    const ficha = crear("div", "ficha");
    if (nombre) ficha.appendChild(parrafo("ficha-capa", titulo));
    ficha.appendChild(parrafo("ficha-fuente", `${textos.fuente}: ${fuente}`));
    if (atribucion) ficha.appendChild(parrafo("ficha-fuente", atribucion));
    return ficha;
  }

  // Muestra de la confianza: la misma línea punteada que en el mapa y la leyenda.
  function muestraConfianza(nivel) {
    const svg = documento.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", `pc-muestra pc-muestra--indicio pc-muestra--${nivel}`);
    svg.setAttribute("viewBox", "0 0 44 16");
    svg.setAttribute("aria-hidden", "true");
    for (const clase of ["h", "l"]) {
      const linea = documento.createElementNS(SVG_NS, "line");
      for (const [k, v] of [["class", clase], ["x1", "4"], ["y1", "8"], ["x2", "40"], ["y2", "8"]]) {
        linea.setAttribute(k, v);
      }
      svg.appendChild(linea);
    }
    return svg;
  }

  // Bloque plegable del detalle: `<details>` con su `<summary>`.
  function detalle(titulo, clase = "") {
    const d = crear("details", `pc-detalle ${clase}`.trim());
    d.appendChild(crear("summary", "pc-detalle__titulo", titulo));
    return d;
  }

  // Trazo sobre la imagen (ADR 0042 §6): `svg` con `viewBox` en píxeles de la imagen y una
  // `polyline` por parte, todo con createElementNS y atributos; nada de HTML como cadena.
  function nodoTrazo(ventana) {
    const svg = documento.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${ventana.ancho} ${ventana.alto}`);
    svg.setAttribute("class", "pc-comparacion__trazo");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    for (const puntos of ventana.partes) {
      const linea = documento.createElementNS(SVG_NS, "polyline");
      linea.setAttribute("points", puntos);
      linea.setAttribute("fill", "none");
      svg.appendChild(linea);
    }
    return svg;
  }

  function nodoImagenComparacion(imagen, ventana, comparacion) {
    const figura = crear("figure", "pc-comparacion__imagen");
    const lienzo = crear("div", "pc-comparacion__lienzo");
    if (ENLACE_SEGURO.test(imagen.url)) {
      const img = documento.createElement("img");
      img.setAttribute("src", imagen.url);
      img.setAttribute("alt", imagen.alt);
      img.setAttribute("loading", "lazy");
      img.setAttribute("width", String(ventana.ancho));
      img.setAttribute("height", String(ventana.alto));
      // Si no carga, el lienzo pasa a decir «imagen no disponible»; la atribución se conserva.
      img.addEventListener("error", () => {
        lienzo.replaceChildren(parrafo("pc-comparacion__no-disponible", comparacion.noDisponible));
      });
      lienzo.appendChild(img);
      lienzo.appendChild(nodoTrazo(ventana));
    } else {
      lienzo.appendChild(parrafo("pc-comparacion__no-disponible", comparacion.noDisponible));
    }
    figura.appendChild(lienzo);
    const pie = documento.createElement("figcaption");
    pie.appendChild(parrafo("pc-comparacion__periodo", imagen.periodo));
    pie.appendChild(parrafo("ficha-fuente", imagen.atribucion));
    figura.appendChild(pie);
    return figura;
  }

  function nodoComparacion(comparacion) {
    const imagenes = comparacion.ventanas.reduce((n, v) => n + v.imagenes.length, 0);
    const seccion = detalle(`${textos.tituloComparacion} (${imagenes})`, "pc-comparacion");

    // Control accesible: botón con `aria-pressed`; oculta o muestra todos los trazos de la ficha.
    const control = crear("button", "pc-boton pc-boton--texto pc-comparacion__control", textos.mostrarTrazo);
    control.setAttribute("type", "button");
    control.setAttribute("aria-pressed", "true");
    seccion.appendChild(control);

    const rejilla = crear("div", "pc-comparacion__rejilla");
    for (const ventana of comparacion.ventanas) {
      for (const imagen of ventana.imagenes) {
        rejilla.appendChild(nodoImagenComparacion(imagen, ventana, comparacion));
      }
    }
    seccion.appendChild(rejilla);
    for (const ventana of comparacion.ventanas) {
      for (const omitida of ventana.omitidas) {
        seccion.appendChild(parrafo("ficha-nota", `${omitida.franja}: ${omitida.texto}`));
      }
    }
    const trazos = [];
    const recoger = (nodo) => {
      if (nodo.tagName === "svg" || nodo.tagName === "SVG") {
        if (String(nodo.getAttribute?.("class") ?? "").includes("pc-comparacion__trazo")) trazos.push(nodo);
      }
      for (const hijo of nodo.children ?? []) recoger(hijo);
    };
    recoger(rejilla);
    control.addEventListener("click", () => {
      const visible = control.getAttribute("aria-pressed") !== "true";
      control.setAttribute("aria-pressed", String(visible));
      for (const trazo of trazos) {
        if (visible) trazo.removeAttribute("hidden");
        else trazo.setAttribute("hidden", "");
      }
    });

    for (const hueco of comparacion.huecos) seccion.appendChild(parrafo("ficha-nota", hueco));
    if (comparacion.servidasPor !== "") {
      seccion.appendChild(parrafo("ficha-fuente", comparacion.servidasPor));
    }
    return seccion;
  }

  function nodoFuentes(evidencia) {
    const seccion = detalle(`${textos.fuentes} (${evidencia.length})`, "pc-fuentes");
    const lista = crear("ul", "ficha-fuentes");
    for (const e of evidencia) {
      const item = documento.createElement("li");
      item.appendChild(parrafo("ficha-fuentes__nombre", `${e.papel}: ${e.fuente} (${e.anio})`));
      item.appendChild(parrafo("ficha-fuente", `Descargada el ${e.fechaDescarga}`));
      item.appendChild(parrafo("ficha-fuente", `Licencia: ${e.licencia}`));
      item.appendChild(parrafo("ficha-fuente", e.atribucion));
      // El enlace se crea solo si la URL es https con dos barras; si no, va como texto.
      if (ENLACE_SEGURO.test(e.url)) {
        const enlace = crear("a", "ficha-enlace", textos.abrirConsulta);
        enlace.setAttribute("href", e.url);
        enlace.setAttribute("title", e.url);
        enlace.setAttribute("rel", "noopener noreferrer");
        enlace.setAttribute("target", "_blank");
        const p = crear("p", "ficha-fuente");
        p.appendChild(enlace);
        item.appendChild(p);
      } else if (e.url !== "") {
        item.appendChild(parrafo("ficha-fuente", e.url));
      }
      lista.appendChild(item);
    }
    seccion.appendChild(lista);
    return seccion;
  }

  function nodoAcciones() {
    const barra = crear("div", "pc-ficha__acciones");
    const acercar = crear("button", "pc-boton", textos.acercar);
    acercar.setAttribute("type", "button");
    acercar.addEventListener("click", () => acciones.alAcercar?.());
    const copiar = crear("button", "pc-boton", textos.copiarEnlace);
    copiar.setAttribute("type", "button");
    copiar.addEventListener("click", () => acciones.alCopiarEnlace?.());
    barra.appendChild(acercar);
    barra.appendChild(copiar);
    return barra;
  }

  // Cuerpo de la ficha de un indicio o tramo (historias #95, #171, #185). Primero el resumen
  // (texto validado, confianza y aviso, que nunca se pliega); después el detalle plegable.
  function nodoFichaIndicio(ficha, comparacion = null) {
    const nodo = crear("div", "ficha ficha-indicio");
    if (!ficha.disponible) {
      nodo.appendChild(parrafo("", textos.fichaNoDisponible));
      nodo.appendChild(parrafo("ficha-aviso", ficha.aviso));
      return nodo;
    }
    nodo.appendChild(parrafo("ficha-texto", ficha.texto));
    if (ficha.confianza) {
      const p = crear("p", "ficha-confianza");
      p.appendChild(muestraConfianza(ficha.confianza.replace("confianza ", "")));
      p.appendChild(crear("span", "", ficha.confianza));
      nodo.appendChild(p);
    }
    nodo.appendChild(parrafo("ficha-aviso", ficha.aviso));
    if (ficha.avisoOmision !== null) nodo.appendChild(parrafo("ficha-aviso", ficha.avisoOmision));
    nodo.appendChild(nodoAcciones());
    if (comparacion !== null) nodo.appendChild(nodoComparacion(comparacion));
    nodo.appendChild(nodoFuentes(ficha.evidencia));
    // Los tramos a verificar (#171) no traen criterio: no se pintan párrafos vacíos.
    if (ficha.criterio !== "" || ficha.descripcionCriterio !== "") {
      const como = detalle(textos.comoSeCalcula, "pc-criterio");
      if (ficha.criterio !== "") como.appendChild(parrafo("ficha-criterio", `Criterio: ${ficha.criterio}`));
      if (ficha.descripcionCriterio !== "") {
        como.appendChild(parrafo("ficha-criterio", ficha.descripcionCriterio));
      }
      nodo.appendChild(como);
    }
    return nodo;
  }

  // Abre el panel (escritorio) u hoja inferior (móvil) con la ficha del modelo del controlador.
  function abrirFicha(modelo) {
    const panel = porId("ficha");
    porId("ficha-tipo").textContent = modelo.nombreCapa;
    let titulo;
    let cuerpo;
    if (modelo.tipo === "trazado") {
      titulo = modelo.ficha.nombre ?? modelo.ficha.titulo;
      cuerpo = nodoFicha(modelo.ficha, modelo.atribucion);
    } else {
      titulo = modelo.ficha.disponible && modelo.ficha.etiqueta ? modelo.ficha.etiqueta : modelo.nombreCapa;
      cuerpo = nodoFichaIndicio(modelo.ficha, modelo.comparacion);
    }
    porId("ficha-titulo").textContent = titulo;
    porId("ficha-cuerpo").replaceChildren(cuerpo);
    panel.dataset.tipo = modelo.tipo;
    panel.removeAttribute("hidden");
    ampliarFicha(false);
    documento.body?.setAttribute?.("data-ficha", "abierta");
    // El foco pasa al panel si estaba en la página (clic en el mapa, teclado); al abrir desde
    // un enlace no se mueve, para no pintar el anillo sin que nadie haya interactuado.
    if (documento.activeElement && documento.activeElement !== documento.body) {
      panel.focus?.({ preventScroll: true });
    }
  }

  function cerrarFicha() {
    const panel = porId("ficha");
    panel.setAttribute("hidden", "");
    porId("ficha-cuerpo").replaceChildren();
    documento.body?.removeAttribute?.("data-ficha");
  }

  // Móvil: la hoja se abre a media altura (resumen) y se amplía para leer el detalle.
  function ampliarFicha(ampliada) {
    const boton = porId("ficha-ampliar");
    boton.setAttribute("aria-expanded", String(Boolean(ampliada)));
    boton.setAttribute("aria-label", ampliada ? "Reducir la ficha" : "Ampliar la ficha");
    porId("ficha").dataset.ampliada = String(Boolean(ampliada));
  }

  function plegarPanel(abierto) {
    const boton = porId("plegar");
    boton.setAttribute("aria-expanded", String(Boolean(abierto)));
    documento.body?.setAttribute?.("data-panel", abierto ? "abierto" : "plegado");
  }

  return {
    conectar,
    ponerMunicipios,
    mostrarSugerencias,
    cerrarSugerencias,
    teclaBuscador,
    seleccionarMunicipio,
    ponerResumenCobertura,
    nodoEtiquetaHito,
    ponerEstadoCapa,
    ponerResumenCapa,
    ponerRecuentoCapa,
    ponerKit,
    marcarCapa,
    ponerFondo,
    mostrarMensaje,
    limpiarMensaje,
    mostrarAvisoBase,
    ponerAtribuciones,
    avisar,
    nodoFicha,
    nodoFichaIndicio,
    abrirFicha,
    cerrarFicha,
    ampliarFicha,
    plegarPanel,
  };
}
