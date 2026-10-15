from parcel_intel.ports.errors import InvalidCadastralReferenceError

_COMPACT_LENGTH = 14
_FULL_LENGTH = 20


def to_compact_reference(reference: str) -> str:
    """Normaliza una referencia catastral a su forma compacta de 14 caracteres.

    Los servicios de Catastro verificados en REGISTRY.md (Consulta_CPMRC, y el
    `nationalCadastralReference` que devuelve el WFS) usan la forma compacta
    `pc1(7) + pc2(7)`, sin el `car` (4) ni el checksum (2) del formato completo
    de 20 caracteres. Si ya viene en 14, se devuelve tal cual.
    """
    cleaned = reference.strip().upper()
    if len(cleaned) == _COMPACT_LENGTH:
        return cleaned
    if len(cleaned) == _FULL_LENGTH:
        return cleaned[:_COMPACT_LENGTH]
    raise InvalidCadastralReferenceError(reference)
