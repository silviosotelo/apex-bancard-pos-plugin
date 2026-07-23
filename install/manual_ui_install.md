# Instalación manual por la UI de APEX

Alternativa a usar los exports reales (`install_plugin_apex20.sql` /
`install_plugin_apex24.sql`) — mismo resultado: APEX genera un ID real para
el plugin por el mismo camino que usa para cualquier otro. Esto recorre
**Shared Components → Plug-ins → Create**, paso a paso.

## Paso 1: Crear el plugin

**App Builder → tu aplicación → Shared Components → Plugins → Create**

| Campo | Valor |
|---|---|
| Name | `BANCARD.POS_CLIENTE` |
| Display Name | `POS Bancard - Cobro directo (cliente)` |
| Plug-in Type | Dynamic Action |
| Category | JavaScript |
| API Version | 1 |
| Supported UI Types | Desktop |
| Substitute Attributes | Yes |
| Standard Attributes | (ninguno marcado) |
| Version Identifier | 1.0 |

**Source → PL/SQL Code:**

```plsql
function render
    ( p_dynamic_action in apex_plugin.t_dynamic_action
    , p_plugin         in apex_plugin.t_plugin
    )
return apex_plugin.t_dynamic_action_render_result
is
    l_result apex_plugin.t_dynamic_action_render_result;
begin
    l_result.javascript_function := 'bancardPosCliente.execute';
    l_result.attribute_01 := p_dynamic_action.attribute_01;
    l_result.attribute_02 := p_dynamic_action.attribute_02;
    l_result.attribute_03 := p_dynamic_action.attribute_03;
    l_result.attribute_04 := p_dynamic_action.attribute_04;
    l_result.attribute_05 := p_dynamic_action.attribute_05;
    l_result.attribute_06 := p_dynamic_action.attribute_06;
    l_result.attribute_07 := p_dynamic_action.attribute_07;
    l_result.attribute_08 := p_dynamic_action.attribute_08;
    l_result.attribute_09 := p_dynamic_action.attribute_09;
    l_result.attribute_10 := p_dynamic_action.attribute_10;
    l_result.attribute_11 := p_dynamic_action.attribute_11;
    return l_result;
end render;
```

**Callbacks → Render Function Name:** `render`

**Help Text:**

```
Cobra con un terminal POS Bancard llamando directo desde el navegador del
cajero (fetch al IP/puerto local del terminal), sin depender de ningun
backend particular. Soporta todos los medios de pago del protocolo Bancard
v1.5.0 (tarjeta contado/cuotas/debito forzado/credito forzado, QR, QR PIX,
extraccion QR, canje de puntos, canje QR, billetera electronica). No mapea
ni formatea nada a un esquema de datos especifico de una empresa: expone
issuerId, monto y fecha crudos -cada app consumidora hace su propio
mapeo/formato antes de guardar. Usa SweetAlert2 (empaquetado como archivo
propio del plugin, no via CDN externo) para el loader durante el eco y
durante la espera/lectura del pago. Requiere que el navegador de la
sucursal tenga habilitados, para el sitio de la app (candado de la barra
de direcciones -> Configuracion de sitios), los permisos "Red local" y
"Contenido no seguro", porque el terminal Bancard es HTTP plano y no manda
headers CORS. Compatible con APEX 20.1 en adelante.
```

Guardá el plugin antes de seguir — recién ahí queda con un ID real asignado.

## Paso 2: Subir el archivo JS (dentro del mismo plugin, sección Files)

Archivo a subir: `js/pos_bancard_cliente_bundle.js` (SweetAlert2 + el
runtime del plugin en un solo archivo — **tiene que ser un solo archivo**:
dos archivos separados en `p_javascript_file_urls` se renderizan como un
único `<script src="a.js,b.js">` inválido en vez de dos tags separados, por
eso van empaquetados juntos).

Si la UI te deja renombrarlo, dejalo como `pos_bancard_cliente.js` para que
coincida con:

**JavaScript File URLs:** `#PLUGIN_FILES#pos_bancard_cliente.js`

