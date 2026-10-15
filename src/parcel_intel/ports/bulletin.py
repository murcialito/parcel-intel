from typing import Protocol

from parcel_intel.domain.bulletin import BulletinNotice


class OfficialBulletinPort(Protocol):
    """Capacidad: sumario completo de un boletín oficial para un día dado.

    Un solo método, sin filtrar (ADR 0008): el filtro por texto es
    `domain.bulletin.filter_by_title`, una función pura sin E/S — separarlo
    del port permite comprobar el mismo sumario ya obtenido contra varios
    municipios sin una segunda petición de red.
    """

    def get_daily_bulletin(self, day: str) -> list[BulletinNotice]:
        """`day` en formato `AAAAMMDD`. Un día por llamada."""
        ...
