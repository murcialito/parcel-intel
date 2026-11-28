"""Despacho de ventanas de comparación por vuelo (historia #208, ADR 0052).

Los vuelos `CM_*` de la Comunidad de Madrid van al adapter de la IDEM (#207); el resto, al
WMS histórico del IGN (#124). La misma tabla da la URL canónica que pide la caché cruda y
que el lector del manifiesto exige: vive aquí, y no en `cli/`, para que los dos la
compartan. El enrutado no filtra por la serie: quien la cierra es el dominio
(`COMPARISON_SLOTS`/`FLIGHTS`) y el lector del manifiesto."""

from parcel_intel.adapters.idem_vuelos import window as idem_window
from parcel_intel.adapters.pnoa import window as pnoa_window
from parcel_intel.domain.orthophoto import HistoricalVintage, Orthophoto, OrthophotoWindow
from parcel_intel.ports.orthophoto import OrthophotoWindowPort


def is_idem_vintage(vintage: HistoricalVintage) -> bool:
    return isinstance(vintage, str) and vintage in idem_window.LAYERS


def comparison_window_url(window: OrthophotoWindow, vintage: HistoricalVintage) -> str:
    """URL canónica de la ventana en el servidor de su vuelo: la que pide la caché y la
    única que se publica (ADR 0049 §2, ampliado)."""
    if is_idem_vintage(vintage):
        return idem_window.window_url(window, vintage)
    return pnoa_window.window_url(window, vintage)


class FlightRoutedWindowAdapter:
    """Implementa `OrthophotoWindowPort`: `CM_*` a la IDEM, el resto al IGN. Un vuelo
    desconocido llega al adapter del IGN, que lanza `InvalidHistoricalVintageError`."""

    def __init__(self, ign: OrthophotoWindowPort, idem: OrthophotoWindowPort) -> None:
        self._ign = ign
        self._idem = idem

    def get_orthophoto_window(
        self, window: OrthophotoWindow, vintage: HistoricalVintage
    ) -> Orthophoto:
        if is_idem_vintage(vintage):
            return self._idem.get_orthophoto_window(window, vintage)
        return self._ign.get_orthophoto_window(window, vintage)
