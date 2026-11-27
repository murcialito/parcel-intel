from parcel_intel.domain.kit_campo import INCIDENCIA_FORM, NOTE_FIELD_LABEL, QFIELD_WARNING


def test_formulario_con_las_listas_aprobadas() -> None:
    assert [o.value for o in INCIDENCIA_FORM.obstacle_types] == [
        "cancela",
        "valla",
        "cadena",
        "zanja",
        "bloques",
        "cartel_prohibido",
        "arado",
        "vegetacion",
    ]
    assert [o.value for o in INCIDENCIA_FORM.states] == [
        "practicable",
        "tapado_vegetacion",
        "con_obstaculo",
        "deteriorado_maquinas",
    ]
    assert INCIDENCIA_FORM.note_label == NOTE_FIELD_LABEL == "Nota corta (sin nombres de personas)"


def test_advertencia_aprobada_literal() -> None:
    assert QFIELD_WARNING.startswith("Anota solo lo que ves del camino")
    assert QFIELD_WARNING.endswith("no denuncia a nadie.")
    assert "este proyecto no envía nada" in QFIELD_WARNING
