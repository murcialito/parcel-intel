# ADR 0053 — Dominio propio pasocomun.org para el sitio

- Estado: aceptada
- Fecha: 2026-11-27
- Historia: #227 (épica #2). Amplía el ADR 0022 (despliegue en GitHub Pages) y aplica la regla de CLAUDE.md sobre componentes con coste recurrente.

## Contexto

El sitio se publica con GitHub Pages en `https://murcialito.github.io/paso-comun/`. Esa dirección depende del usuario de GitHub del fundador y del nombre del repo: si cualquiera de los dos cambia, se rompen los enlaces que ya compartimos (`?municipio=…&tramo=…`, y en el futuro los dossiers). Además, ante ayuntamientos y asociaciones, una dirección propia es más clara. El fundador registró `pasocomun.org` el 2026-11-27. Un dominio tiene coste anual: CLAUDE.md exige un ADR con estimación.

## Decisión

1. **El sitio se sirve en `https://pasocomun.org/`** (apex). `www.pasocomun.org` es un `CNAME` a `murcialito.github.io` y GitHub lo redirige al apex.
2. **El dominio se fija en los ajustes de Pages del repo, no con un fichero `CNAME`.** El sitio se publica con un workflow propio (`desplegar.yml`, `build_type: workflow`), y en ese modo GitHub no usa ni necesita `CNAME` (documentación de Pages, consultada el 2026-11-27). `desplegar.yml` no cambia.
3. **Las rutas del sitio siguen siendo relativas.** Solo `og:url` y `og:image` de `index.html` son absolutas, y apuntan al dominio. Un test de aceptación (#227) falla si en `site/` aparece `murcialito.github.io` o el prefijo `/paso-comun/`; las URLs de `github.com/murcialito/paso-comun` (repo, issues) se quedan.
4. **La URL antigua redirige.** Con el dominio fijado, GitHub responde a `https://murcialito.github.io/paso-comun/…` con un 301 a `https://pasocomun.org/…`. Los enlaces ya compartidos siguen funcionando mientras el repo conserve su nombre y el dominio esté configurado.
5. **El repo y el paquete no se renombran**: `murcialito/paso-comun` y `parcel_intel`.

## Coste

| Concepto | Importe | Fuente y fecha de consulta |
|---|---|---|
| Registrador | OVH sas (IANA 433) | RDAP del registro .org, `https://rdap.publicinterestregistry.org/rdap/domain/pasocomun.org`, 2026-11-27 |
| Primer año | 8 € según el fundador; la página del registrador muestra 7,99 € + IVA («Oferta») | `https://www.ovhcloud.com/es-es/domains/tld/org/`, 2026-11-27 |
| Renovación anual | 13,99 € + IVA | `https://www.ovhcloud.com/es-es/domains/tld/org/`, 2026-11-27 |
| Alojamiento, certificado HTTPS, DNS | 0 € (GitHub Pages en repo público; DNS del registrador) | — |

Alta el 2026-11-27, caducidad el 2027-11-27 (RDAP). El coste recurrente es solo la renovación del dominio; lo paga el fundador. Sigue sin haber backend ni cuentas de pago. Las cifras de precio son las de la consulta del 2026-11-27 y caducan: se revisan al renovar. La página del registrador no da importes con IVA, y este ADR no inventa el de la factura.

## Riesgos y mitigación

- **Caducidad y toma del dominio.** Si no se renueva, el sitio cae y un tercero puede registrar el dominio y servir otra cosa bajo enlaces que ya circulan. Mitigación: renovación automática en el registrador; revisar la fecha de caducidad (2027-11-27) cada año.
- **Toma en Pages sin verificar.** Un dominio apuntado a Pages pero no verificado puede reclamarlo otro repo de Pages si este deja de usarlo. Mitigación: dominio verificado en la cuenta de GitHub (registro `TXT`) antes de fijarlo en el repo, y ningún registro comodín (`*`) en la zona, que GitHub desaconseja porque expone a la toma aun verificado.
- **Transferencia o secuestro.** Mitigación: bloqueo de transferencia en el registrador y DNSSEC activado (el 2026-11-27 la delegación aún no estaba firmada).
- **Datos del titular.** Ocultos en el whois del registrador. Este ADR y el repo no recogen ningún dato del titular.
- **Vista previa social** mientras el DNS no resuelve: `og:url` apunta al dominio; sin efecto en el visor.

## Relación con #104 (avisos con foto)

El dominio permite un buzón del proyecto (p. ej. `avisos@pasocomun.org`, reenviado a una cuenta existente) para la opción a2 de #104. Este ADR **no decide** cómo se reciben los avisos: sigue pendiente del fundador en #104. El fundador ya creó `contacto@pasocomun.org` (cuenta Zimbra incluida con el dominio según la guía de OVH, consultada el 2026-11-27; OVH no garantiza que siga siendo gratis). Eso queda como opción disponible, no como decisión.

## Consecuencias

- La configuración del dominio (DNS, verificación, ajustes de Pages, HTTPS) la hace el fundador con su cuenta; ningún agente la toca.
- Si una pieza futura necesita la URL absoluta del sitio (dossier, enlaces impresos), la define una sola vez en el código, con este valor, en lugar de copiarla.
- Si un día se abandona el dominio, hay que quitarlo antes de los ajustes de Pages (para que la URL antigua deje de redirigir) y mantenerlo registrado un tiempo para que no lo tome un tercero.
- Alternativa descartada: seguir en `murcialito.github.io/paso-comun/` (gratis, pero ata los enlaces al usuario y al nombre del repo).
