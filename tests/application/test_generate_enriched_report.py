from datetime import date

import pytest

from parcel_intel.application.generate_enriched_report import (
    GenerateEnrichedParcelReportUseCase,
)
from parcel_intel.application.generate_report import GenerateParcelReportUseCase
from parcel_intel.domain.bulletin import BulletinNotice
from parcel_intel.domain.flood_hazard import FloodHazardSample
from parcel_intel.domain.geometry import Geometry, LineGeometry
from parcel_intel.domain.land_classification import LandClassification
from parcel_intel.domain.ndvi import Grid, NdviGrid
from parcel_intel.domain.orthophoto import Orthophoto
from parcel_intel.domain.report import ParcelReport
from parcel_intel.domain.watercourse import Watercourse
from parcel_intel.ports.errors import (
    BulletinNotPublishedError,
    NoLandClassificationFoundError,
    NoScenesAfterCloudFilterError,
)
from tests.factories import make_parcel, make_provenance


class _FakeBaseRepository:
    """Repositorio ya poblado: `GenerateParcelReportUseCase` nunca llega a
    pedirle nada a Catastro, el foco de estos tests es el caso de uso
    enriquecido, no el ya cubierto en `test_generate_report.py`."""

    def __init__(self, cached_report: ParcelReport) -> None:
        self._cached_report = cached_report

    def get_report(self, cadastral_reference: str) -> ParcelReport:
        return self._cached_report

    def save_report(self, report: ParcelReport) -> None:
        raise AssertionError("no debería intentar guardar, el informe ya está cacheado")


class FakeOrthophotoPort:
    def __init__(
        self, orthophoto: Orthophoto | None = None, raises: Exception | None = None
    ) -> None:
        self._orthophoto = orthophoto
        self._raises = raises
        self.calls: list[tuple[Geometry, float]] = []

    def get_current_orthophoto(self, geometry: Geometry, margin_m: float) -> Orthophoto:
        self.calls.append((geometry, margin_m))
        if self._raises is not None:
            raise self._raises
        assert self._orthophoto is not None
        return self._orthophoto

    def get_historical_orthophoto(
        self, geometry: Geometry, margin_m: float, vintage: object
    ) -> Orthophoto:
        raise NotImplementedError


class FakeNdviSeriesPort:
    def __init__(
        self, grids: list[NdviGrid] | None = None, raises: Exception | None = None
    ) -> None:
        self._grids = grids if grids is not None else []
        self._raises = raises
        self.calls: list[tuple[Geometry, float, date, date, float]] = []

    def get_ndvi_series(
        self,
        geometry: Geometry,
        margin_m: float,
        start: date,
        end: date,
        max_cloud_cover_percent: float,
    ) -> list[NdviGrid]:
        self.calls.append((geometry, margin_m, start, end, max_cloud_cover_percent))
        if self._raises is not None:
            raise self._raises
        return self._grids


class FakeBulletinPort:
    def __init__(
        self, notices: list[BulletinNotice] | None = None, raises: Exception | None = None
    ) -> None:
        self._notices = notices if notices is not None else []
        self._raises = raises
        self.calls: list[str] = []

    def get_daily_bulletin(self, day: str) -> list[BulletinNotice]:
        self.calls.append(day)
        if self._raises is not None:
            raise self._raises
        return self._notices


