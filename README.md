# apex-bancard-pos-plugin

Oracle APEX Dynamic Action plugin that charges a physical **Bancard POS
terminal** directly from the cashier's browser (`fetch()` to the terminal's
local IP/port), with no application server in the middle.

**Generic by design:** not tied to any company's schema or data model. It
doesn't map `issuerId` to any internal card-brand catalog, and doesn't
format amount or date for any particular save process — it exposes the raw
values the terminal returns, and each app that uses it does its own
mapping/formatting before persisting. This means you can install it in any
APEX application without touching the plugin's code.

## Why this exists

A backend that talks to the terminal (via `apex_web_service.make_rest_request`
or any other server-to-terminal mechanism) only works if that server can
reach the terminal's local IP over the network — and in many real setups the
application server and the POS terminal sit on different network segments,
so that path never connects.

This plugin is the alternative path: the machine that *is* on the same LAN
as the terminal is the cashier's browser, not the server. Meant to
**coexist** with an existing server-to-server integration, if you have one:
use that path where the server can reach the POS, use this plugin where it
can't.

## How it works

1. The cashier triggers the Dynamic Action (e.g. clicking a "Charge with
   POS" button).
2. The plugin's JS (`pos_bancard_cliente.js`) does `POST /pos/eco` to the
   terminal (5s timeout) to confirm it's awake.
3. Depending on the configured **Medio de Pago** (payment method), it calls
   the corresponding terminal endpoint (90s timeout, to give a real customer
   time to complete the transaction) — see the payment methods table below.
4. Writes the raw result into the configured destination items, firing their
   `change` event (not suppressed) so the consuming app can react.
5. All visual feedback — loading, success, error — is shown with
   **SweetAlert2**, bundled with the plugin (no external CDN, doesn't depend
   on `apex.message`).

There's no round-trip to an application server in between — the whole
Bancard protocol runs in the browser. `Date.now()` generates the
`facturaNro` (reference number), with no dependency on any database
sequence.

## Mandatory browser requirement

The Bancard terminal speaks **plain HTTP** and doesn't send CORS headers. If
your app is served over HTTPS, the browser will always block the `fetch()`
with a CORS/mixed-content error unless, once per cashier machine:

1. Go to `chrome://flags/#block-insecure-private-network-requests` and
   **disable** that flag.
2. Install a Chrome extension like **"Allow CORS"** and enable it.

If the plugin shows a "could not connect to POS" error, **this is the first
thing to check**, not the terminal. (This requirement comes from the
terminal's protocol, not from this plugin — it applies the same regardless
of which app installs it. It does **not** apply when testing against the
included simulator — see below, the simulator already answers proper CORS
headers.)

## Installation

### Recommended: through the APEX UI

**Shared Components → Plug-ins → Create Plugin**, filling in the fields by
hand using the reference values in [`install/manual_ui_install.md`](install/manual_ui_install.md)
(exact field values, PL/SQL `render` function code, the 11 custom
attributes, and which file to upload).

This is the recommended path because APEX generates a real internal ID for
the plugin through the same path every other plugin uses — no risk of ID
collisions.

> **Why not just run the SQL script?** The `install/*.sql` scripts use
> `wwv_flow_api.create_plugin`/`create_plugin_attribute` with manually
> chosen IDs (`p_id=>wwv_flow_api.id(N)`, offset 0). In practice, manually
> assigned IDs can end up as literal small numbers instead of a real
> APEX-generated ID (every other plugin in a real app has a 15-20 digit ID).
> A small, hand-picked ID can collide with something else in the instance's
> internal ID space, and — since plugin metadata is loaded application-wide,
> not per-page — a single bad ID can break Page Designer for an entire
> application. Installing through the UI avoids this entirely, since it's
> the same code path Oracle uses to generate every other plugin's ID.

### Alternative: SQL scripts

Three near-identical scripts, one per APEX version line (only `p_release`
differs):

| Script | Target |
|---|---|
| `install/install_plugin_apex20.sql` | APEX 20.x |
| `install/install_plugin_apex22.sql` | APEX 22.x |
| `install/install_plugin_apex24.sql` | APEX 24.x+ |

Edit `p_default_workspace_id` / `p_default_application_id` / `p_default_owner`
at the top of the script to match your target instance before running it in
**SQL Workshop → SQL Scripts** (not SQL Commands — the script is larger than
the 32 KB SQL Commands limit).

### Installing into another app / another schema

Once installed anywhere, the standard APEX way to move it: **Shared
Components → Plug-ins →** open the plugin **→ Export**, then in the target
app **Shared Components → Plug-ins → Import File**. APEX resolves the
target workspace/app/owner automatically and generates a real ID — same
mechanism used to install any third-party plugin.

## Integrating it into a charge/payment page

The pattern that ends up working end-to-end has **three pieces** in the same
Dynamic Action:

1. **Resolve configuration** — a native *Execute Server-side Code* action:
   PL/SQL with bind variables that resolves IP/Port/Payment Method/Amount
   according to your own app's logic (terminal lookup table, selected card
   type, etc.) and writes them into the plugin's configuration items.

   > Use bind variables (`:ITEM_NAME`) with "Items to Submit" / "Items to
   > Return" — not `apex_application.g_x01` + `sys.htp.p`. That other
   > pattern is for a page-level Ajax Callback **process** invoked by hand
   > via `apex.server.process(...)` from JavaScript — a different APEX
   > mechanism with different syntax. Mixing them up means the action
   > silently sets nothing, with no visible error.

