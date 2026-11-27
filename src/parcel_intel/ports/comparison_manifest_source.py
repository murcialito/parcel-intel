from typing import Protocol

from parcel_intel.domain.comparison_image import ComparisonManifest


class ComparisonManifestSource(Protocol):
    """Capacidad: leer el manifiesto completo de imágenes de comparación de un municipio
    (#122; lo consume #172, ADR 0049). `None` = sin manifiesto. Ilegible, con otro
    formato, de otro municipio o con una URL fuera de la lista blanca:
    `ComparisonManifestFileError`."""

    def get_manifest(self, municipality_code: str) -> ComparisonManifest | None: ...
