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
