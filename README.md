# apex-bancard-pos-plugin

Plugin de Dynamic Action para Oracle APEX que cobra con un terminal físico
**POS Bancard** directo desde el navegador del cajero (`fetch()` al IP/puerto
local del terminal), sin ningún servidor de aplicaciones en el medio.

Bancard es el principal procesador de pagos con tarjeta de Paraguay, así que
este plugin nació pensando en ese mercado — pero el patrón (hablarle a un
terminal POS por REST local desde el navegador, en vez de desde el backend)
sirve igual para cualquier otro protocolo de terminal que exponga una API
HTTP local, adaptando el runtime JS a ese protocolo.

**Genérico a propósito:** no está atado al esquema/datos de ninguna empresa.
No mapea `issuerId` a ningún catálogo interno de marcas de tarjeta, no
formatea monto ni fecha para ningún proceso de guardado en particular —
expone los valores tal cual los devuelve el terminal, y cada app que lo
instale hace su propio mapeo/formato antes de guardar. Esto permite
instalarlo en cualquier aplicación APEX sin tocar el código del plugin.

## Por qué existe

Un backend que hable con el terminal (vía `apex_web_service.make_rest_request`
u otro mecanismo servidor-a-terminal) funciona solo si ese servidor llega por
red a la IP local del terminal — y en muchos casos reales el servidor de
aplicaciones y el terminal están en segmentos de red distintos, así que ese
camino nunca conecta. Este plugin es la vía alternativa: el que sí está en la
misma LAN que el terminal es el navegador del cajero, no el servidor.

Pensado para **coexistir** con una integración servidor-a-servidor existente,
si ya tenés una: usá esa vía donde el servidor llegue al POS, usá este
plugin donde no llegue.

## Cómo funciona

1. El cajero dispara la Dynamic Action (por ejemplo, el click de un botón
   "Cobrar con POS").
2. El JS del plugin (`pos_bancard_cliente.js`) hace `POST /pos/eco` al
   terminal (timeout 5s) para confirmar que está despierto.
3. Según el **Medio de Pago** configurado, llama al endpoint correspondiente
   del terminal (timeout 90s, pensado para dar margen real a que el cliente
   complete la operación) — ver tabla de medios más abajo.
4. Escribe el resultado **crudo** en los items destino configurados,
   disparando su evento `change` (no lo suprime) para que la app pueda
   reaccionar.
5. Todo el feedback visual — loader, éxito, error — se muestra con
   **SweetAlert2**, empaquetado con el plugin (sin CDN externo, sin depender
   de `apex.message`).

No hay ningún round-trip a un servidor de aplicaciones en el medio: todo el
protocolo Bancard corre en el navegador. El número de referencia
(`facturaNro`) se genera con `Date.now()`, sin depender de ninguna secuencia
de base de datos.

## Requisito obligatorio del navegador

El terminal Bancard habla **HTTP plano** y no manda headers CORS. Si la app
se sirve por HTTPS, el navegador bloquea el `fetch()` salvo que se habilite
el sitio, una única vez por máquina de cobro.

**Recomendado — permiso por sitio (no toca la configuración global del navegador):**

1. Con la página de cobro abierta, click en el **candado** de la barra de
   direcciones (ícono del certificado SSL).
2. **Configuración de sitios** (Site settings).
3. Habilitar **"Red local"** (Local network access) y **"Contenido no
   seguro"** (Insecure content) para ese sitio.

Esto es más seguro que las dos alternativas de abajo porque el permiso
queda acotado a ese sitio puntual, no a todo el navegador — no hace falta
instalar ninguna extensión de terceros ni bajar la guardia de Chrome contra
cualquier otro sitio que visite esa máquina.

**Alternativa (navegadores/versiones donde no aparece esa opción):**

1. Ir a `chrome://flags/#block-insecure-private-network-requests` y
   **deshabilitar** ese flag (afecta a *todos* los sitios, no solo el tuyo).
2. Instalar una extensión de Chrome tipo **"Allow CORS"** y activarla (esa
   extensión, una vez activa, afecta a cualquier pestaña — desactivarla
   cuando no se esté usando para cobrar).

