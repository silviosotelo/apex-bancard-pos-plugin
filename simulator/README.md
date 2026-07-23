# Simulador del POS Bancard

Simula la API REST del POS Android de Bancard (v1.5.0) para probar cualquier
integración (como el plugin de este repo) sin terminal físico. Solo Python 3
estándar, sin dependencias.

## Uso

```
python pos_simulator.py --port 3000
```

Modo interactivo (pide aprobar/rechazar/timeout cada venta por consola, como un cajero real):

```
python pos_simulator.py --port 3000 --interactive
```

Simular latencia de red del POS (aplica a toda ruta, incluido `/pos/eco`):

```
python pos_simulator.py --port 3000 --interactive --delay 1.5
```

Simular el tiempo real que tarda el cliente en completar la transacción en el
POS (insertar/pasar tarjeta, PIN, escanear QR) — aplica a todo **excepto**
`/pos/eco`, que en un terminal real responde casi instantáneo. Útil para ver
en pantalla el loader "Esperando el pago..." del plugin en vez de una
respuesta inmediata. Acepta un número fijo o un rango aleatorio (distinto en
cada venta):

```
python pos_simulator.py --port 3000 --delay-cliente 6
python pos_simulator.py --port 3000 --delay-cliente 30-60
```

Resultados aleatorios en modo automático (sin `--interactive`): en vez de
aprobar siempre, una parte de las ventas se rechaza (fondos insuficientes,
tarjeta vencida, tarjeta bloqueada, etc.), otra parte hace timeout, y el
propio `/pos/eco` también puede fallar (POS no responde). Probabilidades
ajustables con `--fail-rate` / `--timeout-rate` / `--eco-fail-rate` (0-1):

```
python pos_simulator.py --port 3000 --delay-cliente 30-60 --random
python pos_simulator.py --port 3000 --delay-cliente 30-60 --random --fail-rate 0.3
```

## Puesta en marcha para probar contra tu app APEX

1. Confirmar la IP LAN de la máquina donde corre esto (`ipconfig` / `ifconfig`).
2. Configurar esa IP y puerto 3000 en la tabla/parámetro que tu app usa para
   resolver el terminal (ver README principal del repo, sección "Integración").
3. Firewall: permitir conexiones entrantes al puerto elegido.
4. Levantar el simulador y probar el botón de cobro en tu página.

## Endpoints implementados

`/pos/eco`, `/pos/venta-ux`, `/pos/venta/debito`, `/pos/venta/credito`, `/pos/descuento`,
`/pos/venta-qr`, `/pos/venta-canje`, `/pos/venta-billetera` — validaciones y formatos de
request/response tomados directamente del PDF (rangos de facturaNro/monto/cuotas/plan,
tabla de Issuer ID para las tarjetas simuladas, etc).

`/pos/descuento` valida que el `bin`/`nsu` correspondan a una venta emitida previamente
(y la consume) — igual que un terminal real no permite reusar un nsu.

En modo `--interactive`, elegir "Timeout" cierra la conexión sin responder, para probar
cómo tu integración maneja un timeout real del terminal.