2. **The plugin's own action** — the Dynamic Action *POS Bancard - Cobro
   directo (cliente)*, with the 11 attributes mapped to your page's items.

3. **Map the result** — a **separate Change event** (not a third chained
   action) on one of the plugin's destination items, that copies the raw
   result into your form's real fields.

   > Why a separate event and not a third chained action: the plugin's own
   > action runs asynchronously (several `fetch()` calls with `.then()`)
   > without telling the Dynamic Action engine to wait — as far as APEX is
   > concerned, the action "finishes" as soon as it's triggered, not when
   > the POS responds. A chained action right after it would run
   > immediately, before there's any result. The plugin does **not**
   > suppress the `change` event when it sets its destination items, so
   > binding a separate Change-triggered action on one of them (e.g. the
   > "Nro Boleta" item) always fires once — and only once — a result is
   > actually in.

### The plugin's 11 attributes

| # | Attribute | Item content | Required |
|---|---|---|---|
| 1 | Item: IP del POS | Terminal's local IP | Yes |
| 2 | Item: Puerto del POS | Terminal's port | Yes |
| 3 | Item: Medio de Pago | Payment method code (see table below) | Yes |
| 4 | Item: Monto | Amount to charge, **plain number** (no thousands separator) | Yes |
| 5 | Item: Datos Adicionales (JSON) | JSON depending on the method — see table below. Leave empty if the method doesn't need it. | No |
| 6 | Item destino: Nro Boleta/Autorización | raw `nroBoleta` / `codigoAutorizacion` | Yes |
| 7 | Item destino: Issuer ID | raw `issuerId` (e.g. `VD`, `MC`, `ZM`) — **not mapped** to any catalog | Yes |
| 8 | Item destino: Monto Cobrado | Charged amount, plain number | Yes |
| 9 | Item destino: Fecha/Hora de la Operación | Timestamp in **ISO 8601** | Yes |
| 10 | Item destino: Nro de Referencia | generated `facturaNro` (`Date.now()`) | Yes |
| 11 | Item destino: Resultado Completo (JSON) | full raw POS response | No |

### Piece 1 — example PL/SQL (adapt to your own terminal-lookup table)

```plsql
declare
  l_ip_pos     my_terminals_table.ip_pos%type;
  l_puerto_pos my_terminals_table.puerto_pos%type;
begin
  select t.ip_pos, t.puerto_pos into l_ip_pos, l_puerto_pos
    from my_terminals_table t
   where t.branch_id = :P_BRANCH_ID
     and t.register   = :P_REGISTER
     and t.active      = 'Y';

  :P_POS_IP     := l_ip_pos;
  :P_POS_PUERTO := to_char(l_puerto_pos);
  :P_POS_MEDIO_PAGO := case :P_CARD_TYPE
                          when 'DEBIT' then 'TARJETA_DEBITO'
                          else 'TARJETA_CONTADO'
                        end;
  :P_POS_MONTO_PLANO := trim(replace(:P_AMOUNT, '.', ''));
exception
  when no_data_found then
    raise_application_error(-20001, 'No POS terminal configured for this register.');
end;
```

*Items to Submit:* the items the query needs to read (`P_BRANCH_ID,P_REGISTER,P_CARD_TYPE,P_AMOUNT`).
*Items to Return:* the items the action writes (`P_POS_IP,P_POS_PUERTO,P_POS_MEDIO_PAGO,P_POS_MONTO_PLANO`).

### Piece 3 — example result mapping

**When:** Change · **Selection Type:** Item(s) → the "Nro Boleta/Autorización"
destination item (attribute 6) from piece 2. **Action:** Execute JavaScript
Code.

```javascript
function formatThousands(n) {
  n = Math.round(Number(n) || 0);
  return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}
apex.item("MY_RECEIPT_NUMBER_ITEM").setValue(
  formatThousands(apex.item("P_POS_NRO_BOLETA").getValue())
);
apex.item("MY_AMOUNT_ITEM").setValue(
  formatThousands(apex.item("P_POS_MONTO_COBRADO").getValue())
);
// Card-brand mapping (issuerId -> your own catalog) also goes here,
// see "Downstream mapping" below.
```

Formatting with a thousands separator before `setValue()` applies if your
destination item uses a mask like `999G999G999G999G999G999G990` (Number
Field). If your item is free text or an unmasked number, a plain
`setValue()` is enough.

## Supported payment methods

