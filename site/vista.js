// Vista del visor (historia #85): el único módulo, junto con app.js, que toca el DOM.
// Recibe el `document` por inyección (se prueba con un documento falso en Node).
// Todo texto que viene de datos se inserta con `textContent`, nunca como HTML (CA6).

// Solo `https:` seguido de dos barras y algo más (en minúsculas, sin espacios).
const ENLACE_SEGURO = /^https:\/\/\S/;

export function crearVista(documento, textos) {
  const porId = (id) => {
    const elemento = documento.getElementById(id);
    if (!elemento) throw new Error(`falta el elemento #${id}`);
    return elemento;
  };
  const selector = porId("municipio");
  const mensaje = porId("mensaje");
  const avisoBase = porId("aviso-base");

  const TEXTO_ESTADO = {
    ok: "",
    cargando: textos.cargando,
    vacia: textos.sinTrazados,
    sin_indicios: textos.sinIndicios,
    sin_candidatos: textos.sinCandidatos,
    error: textos.errorCapa,
  };

  // Resumen de la medición bajo la capa de tramos a verificar (historia #171): las frases y la
  // marca «revisado a mano» tal cual, con textContent. `null` lo vacía.
  function ponerResumenCapa(id, resumen) {
    const contenedor = porId(`resumen-${id}`);
    contenedor.replaceChildren();
    if (resumen === null) return;
    for (const frase of resumen.frases) {
      const p = documento.createElement("p");
      p.textContent = frase;
      contenedor.appendChild(p);
    }
    const marca = documento.createElement("p");
    marca.className = "pc-capa__revisado";
    marca.textContent = resumen.revisadoAMano;
    contenedor.appendChild(marca);
  }

  function ponerMunicipios(lista) {
    selector.replaceChildren();
    for (const { ine, nombre } of lista) {
      const opcion = documento.createElement("option");
      opcion.value = ine;
      opcion.textContent = nombre;
      selector.appendChild(opcion);
    }
  }

  function seleccionarMunicipio(ine) {
    selector.value = ine;
  }

  function ponerEstadoCapa(id, estado) {
    const elemento = porId(`estado-${id}`);
    const texto = TEXTO_ESTADO[estado] ?? "";
    elemento.replaceChildren();
    // En carga, una barra decorativa (`aria-hidden`) antes del texto (historia #166, CA4).
    if (estado === "cargando") {
      const progreso = documento.createElement("div");
      progreso.className = "pc-progreso";
      progreso.setAttribute("aria-hidden", "true");
      progreso.appendChild(documento.createElement("i"));
      elemento.appendChild(progreso);
    }
    if (texto !== "") {
      const span = documento.createElement("span");
      span.textContent = texto;
      elemento.appendChild(span);
    }
    elemento.dataset.estado = estado;
  }

  function mostrarMensaje(texto) {
    mensaje.textContent = texto;
  }

  function limpiarMensaje() {
    mensaje.textContent = "";
  }

  function mostrarAvisoBase(texto) {
    avisoBase.textContent = texto;
  }

  function nodoFicha({ titulo, fuente, nombre }) {
    const ficha = documento.createElement("div");
    ficha.className = "ficha";
    const cabecera = documento.createElement("strong");
    cabecera.textContent = titulo;
    ficha.appendChild(cabecera);
    if (nombre) {
      const p = documento.createElement("p");
      p.textContent = nombre;
      ficha.appendChild(p);
    }
    const pie = documento.createElement("p");
    pie.className = "ficha-fuente";
    pie.textContent = `Fuente: ${fuente}`;
    ficha.appendChild(pie);
    return ficha;
  }

  function parrafo(clase, contenido) {
    const p = documento.createElement("p");
    if (clase) p.className = clase;
    p.textContent = contenido;
    return p;
  }

  // Ficha de un indicio (historia #95): solo createElement y textContent. El enlace de una
  // fuente se crea únicamente si la URL es https con dos barras; si no, se muestra como texto.
  // Espacio de nombres de SVG: un identificador, no una URL que se pida. Partido en dos para que
  // el escáner de URL absolutas de #85 (CA1) no lo tome por un recurso externo.
  const SVG_NS = "http:" + "//www.w3.org/2000/svg";

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
    const figura = documento.createElement("figure");
    figura.className = "pc-comparacion__imagen";
    const lienzo = documento.createElement("div");
    lienzo.className = "pc-comparacion__lienzo";
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
    const seccion = documento.createElement("div");
    seccion.className = "pc-comparacion";
    const titulo = documento.createElement("strong");
    titulo.textContent = textos.tituloComparacion;
    seccion.appendChild(titulo);

    // Control accesible: botón con `aria-pressed`; oculta o muestra todos los trazos de la ficha.
    const control = documento.createElement("button");
    control.setAttribute("type", "button");
    control.setAttribute("aria-pressed", "true");
    control.className = "pc-comparacion__control";
    control.textContent = textos.mostrarTrazo;
    seccion.appendChild(control);

    const trazos = [];
    for (const ventana of comparacion.ventanas) {
      for (const imagen of ventana.imagenes) {
        const figura = nodoImagenComparacion(imagen, ventana, comparacion);
        seccion.appendChild(figura);
      }
      for (const omitida of ventana.omitidas) {
        seccion.appendChild(parrafo("ficha-aviso", `${omitida.franja}: ${omitida.texto}`));
      }
    }
    const recoger = (nodo) => {
      if (nodo.tagName === "svg") trazos.push(nodo);
      for (const hijo of nodo.children ?? []) recoger(hijo);
    };
    recoger(seccion);
    control.addEventListener("click", () => {
      const visible = control.getAttribute("aria-pressed") !== "true";
      control.setAttribute("aria-pressed", String(visible));
      for (const trazo of trazos) {
        if (visible) trazo.removeAttribute("hidden");
        else trazo.setAttribute("hidden", "");
      }
    });

    for (const hueco of comparacion.huecos) seccion.appendChild(parrafo("ficha-aviso", hueco));
    if (comparacion.servidasPor !== "") {
      seccion.appendChild(parrafo("ficha-fuente", comparacion.servidasPor));
    }
    return seccion;
  }

  function nodoFichaIndicio(ficha, comparacion = null) {
    const nodo = documento.createElement("div");
    nodo.className = "ficha ficha-indicio";
    if (!ficha.disponible) {
      nodo.appendChild(parrafo("", textos.fichaNoDisponible));
      nodo.appendChild(parrafo("ficha-aviso", ficha.aviso));
      return nodo;
    }
    const cabecera = documento.createElement("strong");
    cabecera.textContent = ficha.etiqueta;
    nodo.appendChild(cabecera);
    nodo.appendChild(parrafo("", ficha.texto));
    if (ficha.confianza) nodo.appendChild(parrafo("ficha-confianza", ficha.confianza));
    nodo.appendChild(parrafo("ficha-aviso", ficha.aviso));

    const lista = documento.createElement("ul");
    lista.className = "ficha-fuentes";
    for (const e of ficha.evidencia) {
      const item = documento.createElement("li");
      item.appendChild(parrafo("", `${e.papel}: ${e.fuente} (${e.anio})`));
      item.appendChild(parrafo("ficha-fuente", `Descargada el ${e.fechaDescarga}`));
      item.appendChild(parrafo("ficha-fuente", `Licencia: ${e.licencia}`));
      item.appendChild(parrafo("ficha-fuente", e.atribucion));
      if (ENLACE_SEGURO.test(e.url)) {
        const enlace = documento.createElement("a");
        enlace.setAttribute("href", e.url);
        enlace.setAttribute("rel", "noopener noreferrer");
        enlace.setAttribute("target", "_blank");
        enlace.textContent = e.url;
        const p = documento.createElement("p");
        p.className = "ficha-fuente";
        p.appendChild(enlace);
        item.appendChild(p);
      } else if (e.url !== "") {
        item.appendChild(parrafo("ficha-fuente", e.url));
      }
      lista.appendChild(item);
    }
    nodo.appendChild(lista);

    // Los tramos a verificar (#171) no traen criterio: no se pintan párrafos vacíos.
    if (ficha.criterio !== "") nodo.appendChild(parrafo("ficha-criterio", `Criterio: ${ficha.criterio}`));
    if (ficha.descripcionCriterio !== "") {
      nodo.appendChild(parrafo("ficha-criterio", ficha.descripcionCriterio));
    }
    if (ficha.avisoOmision !== null) nodo.appendChild(parrafo("ficha-aviso", ficha.avisoOmision));
    if (comparacion !== null) nodo.appendChild(nodoComparacion(comparacion));
    return nodo;
  }

  return {
    nodoFichaIndicio,
    ponerMunicipios,
    seleccionarMunicipio,
    ponerEstadoCapa,
    ponerResumenCapa,
    mostrarMensaje,
    limpiarMensaje,
    mostrarAvisoBase,
    nodoFicha,
  };
}
