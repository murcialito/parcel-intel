Fixtures **sintéticas** con el formato de las respuestas de Catastro (historia #45, ADR 0033): no son respuestas de Catastro ni cartografía catastral.
Se regeneran con `uv run python -m tests.fixtures.generate_catastro` y se comprueban con `uv run python -m tests.fixtures.generate_catastro --check`.
No se editan a mano: se cambia el generador (`tests/fixtures/generate_catastro.py`) y se regeneran.
