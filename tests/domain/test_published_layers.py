from pathlib import Path
from typing import get_args

from parcel_intel.domain.published_layers import (
    INDEXED_LAYER_IDS,
    PUBLISHED_LAYERS,
    IndexedLayerId,
    PublishedLayerId,
)

NOTICE = Path(__file__).resolve().parents[2] / "NOTICE"


def test_catalogo_cerrado_de_dos_capas_sin_catastro() -> None:
    assert set(PUBLISHED_LAYERS) == set(get_args(PublishedLayerId))
    assert set(PUBLISHED_LAYERS) == {"vias_pecuarias", "camino_actual"}
    assert all("catastro" not in spec.source for spec in PUBLISHED_LAYERS.values())
    assert all(layer_id == spec.layer_id for layer_id, spec in PUBLISHED_LAYERS.items())


def test_fuentes_de_cada_capa() -> None:
    assert PUBLISHED_LAYERS["vias_pecuarias"].source == "via_pecuaria_oficial"
    assert PUBLISHED_LAYERS["camino_actual"].source == "ign_red_transporte"


def test_la_atribucion_es_literal_de_notice() -> None:
    notice = NOTICE.read_text(encoding="utf-8")

    for spec in PUBLISHED_LAYERS.values():
        assert f"Atribución: `{spec.attribution}`" in notice or (
            f"Atribución declarada por el servicio: `{spec.attribution}`" in notice
        )


def test_capas_del_indice_son_las_de_trazados_mas_los_indicios() -> None:
    """#94 (ADR 0044): la capa de indicios entra en el índice sin entrar en PUBLISHED_LAYERS."""
    assert set(INDEXED_LAYER_IDS) == set(PUBLISHED_LAYERS) | {"discrepancias", "candidatos"}
    assert set(INDEXED_LAYER_IDS) == set(get_args(IndexedLayerId))
    assert list(INDEXED_LAYER_IDS) == sorted(INDEXED_LAYER_IDS)