class FakeLandClassificationPort:
    def __init__(
        self,
        classifications: list[LandClassification] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._classifications = classifications if classifications is not None else []
        self._raises = raises
        self.calls: list[tuple[Geometry, float]] = []

    def get_land_classifications(
        self, geometry: Geometry, margin_m: float
    ) -> list[LandClassification]:
        self.calls.append((geometry, margin_m))
        if self._raises is not None:
            raise self._raises
        return self._classifications


class FakeWatercoursePort:
    def __init__(
        self, watercourses: list[Watercourse] | None = None, raises: Exception | None = None
    ) -> None:
        self._watercourses = watercourses if watercourses is not None else []
        self._raises = raises
        self.calls: list[tuple[Geometry, float]] = []

    def get_nearby_watercourses(self, geometry: Geometry, margin_m: float) -> list[Watercourse]:
        self.calls.append((geometry, margin_m))
        if self._raises is not None:
            raise self._raises
        return self._watercourses


class FakeFloodHazardPort:
    def __init__(
        self, samples: list[FloodHazardSample] | None = None, raises: Exception | None = None
    ) -> None:
        self._samples = samples if samples is not None else []
        self._raises = raises
        self.calls: list[tuple[Geometry, float]] = []

    def get_flood_hazard(self, geometry: Geometry, margin_m: float) -> list[FloodHazardSample]:
        self.calls.append((geometry, margin_m))
        if self._raises is not None:
            raise self._raises
        return self._samples


class _UnusedPort:
    """Ni `parcel_port` ni `building_port` deberían llamarse: el repositorio
    ya tiene un informe cacheado, así que `GenerateParcelReportUseCase`
    nunca toca Catastro."""

    def get_parcel(self, cadastral_reference: str) -> object:
        raise AssertionError("no debería llamar a Catastro con informe cacheado")

    def get_buildings(self, cadastral_reference: str) -> object:
        raise AssertionError("no debería llamar a Catastro con informe cacheado")


def _base_use_case() -> GenerateParcelReportUseCase:
    parcel = make_parcel(municipality="COLMENAR DE OREJA")
    unused_port = _UnusedPort()
    return GenerateParcelReportUseCase(
        parcel_port=unused_port,  # type: ignore[arg-type]
        building_port=unused_port,  # type: ignore[arg-type]
        repository=_FakeBaseRepository(cached_report=ParcelReport(parcel=parcel, buildings=())),
    )


def _fixed_today() -> date:
    return date(2026, 10, 15)


def _orthophoto() -> Orthophoto:
    return Orthophoto(image=b"fake-jpeg", vintage="actual", provenance=make_provenance("pnoa"))


def _ndvi_grid(scene_date: date = date(2026, 9, 1)) -> NdviGrid:
    values: Grid = ((0.2, 0.4), (0.6, float("nan")))
    return NdviGrid(
        values=values,
        bbox=(0.0, 0.0, 10.0, 10.0),
        srid=25830,
        scene_date=scene_date,
        cloud_cover_percent=10.0,
        provenance=make_provenance("sentinel2"),
    )


def _notice(title: str = "Convenio con el Ayuntamiento de Colmenar de Oreja") -> BulletinNotice:
    return BulletinNotice(
        identifier="BOCM-20261015-32",
        title=title,
        section_code="I",
        section_name="COMUNIDAD DE MADRID",
        pdf_url="https://example.org/x.pdf",
        provenance=make_provenance("bocm"),
    )


def _land_classification() -> LandClassification:
    return LandClassification(
        general_category="Suelo No Urbanizable Común",
        detailed_category="suelo no urbanizable común",
        short_code="SUBNS",
        reference_date=date(2025, 6, 29),
        municipality_code="043",
        municipality_name="COLMENAR DE OREJA",
        area_m2=1000.0,
        geometry=Geometry(rings=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),), srid=25830),
        provenance=make_provenance("idem"),
    )


def _watercourse() -> Watercourse:
    return Watercourse(
        name="Barranco del Montero",
        hydrographic_demarcation_code="ES030",
        hydrographic_demarcation_name="Tajo",
        course_type="Curso natural",
        persistence="Estacional",
        min_width_m=1.0,
        max_width_m=5.0,
        length_m=2058.58,
        geometry=LineGeometry(points=((0.0, 0.0), (1.0, 1.0)), srid=25830),
        provenance=make_provenance("idee-watercourse"),
    )


def _flood_hazard_samples() -> list[FloodHazardSample]:
    return [
        FloodHazardSample(
            kind="fluvial",
            return_period_years=period,
            water_depth_m=None,
            provenance=make_provenance("idee-flood-hazard"),
        )
        for period in (10, 100, 500)
    ] + [
        FloodHazardSample(
            kind="marina",
            return_period_years=period,
            water_depth_m=None,
            provenance=make_provenance("idee-flood-hazard"),
        )
        for period in (100, 500)
    ]


