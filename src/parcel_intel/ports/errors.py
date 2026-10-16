class InvalidCadastralReferenceError(Exception):
    """La referencia catastral no tiene un formato reconocible (14 o 20 caracteres)."""

    def __init__(self, reference: str) -> None:
        super().__init__(f"Referencia catastral con formato no reconocido: {reference!r}")
        self.reference = reference


class ParcelNotFoundError(Exception):
    """No existe ninguna parcela para la referencia catastral dada."""

    def __init__(self, reference: str) -> None:
        super().__init__(
            f"No se encontró ninguna parcela para la referencia catastral: {reference!r}"
        )
        self.reference = reference


class ParcelNotCachedError(Exception):
    """No hay ningún informe cacheado para la referencia catastral dada.

    Señal de "cache miss" para `ParcelRepositoryPort.get_report` (ver ADR
    0005) — vive aquí, no en `adapters/postgis/`, porque `application/`
    necesita capturarla y solo puede importar `ports`/`domain`.
    """

    def __init__(self, reference: str) -> None:
        super().__init__(
            f"No hay ningún informe cacheado para la referencia catastral: {reference!r}"
        )
        self.reference = reference


class InvalidHistoricalVintageError(Exception):
    """El año o vuelo histórico pedido no está entre los confirmados en REGISTRY.md."""

    def __init__(self, vintage: object) -> None:
        super().__init__(f"Año o vuelo histórico no reconocido: {vintage!r}")
        self.vintage = vintage


class NoScenesAfterCloudFilterError(Exception):
    """Ninguna escena de Sentinel-2 encontrada para el bbox/rango de fechas
    pedidos pasa el umbral de nubosidad."""

    def __init__(
        self,
        bbox: tuple[float, float, float, float],
        start: object,
        end: object,
        max_cloud_cover_percent: float,
    ) -> None:
        super().__init__(
            f"Ninguna escena Sentinel-2 por debajo de {max_cloud_cover_percent}% de nubes "
            f"para bbox={bbox}, rango {start}..{end}"
        )
        self.bbox = bbox
        self.start = start
        self.end = end
        self.max_cloud_cover_percent = max_cloud_cover_percent


class InvalidBulletinDayError(Exception):
    """El día pedido no tiene formato AAAAMMDD válido (longitud, no numérico,
    o fecha de calendario inexistente). Se lanza antes de cualquier petición
    de red."""

    def __init__(self, day: str) -> None:
        super().__init__(f"Día de boletín con formato no reconocido: {day!r}")
        self.day = day


class BulletinNotPublishedError(Exception):
    """No hay sumario publicado para el día pedido (fin de semana, festivo, o
    fecha futura todavía sin publicar) — el proveedor no distingue estos
    casos (confirmado real en REGISTRY.md), así que tampoco este cliente."""

    def __init__(self, day: str) -> None:
        super().__init__(f"No hay sumario de boletín publicado para el día: {day!r}")
        self.day = day


class NoLandClassificationFoundError(Exception):
    """Ningún polígono de clasificación de suelo intersecta el bbox pedido.
    El servicio no distingue "fuera de cobertura de la Comunidad de Madrid"
    de "hueco real dentro de la cobertura" — confirmado real en
    REGISTRY.md (ambos casos devuelven una FeatureCollection vacía
    idéntica, 200 OK, 0 features) — así que tampoco este cliente los
    distingue."""

    def __init__(self, bbox: tuple[float, float, float, float]) -> None:
        super().__init__(f"Ninguna clasificación de suelo encontrada para el bbox: {bbox}")
        self.bbox = bbox