| Code (Item: Medio de Pago) | Bancard endpoint(s) | Datos Adicionales (JSON) |
|---|---|---|
| `TARJETA_CONTADO` | `venta-ux` → `descuento` | — |
| `TARJETA_CUOTAS` | `venta-ux` (installments) → `descuento` | `{"cuotas":N,"plan":N}` |
| `TARJETA_DEBITO` | `venta/debito` → `descuento` | — |
| `TARJETA_CREDITO` | `venta/credito` → `descuento` | `{"cuotas":N,"plan":N}` |
| `QR` | `venta-qr` | `{"montoVuelto":N,"promotions":[...]}` (optional) |
| `QR_PIX` | `venta-qr-pix` | `{"pix_payer_cpf":"...","pix_payer_phone":"..."}` |
| `EXTRACCION_QR` | `extraccion-qr` | — |
| `CANJE` | `venta-canje` | — |
| `CANJE_QR` | `venta-canje-qr` | — |
| `BILLETERA` | `venta-billetera` | `{"billetera":"ZIM","cuenta":"123456"}` |

`anulacion`/`consulta-anulacion` (void/query receipts) are deliberately out
of scope — they're post-sale management operations, not payment methods.

## Downstream mapping (each app's own responsibility)

Each company keeps its own card-brand catalog (`issuerId → internal brand
id`). The plugin doesn't know it; the mapping happens in the page, typically
in the same "Change" event from piece 3:

```javascript
var myBrand = MY_BRAND_CATALOG[ apex.item('P_POS_ISSUER_ID').getValue() ] || 99;
apex.item('MY_CARD_BRAND_ITEM').setValue(myBrand);

// Same applies to date formatting: convert P_POS_FECHA (ISO 8601)
// to whatever format your save process expects.
```

This is intentionally each app's responsibility, not the plugin's — it's
what lets the same, unmodified plugin be installed in any application, with
its own brand catalog and its own save format.

## Testing without a physical terminal

`simulator/pos_simulator.py` implements all 13 real Bancard protocol
endpoints, runs on the same machine or over the LAN, no external
dependencies (standard Python 3 only):

```
python simulator/pos_simulator.py --port 3000 --delay-cliente 5-10 --random
```

- `--delay-cliente N` or `N-M`: simulates how long a real customer takes to
  complete the transaction (fixed value or random range).
- `--random`: instead of always approving, randomly rejects, times out, or
  fails the `/pos/eco` check — tunable with `--fail-rate` / `--timeout-rate`
  / `--eco-fail-rate`.
- `--interactive`: approve/reject/timeout each sale from the console
  instead, to reproduce a specific case.

See [`simulator/README.md`](simulator/README.md) for the full flag
reference. To try the plugin alone, with no APEX app at all, open
[`js/demo.html`](js/demo.html) — a standalone harness that calls the plugin
the same way a real Dynamic Action would.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `Failed to fetch` against a **real** terminal | Missing `chrome://flags` + "Allow CORS" extension setup on that machine |
| `Failed to fetch` against the **simulator** | `--delay-cliente` is close to or above the plugin's 90s timeout — lower the delay range, not a real network issue |
| "POS did not respond in time" | Terminal off, wrong IP/port, disconnected network cable, or (against the simulator) `--random` rolled a timeout |
| Configuration items (IP/Port/Payment Method) arrive empty at the plugin's action | The "Execute Server-side Code" action (piece 1) is written with `apex_application.g_x01` + `sys.htp.p` instead of bind variables — see the note under piece 1. No error is thrown, it just sets nothing. |
| The plugin's action, chained right after another async action, never gets its attributes | Move the result mapping to a separate "Change" event (piece 3), not a third chained action — see the note under piece 3. |
| Charge button doesn't show/hide live as the cashier fills the form | A server-side (PL/SQL) button condition only evaluates at page render, not on every form change — add your own show/hide Dynamic Action bound to the relevant items. |

## APEX version compatibility

Built and tested on APEX 20.2. The `apex_plugin.t_dynamic_action` /
`t_dynamic_action_render_result` API this plugin's `render` function uses is
stable and documented from APEX 20.1 onward — comparing the official
definitions for [20.1](https://docs.oracle.com/en/database/oracle/application-express/20.1/aeapi/APEX_PLUGIN-Data-Types.html)
against [24.2](https://docs.oracle.com/en/database/oracle/apex/24.2/aeapi/APEX_PLUGIN-Data-Types.html),
the `attribute_01`..`attribute_15` fields this plugin uses didn't change;
24.2 only adds new fields at the end that this plugin doesn't need.

SweetAlert2 ships bundled as the plugin's own file, not loaded from an
external CDN — deliberate, since a strict Content Security Policy
`script-src` (which Oracle documents strengthening for APEX 24.2) would
block a `<script>` pointing at an external CDN domain not explicitly
allow-listed.

Installing through the UI (recommended path above), version compatibility
is handled by APEX itself — it doesn't depend on any hand-typed `p_release`.
The `install/*.sql` scripts remain in the repo mainly as a readable
reference for the plugin's source code.

## License

MIT — see [`LICENSE`](LICENSE). SweetAlert2, bundled in `js/vendor/`, is
also MIT-licensed.
