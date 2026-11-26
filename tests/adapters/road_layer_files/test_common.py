from datetime import date

from parcel_intel.adapters.road_layer_files.common import provenance_properties
from parcel_intel.domain.provenance import Provenance, Redistribution


def test_la_procedencia_escrita_lleva_la_marca_de_redistribucion() -> None:
    base = Provenance("idem", "https://example.invalid", date(2026, 11, 26), "CC BY 4.0")

    assert provenance_properties(base)["redistribucion"] == "solo_uso_interno"
    public = Provenance(
        "idem", "https://example.invalid", date(2026, 11, 26), "CC BY 4.0", Redistribution.PUBLIC
    )
    assert provenance_properties(public) == {
        "fuente": "idem",
        "url": "https://example.invalid",
        "fecha_descarga": "2026-11-26",
        "licencia": "CC BY 4.0",
        "redistribucion": "publicable",
    }
