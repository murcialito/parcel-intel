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
    error: textos.errorCapa,
  };

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
    elemento.textContent = TEXTO_ESTADO[estado] ?? "";
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
  function nodoFichaIndicio(ficha) {
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

    nodo.appendChild(parrafo("ficha-criterio", `Criterio: ${ficha.criterio}`));
    nodo.appendChild(parrafo("ficha-criterio", ficha.descripcionCriterio));
    if (ficha.avisoOmision !== null) nodo.appendChild(parrafo("ficha-aviso", ficha.avisoOmision));
    return nodo;
  }

  return {
    nodoFichaIndicio,
    ponerMunicipios,
    seleccionarMunicipio,
    ponerEstadoCapa,
    mostrarMensaje,
    limpiarMensaje,
    mostrarAvisoBase,
    nodoFicha,
  };
}