Si el plugin muestra un error de "No se pudo conectar al POS", **lo primero
que hay que revisar es esto**, no el terminal. (Esto viene del protocolo del
terminal, no de este plugin — aplica igual en cualquier app que lo instale.
**No aplica** probando contra el simulador incluido, sección "Probar sin
terminal físico": el simulador ya responde los headers CORS correctos.)

## Instalación

### Recomendado: exports reales verificados (sin editar a mano)

`install/install_plugin_apex20.sql` e `install/install_plugin_apex24.sql`
**no son scripts escritos a mano** — son exports reales de Oracle
(**Shared Components → Plugins → Export**), con los datos identificatorios
de origen (workspace/app/owner) reemplazados por placeholders, nada más.
El resto — IDs internos del plugin, los 11 atributos, el JS empaquetado —
es exactamente el export real, byte a byte.

Esto está verificado en la práctica: el de 24.2 se generó **después** de
importar el export de 20.2 en una aplicación APEX completamente distinta —
otra instancia, otro workspace, otra app — vía **Shared Components →
Plugins → Import File**, sin tocar nada a mano, y funcionó sin problema.

Para instalar: editar los 3 valores marcados con `REPLACE` al principio del
script que corresponda a tu versión de APEX (`p_default_workspace_id` /
`p_default_application_id` / `p_default_owner`), y correrlo en **SQL
Workshop → SQL Scripts** (no SQL Commands: el script supera el límite de
32&nbsp;KB).

> **Por qué esto es seguro y escribir el script a mano no lo es.** Un export
> real de Oracle usa un ID interno de 15-20 dígitos para el plugin (en este
> caso `933693839865086367`), generado por la secuencia real de la
> instancia — al reimportarlo, ese número gigante prácticamente no puede
> colisionar con nada. Un script escrito a mano con `wwv_flow_api.id(9201)`
> (un número chico, inventado) sí puede colisionar con algún objeto real y
> viejo de la instancia — y como la metadata de plugins se carga a nivel de
> toda la aplicación (no por página), una sola colisión puede romper Page
> Designer para **toda la app**, en cualquier página, para cualquier
> desarrollador. Esto no es una hipótesis: pasó exactamente así en el
> desarrollo de este plugin, y se resolvió desinstalando con
> `WWV_FLOW_API.REMOVE_PLUGIN` y reinstalando con un export real.

### Alternativa: por la UI de APEX

**Shared Components → Plug-ins → Create Plugin**, cargando los valores a
mano (nombre, función `render`, los 11 atributos, subir el archivo JS). Guía
completa paso a paso, con todos los textos exactos para copiar/pegar:
[`install/manual_ui_install.md`](install/manual_ui_install.md). Tiene el
mismo resultado que usar un export real: APEX genera un ID propio, sin
riesgo de colisión.

### Instalar en otra app / otro workspace

Una vez instalado (por cualquiera de las dos vías de arriba), para llevarlo
a otra app: **Shared Components → Plug-ins →** abrir el plugin **→
Export**, y en la app destino **Shared Components → Plug-ins → Import
File**. APEX resuelve el workspace/app/owner destino automáticamente y
genera un ID real — es el mismo mecanismo verificado en la práctica
(20.2 → 24.2, entre instancias distintas) descrito arriba.

## Cómo integrarlo en una página de cobro

El patrón que funciona de punta a punta tiene **tres piezas** en la misma
Dynamic Action:

1. **Resolver configuración** — acción nativa *Execute Server-side Code*:
   PL/SQL con bind variables que resuelve IP/Puerto/Medio de Pago/Monto
   según la lógica propia de tu app (tabla de terminales, tipo de tarjeta
   elegido, etc.) y los escribe en los items de configuración del plugin.

   > Usar bind variables (`:ITEM`) con "Items to Submit"/"Items to Return"
   > — no `apex_application.g_x01` + `sys.htp.p`. Ese otro patrón es para
   > un **proceso de página Ajax Callback** invocado a mano con
   > `apex.server.process(...)` desde JavaScript — un mecanismo distinto de
   > APEX, con sintaxis distinta. Mezclarlos hace que la acción no setee
   > nada, sin ningún error visible.

2. **La acción del plugin en sí** — la Dynamic Action *POS Bancard - Cobro
   directo (cliente)*, con los 11 atributos mapeados a los items propios de
   tu página.

3. **Mapear el resultado** — un evento **Change** separado (no una tercera
   acción encadenada) sobre uno de los items destino del plugin, que copia
   el resultado crudo a los items reales de tu formulario.

   > Por qué un evento separado y no una tercera acción encadenada: la
   > acción del plugin corre de forma asíncrona (varios `fetch()` con
   > `.then()`) sin avisarle al motor de Dynamic Actions que espere — para
   > APEX, la acción "termina" apenas se dispara, no cuando el POS
   > responde. Una acción encadenada después se ejecutaría de inmediato,
   > antes de tener resultado. El plugin no suprime el evento `change` al
   > setear sus items destino, así que un evento Change separado sobre uno
   > de ellos (por ejemplo, "Nro Boleta") siempre dispara una vez que el
   > resultado realmente está.

### Los 11 atributos del plugin

| # | Atributo | Contenido del item | Oblig. |
|---|---|---|---|
| 1 | Item: IP del POS | IP local del terminal | Sí |
| 2 | Item: Puerto del POS | Puerto del terminal | Sí |
| 3 | Item: Medio de Pago | Código del medio (ver tabla siguiente) | Sí |
| 4 | Item: Monto | Monto a cobrar, **número plano** (sin puntos de miles) | Sí |
| 5 | Item: Datos Adicionales (JSON) | JSON según el medio — ver tabla siguiente | No |
| 6 | Item destino: Nro Boleta/Autorización | `nroBoleta`/`codigoAutorizacion` crudo | Sí |
| 7 | Item destino: Issuer ID | `issuerId` crudo (ej. `VD`, `MC`, `ZM`) — **sin mapear** | Sí |
| 8 | Item destino: Monto Cobrado | Monto cobrado, número plano | Sí |
| 9 | Item destino: Fecha/Hora de la Operación | Fecha/hora en **ISO 8601** | Sí |
| 10 | Item destino: Nro de Referencia | `facturaNro` generado (`Date.now()`) | Sí |
| 11 | Item destino: Resultado Completo (JSON) | Respuesta cruda completa del POS | No |

### Pieza 1 — PL/SQL de ejemplo (adaptar a tu propia tabla de terminales)

```plsql
declare
  l_ip_pos     mi_tabla_terminales.ip_pos%type;
  l_puerto_pos mi_tabla_terminales.puerto_pos%type;
begin
  select t.ip_pos, t.puerto_pos into l_ip_pos, l_puerto_pos
    from mi_tabla_terminales t
   where t.id_sucursal = :P_ID_SUCURSAL
     and t.puesto       = :P_PUESTO
     and t.activo        = 'S';

  :P_POS_IP     := l_ip_pos;
  :P_POS_PUERTO := to_char(l_puerto_pos);
  :P_POS_MEDIO_PAGO := case :P_TIPO_TARJETA
                          when 4 then 'TARJETA_DEBITO'
                          else 'TARJETA_CONTADO'
                        end;
  :P_POS_MONTO_PLANO := trim(replace(:P_MONTO, '.', ''));
exception
  when no_data_found then
    raise_application_error(-20001, 'No hay POS Bancard configurado para este puesto de cobro.');
end;
```

*Items to Submit:* los items que la consulta necesita leer
(`P_ID_SUCURSAL,P_PUESTO,P_TIPO_TARJETA,P_MONTO`).
*Items to Return:* los items que la acción escribe
(`P_POS_IP,P_POS_PUERTO,P_POS_MEDIO_PAGO,P_POS_MONTO_PLANO`).

### Pieza 3 — mapeo del resultado (ejemplo)

**When:** Change · **Selection Type:** Item(s) → el item destino "Nro
Boleta/Autorización" (atributo 6) de la pieza 2. **Action:** Execute
JavaScript Code.

```javascript
function formatMiles(n) {
  n = Math.round(Number(n) || 0);
  return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}
apex.item("MI_ITEM_NRO_CHEQUE_TARJETA").setValue(
  formatMiles(apex.item("P_POS_NRO_BOLETA").getValue())
);
apex.item("MI_ITEM_MONTO").setValue(
  formatMiles(apex.item("P_POS_MONTO_COBRADO").getValue())
);
// El mapeo de marca de tarjeta (issuerId -> catalogo propio) tambien va
// aca, ver "Mapeo aguas abajo" mas abajo.
```

Formatear con separador de miles antes de `setValue()` aplica si tu item
destino usa una máscara tipo `999G999G999G999G999G999G990` (Number Field).
Si tu item es texto libre o numérico sin máscara, alcanza con `setValue()`
directo.

## Medios de pago soportados

| Código (Item: Medio de Pago) | Endpoint(s) Bancard | Datos Adicionales (JSON) |
|---|---|---|
| `TARJETA_CONTADO` | `venta-ux` → `descuento` | — |
| `TARJETA_CUOTAS` | `venta-ux` (con cuotas) → `descuento` | `{"cuotas":N,"plan":N}` |
| `TARJETA_DEBITO` | `venta/debito` → `descuento` | — |
| `TARJETA_CREDITO` | `venta/credito` → `descuento` | `{"cuotas":N,"plan":N}` |
| `QR` | `venta-qr` | `{"montoVuelto":N,"promotions":[...]}` (opcional) |
| `QR_PIX` | `venta-qr-pix` | `{"pix_payer_cpf":"...","pix_payer_phone":"..."}` |
| `EXTRACCION_QR` | `extraccion-qr` | — |
| `CANJE` | `venta-canje` | — |
| `CANJE_QR` | `venta-canje-qr` | — |
| `BILLETERA` | `venta-billetera` | `{"billetera":"ZIM","cuenta":"123456"}` |

`anulacion`/`consulta-anulacion` quedan fuera del plugin a propósito: son
operaciones de gestión post-venta, no medios de pago.

## Mapeo aguas abajo (a cargo de cada app)

Cada empresa mantiene su propio catálogo de marcas de tarjeta (`issuerId →
id_marca_tarjeta` propio). El plugin no lo conoce; el mapeo se hace en la
página, típicamente en el mismo evento "Change" de la pieza 3:

```javascript
var marcaPropia = MI_CATALOGO_MARCAS[ apex.item('P_POS_ISSUER_ID').getValue() ] || 99;
apex.item('MI_ITEM_MARCA_TARJETA').setValue(marcaPropia);

// Lo mismo aplica a formato de fecha: convertir P_POS_FECHA (ISO 8601)
// al formato que tu proceso de guardado espere.
```

Este mapeo es intencionalmente responsabilidad de cada app, no del plugin:
es lo que permite instalar el mismo plugin, sin modificarlo, en cualquier
aplicación con su propio catálogo de marcas y su propio formato de guardado.

## Probar sin terminal físico

`simulator/pos_simulator.py` implementa los 13 endpoints reales del
protocolo Bancard v1.5.0, corre en la misma máquina o en la LAN, sin
dependencias externas (solo Python 3 estándar):

```
python simulator/pos_simulator.py --port 3000 --delay-cliente 5-10 --random
```

- `--delay-cliente N` o `N-M`: simula el tiempo que tarda el cliente en
  completar la operación (número fijo o rango aleatorio, distinto por cada
  venta).
- `--random`: en vez de aprobar siempre, rechaza ventas al azar (fondos
  insuficientes, tarjeta vencida/bloqueada, etc.), hace timeout, o falla el
  propio `/pos/eco` — ajustable con `--fail-rate` / `--timeout-rate` /
  `--eco-fail-rate`.
- `--interactive`: aprobar/rechazar/timeout cada venta por consola, para
  reproducir un caso puntual.

Ver [`simulator/README.md`](simulator/README.md) para la referencia
completa de endpoints y flags. Para probar el plugin solo, sin ninguna app
APEX: [`js/demo.html`](js/demo.html) — dos paneles, formulario de
configuración de la venta (monto, medio de pago, y los campos propios de
cada medio: cuotas/plan, billetera, datos de QR PIX) a la izquierda, y un
mock interactivo del terminal a la derecha que refleja en vivo cada llamada
real del plugin al simulador (conectando, esperando pago, procesando,
aprobada/rechazada) — no es una animación con tiempos fijos.

## Troubleshooting

| Síntoma | Causa probable |
|---|---|
| `Failed to fetch` contra un terminal **real** | Falta habilitar "Red local" + "Contenido no seguro" para el sitio (candado → Configuración de sitios) en esa máquina |
| `Failed to fetch` contra el **simulador** | `--delay-cliente` muy cerca o por encima del timeout del plugin (90s) — bajar el rango del delay |
| "El POS no respondió dentro del tiempo de espera" | Terminal apagado, IP/puerto mal configurados, o (contra el simulador) salió el resultado aleatorio de timeout con `--random` |
| Items de configuración llegan vacíos a la acción del plugin | La acción "Execute Server-side Code" (pieza 1) está escrita con `g_x01`/`sys.htp.p` en vez de bind variables — ver la nota bajo la pieza 1. No tira error, simplemente no setea nada |
| La acción del plugin encadenada después de otra acción async nunca recibe los atributos | Mover el mapeo del resultado a un evento "Change" separado (pieza 3), no una tercera acción encadenada |
| El botón de cobro no aparece/desaparece en vivo según lo que elige el cajero | Una condición *server-side* (PL/SQL) se evalúa solo al renderizar — agregar tu propia Dynamic Action de mostrar/ocultar ligada al cambio de los items relevantes |
| Rompió Page Designer para toda la app (no se puede abrir ninguna Dynamic Action, en ninguna página) | Plugin instalado con un ID chico puesto a mano vía `wwv_flow_api` en vez de un export real o la UI — ver la nota en "Instalación". Desinstalar con `WWV_FLOW_API.REMOVE_PLUGIN` y reinstalar con un export real o por la UI |

## Compatibilidad de versiones de APEX

Desarrollado y probado en APEX 20.2, y **verificado en la práctica** contra
una instancia 24.2 completamente distinta (ver "Instalación" arriba) — el
plugin se importó vía Export/Import sin tocar nada y funcionó de punta a
punta.

- **La API que usa el `render` del plugin** (`apex_plugin.t_dynamic_action`/
  `t_dynamic_action_render_result`) es estable y documentada: los 11
  atributos (`attribute_01`..`attribute_11`) que usa este plugin no
  cambiaron entre 20.1 y 24.2.
- **Lo que sí cambió: el paquete interno que usa el propio export/import de
  Oracle.** El export real de una instancia 20.2 usa `wwv_flow_api.*`; el de
  una instancia 24.2 usa `wwv_flow_imp.*`/`wwv_flow_imp_shared.*` — paquetes
  distintos, con al menos un parámetro que desapareció
  (`p_supported_ui_types`) y uno nuevo que apareció (`p_version_scn`). Esto
  no afecta al plugin en uso (su lógica no cambió), pero si algún día
  necesitás tocar el script de instalación a mano, no asumas que la firma es
  idéntica entre versiones — comparado línea por línea en
  `install/install_plugin_apex20.sql` vs `install/install_plugin_apex24.sql`.
- **SweetAlert2 va empaquetado como archivo propio del plugin**, no cargado
  desde un CDN externo — pensado para instancias con Content Security
  Policy reforzada (documentado por Oracle para APEX 24.2): un `script-src`
  estricto bloquearía un `<script>` apuntando a un CDN externo no permitido
  explícitamente.
- **APEX 24.1 deprecó el switch "Substitute Attribute Values"** para
  plugins de región; no afecta a este plugin, que usa el patrón más simple
  y estable de Dynamic Action (solo `p_render_function`).

## Licencia

MIT — ver [`LICENSE`](LICENSE). SweetAlert2, empaquetado en `js/vendor/`,
también es MIT.
