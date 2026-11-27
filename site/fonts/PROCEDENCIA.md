# Procedencia de las tipografías

Atkinson Hyperlegible (Braille Institute), alojada en el propio sitio: el navegador no pide nada a terceros.

| Fichero | Origen | Licencia |
|---|---|---|
| `atkinson-hyperlegible-next-400.woff2` | `AtkinsonHyperlegibleNext-Regular.ttf` | SIL OFL 1.1 |
| `atkinson-hyperlegible-next-700.woff2` | `AtkinsonHyperlegibleNext-Bold.ttf` | SIL OFL 1.1 |
| `atkinson-hyperlegible-mono-400.woff2` | `AtkinsonHyperlegibleMono-Regular.ttf` | SIL OFL 1.1 |

- **Fuente**: repositorios oficiales de Google Fonts / Braille Institute.
  - Next: https://github.com/googlefonts/atkinson-hyperlegible-next (rama `main`, commit `7925f50f649b3813257faf2f4c0b381011f434f1`).
  - Mono: https://github.com/googlefonts/atkinson-hyperlegible-next-mono (rama `main`, commit `154d50362016cc3e873eb21d242cd0772384c8f9`).
- **URL de descarga**:
  - https://github.com/googlefonts/atkinson-hyperlegible-next/archive/refs/heads/main.zip
  - https://github.com/googlefonts/atkinson-hyperlegible-next-mono/archive/refs/heads/main.zip
- **Fecha de descarga**: 2026-11-26.
- **Versión de la fuente**: 2.001 (campo `name` ID 5 de los tres ficheros).
- **Licencia**: SIL OFL 1.1. Texto en `OFL.txt` (copia del `OFL.txt` del repositorio de Next; el de Mono es la misma licencia).
- **Comando de subconjunto** (`fonttools` y `brotli` solo en la generación, no están en `pyproject.toml`):

```sh
UNICODES="U+0000-00FF,U+0131,U+0152-0153,U+2013-2014,U+2018-201E,U+2022,U+2026,U+20AC"
uv run --no-project --with fonttools --with brotli pyftsubset AtkinsonHyperlegibleNext-Regular.ttf --unicodes="$UNICODES" --flavor=woff2 --layout-features='kern,liga,tnum' --output-file=atkinson-hyperlegible-next-400.woff2
uv run --no-project --with fonttools --with brotli pyftsubset AtkinsonHyperlegibleNext-Bold.ttf    --unicodes="$UNICODES" --flavor=woff2 --layout-features='kern,liga,tnum' --output-file=atkinson-hyperlegible-next-700.woff2
uv run --no-project --with fonttools --with brotli pyftsubset AtkinsonHyperlegibleMono-Regular.ttf --unicodes="$UNICODES" --flavor=woff2 --output-file=atkinson-hyperlegible-mono-400.woff2
```

- **Volcados de codepoints**: `cmap-next-400.txt`, `cmap-next-700.txt` y `cmap-mono-400.txt` listan los codepoints que cada WOFF2 cubre de verdad (uno por línea, `U+XXXX`), generados con `fontTools` a partir de los propios WOFF2.

## Hallazgo: las flechas no están en la fuente oficial

La versión 2.001 oficial de Next y de Mono **no incluye** U+2190-2193 (← ↑ → ↓), ni U+00AD ni U+00B5. Se comprobó sobre el TTF completo, no solo sobre el subconjunto. No se han añadido glifos propios. Por decisión del fundador, el `unicode-range` de `tokens.css` los excluye (las flechas y, en las Next, también U+00AD y U+00B5) y se pintan con la fuente del sistema (`system-ui` está en la pila).
