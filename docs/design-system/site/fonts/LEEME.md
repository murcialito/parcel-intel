# Tipografías

Paso Común usa la familia **Atkinson Hyperlegible** (Braille Institute, licencia SIL OFL 1.1), pensada para máxima legibilidad: letras con formas muy diferenciadas (I/l/1, 0/O), útil a pleno sol y para personas con baja visión.

Coloca aquí estos tres ficheros (los nombres deben coincidir con `css/tokens.css`):

- `atkinson-hyperlegible-next-400.woff2`
- `atkinson-hyperlegible-next-700.woff2`
- `atkinson-hyperlegible-mono-400.woff2` (coordenadas, fechas, referencias)

## Cómo generarlos (subconjunto latino con ñ y tildes)

Descarga los TTF desde el repositorio oficial del Braille Institute o desde el paquete OFL de Google Fonts (una sola vez, en tu equipo) y ejecuta:

```sh
pip install fonttools brotli
UNICODES="U+0000-00FF,U+0131,U+0152-0153,U+2013-2014,U+2018-201E,U+2022,U+2026,U+20AC"
pyftsubset AtkinsonHyperlegibleNext-Regular.ttf --unicodes="$UNICODES" --flavor=woff2 --layout-features='kern,liga,tnum' --output-file=atkinson-hyperlegible-next-400.woff2
pyftsubset AtkinsonHyperlegibleNext-Bold.ttf    --unicodes="$UNICODES" --flavor=woff2 --layout-features='kern,liga,tnum' --output-file=atkinson-hyperlegible-next-700.woff2
pyftsubset AtkinsonHyperlegibleMono-Regular.ttf --unicodes="$UNICODES" --flavor=woff2 --output-file=atkinson-hyperlegible-mono-400.woff2
```

Cada fichero debería quedar en torno a 15-25 KB. Incluye el `OFL.txt` de la fuente junto a los WOFF2.

Si faltan los ficheros, el sitio sigue funcionando con la fuente del sistema (`system-ui`).
