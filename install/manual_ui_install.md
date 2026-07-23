# Manual installation via the APEX UI (recommended)

Recommended over running the SQL scripts directly — see the "Why not just
run the SQL script?" note in the main README. This walks through creating
the plugin by hand in **Shared Components → Plug-ins → Create**, which is
the same path APEX uses to generate every other plugin's real ID.

## Step 1: Create the plugin

**App Builder → your application → Shared Components → Plugins → Create**

| Field | Value |
|---|---|
| Name | `BANCARD.POS_CLIENTE` |
| Display Name | `POS Bancard - Cobro directo (cliente)` |
| Plug-in Type | Dynamic Action |
| Category | JavaScript |
| API Version | 1 |
| Supported UI Types | Desktop |
| Substitute Attributes | Yes |
| Standard Attributes | (none checked) |
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
Charges a Bancard POS terminal by calling it directly from the cashier's
browser (fetch to the terminal's local IP/port), with no backend in the
middle. Supports every payment method of the Bancard v1.5.0 REST protocol
(cash/installment/forced-debit/forced-credit card, QR, QR PIX, QR
withdrawal, loyalty-point redemption, QR redemption, e-wallet). Does not map
or format anything to a company-specific schema: exposes issuerId, amount
and date raw -- each consuming app does its own mapping/formatting before
saving. Uses SweetAlert2 (bundled as the plugin's own file, not via external
CDN -- works with Content Security Policy enabled and without internet
access on the cashier machine) for the loader during the echo check and
while waiting for/reading the payment. Requires the branch's browser to have
chrome://flags/#block-insecure-private-network-requests disabled and an
"Allow CORS"-type extension installed, because the Bancard terminal is plain
HTTP and doesn't send CORS headers. Compatible with APEX 20.1 onward.
```

Save the plugin before continuing — that's when it gets a real ID assigned.

## Step 2: Upload the JS file (same plugin, Files section)

File to upload: `js/pos_bancard_cliente_bundle.js` (SweetAlert2 + the
plugin's own runtime bundled into a single file — **it needs to be a single
file**: two separate files referenced in `p_javascript_file_urls` render as
one broken `<script src="a.js,b.js">` tag instead of two separate tags,
which is why they're bundled).

If the UI lets you rename the uploaded file, name it
`pos_bancard_cliente.js` to match:

**JavaScript File URLs:** `#PLUGIN_FILES#pos_bancard_cliente.js`

If the UI keeps the original uploaded filename
(`pos_bancard_cliente_bundle.js`), set the field above to
`#PLUGIN_FILES#pos_bancard_cliente_bundle.js` instead — what matters is that
the name matches the uploaded file exactly.

## Step 3: The 11 attributes (Custom Attributes → Create Attribute, one by one)

All with **Attribute Scope = Component**, **Type = Page Item**, **Is
Translatable = No**. Sequence defines the order in the panel; use 10, 20,
30... 110 in order.

| # | Sequence | Prompt | Required | Help Text |
|---|---|---|---|---|
| 1 | 10 | Item: IP del POS | Yes | Name of the item holding the terminal's local IP. |
| 2 | 20 | Item: Puerto del POS | Yes | Name of the item holding the terminal's port. |
| 3 | 30 | Item: Medio de Pago | Yes | Name of the item holding the payment method code: TARJETA_CONTADO, TARJETA_CUOTAS, TARJETA_DEBITO, TARJETA_CREDITO, QR, QR_PIX, EXTRACCION_QR, CANJE, CANJE_QR, or BILLETERA. |
| 4 | 40 | Item: Monto | Yes | Name of the item holding the amount to charge, as a plain number (no thousands separator). If your app formats the on-screen amount, convert it to a number before this action fires. |
| 5 | 50 | Item: Datos Adicionales (JSON, opcional) | No | Item with raw JSON depending on the payment method: {"cuotas":N,"plan":N} for TARJETA_CUOTAS/TARJETA_CREDITO, {"billetera":"ZIM","cuenta":"123456"} for BILLETERA, {"pix_payer_cpf":"...","pix_payer_phone":"..."} for QR_PIX, {"montoVuelto":N,"promotions":[...]} optional for QR. Empty if the method doesn't need extra data. |
| 6 | 60 | Item destino: Nro Boleta/Autorizacion | Yes | Item where the raw string nroBoleta (or codigoAutorizacion if nroBoleta is absent) returned by the POS is written. |
| 7 | 70 | Item destino: Issuer ID | Yes | Item where the raw issuerId returned by the POS is written (e.g. VD, MC, ZM). The plugin does NOT map it to any internal card-brand code -- each app does its own mapping against its own catalog, if it needs one. |
| 8 | 80 | Item destino: Monto Cobrado | Yes | Item where the charged amount is written, as a plain number (unformatted). Each app formats it per its own convention before saving. |
| 9 | 90 | Item destino: Fecha/Hora de la Operacion | Yes | Item where the current date/time is written in ISO 8601 format (e.g. 2026-07-22T19:13:07.342Z). Each app converts it to whatever format its save process needs. |
| 10 | 100 | Item destino: Nro de Referencia | Yes | Item where the client-side generated facturaNro (Date.now()) is written -- the reference number the plugin passed to the POS. |
| 11 | 110 | Item destino: Resultado Completo (JSON, opcional) | No | Item where the full JSON returned by the POS is written, to access method-specific fields that don't have their own item (saldo, montoComision, montoRs, nombreCliente, etc). |

The order of these 11 attributes matters: they're what shows up as
Attribute 1..11 when configuring the plugin's action on a Dynamic Action,
and `attribute_01..attribute_11` in the `render()` above passes them in that
same order. Don't change the creation order.

## Step 4: Verify

```sql
select plugin_id, name, display_name from apex_appl_plugins
 where application_id = :your_app_id and name = 'BANCARD.POS_CLIENTE';
```

`PLUGIN_ID` should come back as a real 15-20 digit number, not a small
manually-typed one.