def test_todas_las_fuentes_disponibles_componen_el_informe_enriquecido() -> None:
    orthophoto_port = FakeOrthophotoPort(orthophoto=_orthophoto())
    ndvi_port = FakeNdviSeriesPort(grids=[_ndvi_grid()])
    boe_port = FakeBulletinPort(notices=[_notice("Disposición sin relación con el municipio")])
    bocm_port = FakeBulletinPort(notices=[_notice()])
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=orthophoto_port,
        ndvi_port=ndvi_port,
        boe_port=boe_port,
        bocm_port=bocm_port,
        land_classification_port=FakeLandClassificationPort(
            classifications=[_land_classification()]
        ),
        watercourse_port=FakeWatercoursePort(watercourses=[_watercourse()]),
        flood_hazard_port=FakeFloodHazardPort(samples=_flood_hazard_samples()),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.orthophoto is not None
    assert enriched.ndvi_summary is not None
    assert enriched.ndvi_summary.mean == pytest.approx((0.2 + 0.4 + 0.6) / 3)
    assert enriched.boe_notices == ()
    assert enriched.bocm_notices == (_notice(),)
    assert boe_port.calls == ["20261015"]
    assert bocm_port.calls == ["20261015"]
    assert enriched.land_classifications == (_land_classification(),)
    assert enriched.watercourses == (_watercourse(),)
    assert enriched.flood_hazard == tuple(_flood_hazard_samples())


def test_fallo_de_idem_no_impide_el_resto_del_informe() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=FakeBulletinPort(notices=[_notice()]),
        bocm_port=FakeBulletinPort(notices=[_notice()]),
        land_classification_port=FakeLandClassificationPort(
            raises=NoLandClassificationFoundError((0.0, 0.0, 1.0, 1.0))
        ),
        watercourse_port=FakeWatercoursePort(watercourses=[_watercourse()]),
        flood_hazard_port=FakeFloodHazardPort(samples=_flood_hazard_samples()),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.land_classifications is None
    assert enriched.orthophoto is not None
    assert enriched.watercourses == (_watercourse(),)
    assert enriched.flood_hazard == tuple(_flood_hazard_samples())


def test_fallo_de_hidrografia_no_impide_el_resto_del_informe() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=FakeBulletinPort(notices=[_notice()]),
        bocm_port=FakeBulletinPort(notices=[_notice()]),
        land_classification_port=FakeLandClassificationPort(
            classifications=[_land_classification()]
        ),
        watercourse_port=FakeWatercoursePort(raises=RuntimeError("timeout")),
        flood_hazard_port=FakeFloodHazardPort(samples=_flood_hazard_samples()),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.watercourses is None
    assert enriched.land_classifications == (_land_classification(),)
    assert enriched.flood_hazard == tuple(_flood_hazard_samples())


def test_sin_cauces_cercanos_devuelve_tupla_vacia_no_none() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=FakeBulletinPort(notices=[_notice()]),
        bocm_port=FakeBulletinPort(notices=[_notice()]),
        land_classification_port=FakeLandClassificationPort(
            classifications=[_land_classification()]
        ),
        watercourse_port=FakeWatercoursePort(watercourses=[]),
        flood_hazard_port=FakeFloodHazardPort(samples=_flood_hazard_samples()),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.watercourses == ()


def test_fallo_de_peligrosidad_inundacion_no_impide_el_resto_del_informe() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=FakeBulletinPort(notices=[_notice()]),
        bocm_port=FakeBulletinPort(notices=[_notice()]),
        land_classification_port=FakeLandClassificationPort(
            classifications=[_land_classification()]
        ),
        watercourse_port=FakeWatercoursePort(watercourses=[_watercourse()]),
        flood_hazard_port=FakeFloodHazardPort(raises=RuntimeError("timeout en una de las 5 capas")),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.flood_hazard is None
    assert enriched.land_classifications == (_land_classification(),)
    assert enriched.watercourses == (_watercourse(),)


def test_fallo_de_pnoa_no_impide_el_resto_del_informe() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(raises=RuntimeError("timeout")),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=FakeBulletinPort(notices=[_notice()]),
        bocm_port=FakeBulletinPort(notices=[_notice()]),
        land_classification_port=FakeLandClassificationPort(
            classifications=[_land_classification()]
        ),
        watercourse_port=FakeWatercoursePort(watercourses=[_watercourse()]),
        flood_hazard_port=FakeFloodHazardPort(samples=_flood_hazard_samples()),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.orthophoto is None
    assert enriched.ndvi_summary is not None
    assert enriched.boe_notices == (_notice(),)
    assert enriched.bocm_notices == (_notice(),)
    assert enriched.report.parcel.municipality == "COLMENAR DE OREJA"


