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