Si la UI conserva el nombre original del archivo subido
(`pos_bancard_cliente_bundle.js`), ajustá el campo de arriba a
`#PLUGIN_FILES#pos_bancard_cliente_bundle.js` en su lugar — lo que importa
es que el nombre coincida exactamente con el archivo subido.

## Paso 3: Los 11 atributos (Custom Attributes → Create Attribute, uno por uno)

Todos con **Attribute Scope = Component**, **Type = Page Item**, **Is
Translatable = No**. La secuencia define el orden en el panel; usá 10, 20,
30... 110 en orden.

| # | Sequence | Prompt | Oblig. | Help Text |
|---|---|---|---|---|
| 1 | 10 | Item: IP del POS | Yes | Nombre del item que contiene la IP local del terminal Bancard. |
| 2 | 20 | Item: Puerto del POS | Yes | Nombre del item que contiene el puerto del terminal Bancard. |
| 3 | 30 | Item: Medio de Pago | Yes | Nombre del item con el codigo del medio de pago: TARJETA_CONTADO, TARJETA_CUOTAS, TARJETA_DEBITO, TARJETA_CREDITO, QR, QR_PIX, EXTRACCION_QR, CANJE, CANJE_QR o BILLETERA. |
| 4 | 40 | Item: Monto | Yes | Nombre del item con el monto a cobrar, como numero plano (sin separador de miles). Si tu app formatea el monto en pantalla, convertilo a numero antes de que dispare esta accion. |
| 5 | 50 | Item: Datos Adicionales (JSON, opcional) | No | Item con un JSON crudo segun el medio de pago: {"cuotas":N,"plan":N} para TARJETA_CUOTAS/TARJETA_CREDITO, {"billetera":"ZIM","cuenta":"123456"} para BILLETERA, {"pix_payer_cpf":"...","pix_payer_phone":"..."} para QR_PIX, {"montoVuelto":N,"promotions":[...]} opcional para QR. Vacio si el medio no necesita datos extra. |
| 6 | 60 | Item destino: Nro Boleta/Autorizacion | Yes | Item donde se escribe, como string crudo, el nroBoleta (o codigoAutorizacion si no viene nroBoleta) devuelto por el POS. |
| 7 | 70 | Item destino: Issuer ID | Yes | Item donde se escribe el issuerId crudo devuelto por el POS (ej. VD, MC, ZM). El plugin NO lo mapea a ningun codigo de marca de tarjeta interno -cada app hace su propio mapeo contra su propio catalogo, si lo necesita. |
| 8 | 80 | Item destino: Monto Cobrado | Yes | Item donde se escribe el monto cobrado como numero plano (sin formato). Cada app lo formatea segun su propia convencion antes de guardarlo. |
| 9 | 90 | Item destino: Fecha/Hora de la Operacion | Yes | Item donde se escribe la fecha/hora actual en formato ISO 8601 (ej. 2026-07-22T19:13:07.342Z). Cada app la convierte al formato que necesite su proceso de guardado. |
| 10 | 100 | Item destino: Nro de Referencia | Yes | Item donde se escribe el facturaNro generado client-side (Date.now()) para esta transaccion, el numero de referencia que el plugin le paso al POS. |
| 11 | 110 | Item destino: Resultado Completo (JSON, opcional) | No | Item donde se escribe el JSON completo devuelto por el POS, para acceder a campos especificos de cada medio que no tienen item propio (saldo, montoComision, montoRs, nombreCliente, etc.). |

El orden de estos 11 atributos importa: son los que después se ven como
Attribute 1..11 al configurar la acción del plugin en una Dynamic Action, y
`attribute_01..attribute_11` en el `render()` de arriba los pasa en ese
mismo orden. No cambies el orden de creación.

## Paso 4: Verificar

```sql
select plugin_id, name, display_name from apex_appl_plugins
 where application_id = :tu_app_id and name = 'BANCARD.POS_CLIENTE';
```

`PLUGIN_ID` debería salir con un número real de 15-20 dígitos, no un número
chico puesto a mano.