def test_fallo_de_sentinel2_no_impide_el_resto_del_informe() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(
            raises=NoScenesAfterCloudFilterError(
                (0.0, 0.0, 1.0, 1.0), date(2026, 7, 1), date(2026, 10, 15), 40.0
            )
        ),
        boe_port=FakeBulletinPort(notices=[_notice()]),
        bocm_port=FakeBulletinPort(notices=[_notice()]),
        land_classification_port=FakeLandClassificationPort(
            classifications=[_land_classification()]
        ),
        watercourse_port=FakeWatercoursePort(watercourses=[_watercourse()]),
        flood_hazard_port=FakeFloodHazardPort(samples=_flood_hazard_samples()),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.orthophoto is not None
    assert enriched.ndvi_summary is None
    assert enriched.boe_notices == (_notice(),)
    assert enriched.bocm_notices == (_notice(),)


def test_fallo_de_boe_no_impide_el_resto_del_informe() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=FakeBulletinPort(raises=BulletinNotPublishedError("20261015")),
        bocm_port=FakeBulletinPort(notices=[_notice()]),
        land_classification_port=FakeLandClassificationPort(
            classifications=[_land_classification()]
        ),
        watercourse_port=FakeWatercoursePort(watercourses=[_watercourse()]),
        flood_hazard_port=FakeFloodHazardPort(samples=_flood_hazard_samples()),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.orthophoto is not None
    assert enriched.ndvi_summary is not None
    assert enriched.boe_notices is None
    assert enriched.bocm_notices == (_notice(),)


def test_fallo_de_bocm_no_impide_el_resto_del_informe() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=FakeBulletinPort(notices=[_notice()]),
        bocm_port=FakeBulletinPort(raises=BulletinNotPublishedError("20261015")),
        land_classification_port=FakeLandClassificationPort(
            classifications=[_land_classification()]
        ),
        watercourse_port=FakeWatercoursePort(watercourses=[_watercourse()]),
        flood_hazard_port=FakeFloodHazardPort(samples=_flood_hazard_samples()),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.orthophoto is not None
    assert enriched.ndvi_summary is not None
    assert enriched.boe_notices == (_notice(),)
    assert enriched.bocm_notices is None


def test_boletin_sin_coincidencias_devuelve_tupla_vacia_no_none() -> None:
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=FakeBulletinPort(notices=[_notice("Disposición sin relación con el municipio")]),
        bocm_port=FakeBulletinPort(notices=[]),
        land_classification_port=FakeLandClassificationPort(
            classifications=[_land_classification()]
        ),
        watercourse_port=FakeWatercoursePort(watercourses=[_watercourse()]),
        flood_hazard_port=FakeFloodHazardPort(samples=_flood_hazard_samples()),
        today=_fixed_today,
    )

    enriched = use_case.execute("REFCAT-RETIRADA")

    assert enriched.boe_notices == ()
    assert enriched.bocm_notices == ()


def test_dia_consultado_es_el_today_inyectado_no_la_fecha_real() -> None:
    boe_port = FakeBulletinPort(notices=[])
    bocm_port = FakeBulletinPort(notices=[])
    use_case = GenerateEnrichedParcelReportUseCase(
        base_use_case=_base_use_case(),
        orthophoto_port=FakeOrthophotoPort(orthophoto=_orthophoto()),
        ndvi_port=FakeNdviSeriesPort(grids=[_ndvi_grid()]),
        boe_port=boe_port,
        bocm_port=bocm_port,
        land_classification_port=FakeLandClassificationPort(
            classifications=[_land_classification()]
        ),
        watercourse_port=FakeWatercoursePort(watercourses=[_watercourse()]),
        flood_hazard_port=FakeFloodHazardPort(samples=_flood_hazard_samples()),
        today=lambda: date(2020, 1, 1),
    )

    use_case.execute("REFCAT-RETIRADA")

    assert boe_port.calls == ["20200101"]
    assert bocm_port.calls == ["20200101"]
