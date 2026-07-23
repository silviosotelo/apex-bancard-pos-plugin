#!/usr/bin/env python3
"""Simulador local del POS Android CajaPOS (Bancard, API REST v1.5.0).

Implementa TODOS los endpoints documentados en
"ICP-Integración CAJA POS - Android 2.0 v1.9 2025_06_10.pdf" (la API REST
en si sigue siendo la 1.5.0; solo el documento se actualizo a v1.9), para
poder probar la integracion completa sin terminal fisico. Solo libreria
estandar de Python, sin dependencias externas.

Endpoints:
  /pos/eco                 verificacion de conexion
  /pos/venta-ux            venta contado / cuotas
  /pos/venta/debito        venta forzado debito
  /pos/venta/credito       venta forzado credito
  /pos/descuento           envio de monto (paso 2 de venta-ux/debito/credito)
  /pos/venta-qr            venta QR (con vuelto y promotions opcionales)
  /pos/venta-qr-pix        venta QR PIX
  /pos/extraccion-qr       extraccion QR
  /pos/venta-canje         venta por canje de puntos
  /pos/venta-canje-qr      venta por canje de puntos via QR
  /pos/venta-billetera     venta con billetera electronica
  /pos/consulta-anulacion  consulta de boletas para anular
  /pos/anulacion           anulacion de una boleta

Uso:
    python pos_simulator.py --port 3000
    python pos_simulator.py --port 3000 --interactive
    python pos_simulator.py --port 3000 --interactive --delay 1.5
    python pos_simulator.py --port 3000 --delay-cliente 6
    python pos_simulator.py --port 3000 --delay-cliente 30-60 --random
    python pos_simulator.py --port 3000 --delay-cliente 30-60 --random --fail-rate 0.3

Con --interactive, cada venta pide aprobar/rechazar/timeout por consola,
igual que un cajero interactuando con la terminal fisica real.

Con --random (sin --interactive), el simulador decide solo, al azar: la
mayoria de las ventas se aprueban, pero una parte se rechaza (fondos
insuficientes, tarjeta vencida, tarjeta bloqueada, etc.), otra parte hace
timeout (sin respuesta), y el propio /pos/eco tambien puede fallar (POS no
responde). Las probabilidades se ajustan con --fail-rate, --timeout-rate y
--eco-fail-rate (0-1 cada una). Sin --random ni --interactive, el simulador
aprueba todo siempre (modo automatico simple, el de antes).

--delay-cliente simula el tiempo real que tarda el cliente en completar la
transaccion en el POS (insertar/pasar la tarjeta, ingresar PIN, escanear el
QR) -- se aplica a todos los endpoints EXCEPTO /pos/eco (que en un terminal
real responde casi instantaneo, es solo un ping de conectividad). Acepta un
numero fijo ("6") o un rango aleatorio ("30-60", distinto por cada venta).
Util para ver en pantalla el loader "Esperando el pago..." del plugin en vez
de que la respuesta llegue de inmediato. --delay, en cambio, es latencia de
red generica (fija) y se aplica a todo, incluido /pos/eco.
"""
import argparse
import json
import random
import string
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- Tarjetas de prueba (TABLA DE ISSUER ID, v1.9 del PDF) ----
TARJETAS_CREDITO = [
    {"issuerId": "VC", "nombreTarjeta": "VISA - CLASICA - BANCO ITAU PY", "bin_prefix": "4"},
    {"issuerId": "MC", "nombreTarjeta": "MASTERCARD - BLACK - BANCO ITAU PY", "bin_prefix": "5"},
    {"issuerId": "CB", "nombreTarjeta": "CABAL - CLASICA - BANCO FAMILIAR", "bin_prefix": "6"},
    {"issuerId": "AC", "nombreTarjeta": "AMERICAN EXPRESS - BANCO GNB", "bin_prefix": "3"},
    {"issuerId": "BC", "nombreTarjeta": "BANCARD - CLASICA", "bin_prefix": "6"},
    {"issuerId": "CP", "nombreTarjeta": "PANAL - CLASICA", "bin_prefix": "6"},
    {"issuerId": "PC", "nombreTarjeta": "CREDICARD - CLASICA", "bin_prefix": "5"},
    {"issuerId": "TC", "nombreTarjeta": "TARJETA CREDITO - BANCO REGIONAL", "bin_prefix": "4"},
    {"issuerId": "DC", "nombreTarjeta": "DINERS CLUB - INTERNATIONAL", "bin_prefix": "3"},
    {"issuerId": "CC", "nombreTarjeta": "CREDIFIELCO - CLASICA", "bin_prefix": "6"},
    {"issuerId": "CL", "nombreTarjeta": "CARTA CLAVE - CLASICA", "bin_prefix": "6"},
]
TARJETAS_DEBITO = [
    {"issuerId": "VD", "nombreTarjeta": "VISA - PREPAGA - BANCO ITAU PY", "bin_prefix": "4"},
    {"issuerId": "MD", "nombreTarjeta": "MASTERCARD - DEBITO - BANCO CONTINENTAL", "bin_prefix": "5"},
    {"issuerId": "ID", "nombreTarjeta": "INFONET - DEBITO", "bin_prefix": "9"},
    {"issuerId": "TD", "nombreTarjeta": "TARJETA DEBITO - BANCO REGIONAL", "bin_prefix": "4"},
    {"issuerId": "UD", "nombreTarjeta": "UNICA - DEBITO", "bin_prefix": "6"},
    {"issuerId": "CD", "nombreTarjeta": "DEBITO EN CUENTA - BANCO FAMILIAR", "bin_prefix": "4"},
]
BILLETERAS = {
    "ZIM": {"issuerId": "ZM", "nombreTarjeta": "Zimple - Debito Infonet"},
    "WPJ": {"issuerId": "PJ", "nombreTarjeta": "Paraguayo Japonesa - Billetera"},
    "VBV": {"issuerId": "VB", "nombreTarjeta": "Vision Banco - Billetera"},
    "BPI": {"issuerId": "PI", "nombreTarjeta": "Personal-Itau - Billetera"},
    "BBF": {"issuerId": "BF", "nombreTarjeta": "Billetera Viru"},
}
NOMBRES_CLIENTE = ["GONZALEZ/JOSE", "RODRIGUEZ/RENE", "BENITEZ/MARIA", "FLEITAS/CARLOS", "GIMENEZ/ANA"]
MOTIVOS_RECHAZO = [
    "Transaccion rechazada por el emisor",
    "Fondos insuficientes",
    "Tarjeta vencida",
    "Tarjeta bloqueada, contacte a su banco",
    "Error de comunicacion con el emisor, intente nuevamente",
    "Transaccion no permitida para esta tarjeta",
]


def rand_digits(n):
    return "".join(random.choices(string.digits, k=n))


def parse_rango_segundos(valor):
    """Acepta 'N' (fijo) o 'N-M' (aleatorio uniforme entre N y M segundos)."""
    valor = valor.strip()
    if "-" in valor:
        lo, hi = valor.split("-", 1)
        lo, hi = float(lo), float(hi)
        if lo > hi:
            lo, hi = hi, lo
        return (lo, hi)
    n = float(valor)
    return (n, n)


def error_400(mensaje):
    return 400, {"statusCode": 400, "error": "Bad Request", "message": mensaje}


def error_500(mensaje="Error interno del POS"):
    return 500, {"statusCode": 500, "error": "Internal Server Error", "message": mensaje}


class Estado:
    def __init__(self, interactivo, delay, delay_cliente, random_outcomes=False,
                 fail_rate=0.15, timeout_rate=0.03, eco_fail_rate=0.05):
        self.interactivo = interactivo
        self.delay = delay
        self.delay_cliente = delay_cliente  # tupla (min, max) segundos
        self.random_outcomes = random_outcomes
        self.fail_rate = fail_rate
        self.timeout_rate = timeout_rate
        self.eco_fail_rate = eco_fail_rate
        self.lock = threading.Lock()
        self.transacciones = {}  # nsu -> dict (ventas contado/cuotas/debito/credito pendientes de descuento)
        self.boletas = []  # ledger para consulta-anulacion / anulacion

    def registrar(self, evento):
        print(f"[{time.strftime('%H:%M:%S')}] {evento}")

    def registrar_boleta(self, nro_tarjeta, nro_boleta, monto, transaccion):
        with self.lock:
            self.boletas.insert(0, {
                "nroTarjeta": nro_tarjeta,
                "nroBoleta": nro_boleta,
                "monto": str(monto),
                "fechaHora": time.strftime("%y/%m/%d %H:%M"),
                "transaccion": transaccion,
                "anulada": False,
            })
            self.boletas = self.boletas[:200]


def preguntar_operador(estado, resumen):
    if estado.interactivo:
        print("\n" + "=" * 60)
        print("SOLICITUD DE APROBACION")
        print(resumen)
        print("=" * 60)
        while True:
            resp = input(">> Aprobar (a) / Rechazar (r) / Timeout (t)? [a]: ").strip().lower()
            if resp in ("", "a"):
                return True, None
            if resp == "r":
                motivo = input(">> Motivo de rechazo [Transaccion rechazada]: ").strip() or "Transaccion rechazada"
                return False, motivo
            if resp == "t":
                return False, "__TIMEOUT__"
            print("Respuesta invalida.")

    if estado.random_outcomes:
        roll = random.random()
        if roll < estado.timeout_rate:
            estado.registrar(f"{resumen} -> TIMEOUT (aleatorio)")
            return False, "__TIMEOUT__"
        if roll < estado.timeout_rate + estado.fail_rate:
            motivo = random.choice(MOTIVOS_RECHAZO)
            estado.registrar(f"{resumen} -> RECHAZADA (aleatorio): {motivo}")
            return False, motivo

    return True, None


def mask_bin(bin_):
    return bin_[:4] + "*" * 8 + bin_[-4:] if len(bin_) >= 8 else bin_


class Handler(BaseHTTPRequestHandler):
    estado = None  # inyectado desde main()

    def log_message(self, format, *args):
        pass  # silenciamos el log default de http.server; usamos Estado.registrar

    def _leer_json(self):
        largo = int(self.headers.get("Content-Length", 0) or 0)
        crudo = self.rfile.read(largo) if largo else b""
        if not crudo:
            return None
        try:
            return json.loads(crudo)
        except json.JSONDecodeError:
            return "__INVALID__"

    def _cors_headers(self):
        # El simulador es nuestro, a diferencia de un terminal Bancard real
        # (que no manda CORS y por eso el plugin requiere una extension tipo
        # "Allow CORS" en el navegador de la sucursal) -- para probar contra
        # el simulador no hace falta esa extension, el simulador ya responde
        # los headers CORS necesarios, incluido el preflight OPTIONS.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _responder(self, status, payload):
        cuerpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/status"):
            with self.estado.lock:
                abiertas = len(self.estado.transacciones)
                boletas = len(self.estado.boletas)
            self._responder(200, {
                "transacciones_abiertas": abiertas,
                "boletas_registradas": boletas,
                "modo": "interactivo" if self.estado.interactivo else "automatico",
            })
        else:
            self._responder(404, {"statusCode": 404, "error": "Not Found", "message": "Ruta no encontrada"})

    def do_POST(self):
        estado = self.estado
        path = self.path.split("?")[0]
        body = self._leer_json()

        if estado.delay:
            time.sleep(estado.delay)
        if estado.delay_cliente and path != "/pos/eco":
            lo, hi = estado.delay_cliente
            if hi > 0:
                espera = random.uniform(lo, hi)
                estado.registrar(f"{path} -> simulando {espera:.1f}s de cliente completando la transaccion...")
                time.sleep(espera)

        if body is None:
            status, payload = error_400("MENSAJE INCOMPLETO")
        elif body == "__INVALID__":
            status, payload = error_400("ERROR AL RECIBIR DATOS DE CAJA")
        else:
            try:
                status, payload = self._despachar(path, body, estado)
            except TimeoutError:
                estado.registrar(f"{path} -> TIMEOUT simulado (sin responder)")
                try:
                    self.close_connection = True
                except Exception:
                    pass
                return
            except Exception as e:
                status, payload = error_500(str(e))

        estado.registrar(f"{path} -> {status} {json.dumps(payload, ensure_ascii=False)}")
        self._responder(status, payload)

    def _despachar(self, path, body, estado):
        if path == "/pos/eco":
            return self._eco(body, estado)
        if path == "/pos/venta-ux":
            return self._venta_ux(body, estado)
        if path == "/pos/venta/debito":
            return self._venta_forzada(body, estado, "debito")
        if path == "/pos/venta/credito":
            return self._venta_forzada(body, estado, "credito")
        if path == "/pos/descuento":
            return self._descuento(body, estado)
        if path == "/pos/venta-qr":
            return self._venta_qr(body, estado)
        if path == "/pos/venta-qr-pix":
            return self._venta_qr_pix(body, estado)
        if path == "/pos/extraccion-qr":
            return self._extraccion_qr(body, estado)
        if path in ("/pos/venta-canje", "/pos/venta-canje-qr"):
            return self._venta_canje(body, estado, path)
        if path == "/pos/venta-billetera":
            return self._venta_billetera(body, estado)
        if path == "/pos/consulta-anulacion":
            return self._consulta_anulacion(body, estado)
        if path == "/pos/anulacion":
            return self._anulacion(body, estado)
        return 404, {"statusCode": 404, "error": "Not Found", "message": "Ruta no encontrada"}

    # ---- validaciones comunes ----
    def _valida_factura_monto(self, body, requiere_monto):
        factura = body.get("facturaNro")
        if not isinstance(factura, int) or factura < 0 or factura > 999999999999999:
            return "Numero factura fuera de rango"
        if requiere_monto:
            monto = body.get("monto")
            if not isinstance(monto, int) or monto < 1 or monto > 999999999:
                return "Monto invalido"
        return None

    def _valida_cuotas_plan(self, body):
        cuotas = body.get("cuotas", 0)
        plan = body.get("plan", 0)
        if not isinstance(cuotas, int) or cuotas < 0 or cuotas > 99:
            return "Cantidad de cuotas invalida"
        if cuotas == 1:
            return "Cantidad de cuotas invalida"
        if not isinstance(plan, int) or plan < 0 or plan > 99:
            return "Numero plan invalido"
        return None

    def _pedir_aprobacion(self, estado, resumen):
        ok, motivo = preguntar_operador(estado, resumen)
        if not ok:
            if motivo == "__TIMEOUT__":
                raise TimeoutError
            return motivo
        return None

    # ---- eco ----
    def _eco(self, body, estado):
        eco = body.get("eco")
        if not isinstance(eco, int) or eco < 0 or eco > 99:
            return error_400(f"Error de rango: {eco}")
        if estado.random_outcomes and random.random() < estado.eco_fail_rate:
            estado.registrar("/pos/eco -> FALLO (aleatorio): POS no responde")
            return error_500("POS no responde")
        return 200, {"eco": eco}

    # ---- venta-ux / debito / credito + descuento (flujo de 2 pasos) ----
    def _emitir_venta(self, estado, factura, monto, tipo, cuotas=0, plan=0):
        resumen = f"VENTA {tipo.upper()} | factura={factura} monto={monto} cuotas={cuotas} plan={plan}"
        rechazo = self._pedir_aprobacion(estado, resumen)
        if rechazo:
            return error_400(rechazo)

        if tipo == "credito":
            tarjeta = random.choice(TARJETAS_CREDITO)
        elif tipo == "debito":
            tarjeta = random.choice(TARJETAS_DEBITO)
        else:
            tarjeta = random.choice(TARJETAS_CREDITO + TARJETAS_DEBITO)

        bin_ = tarjeta["bin_prefix"] + rand_digits(9)
        nsu = rand_digits(6)
        with estado.lock:
            estado.transacciones[nsu] = {
                "bin": bin_, "factura": factura, "monto": monto,
                "tipo": tipo, "tarjeta": tarjeta, "cuotas": cuotas, "plan": plan,
            }
        return 200, {"bin": bin_, "nsu": nsu}

    def _venta_ux(self, body, estado):
        err = self._valida_factura_monto(body, requiere_monto=True)
        if err:
            return error_400(err)
        cuotas = body.get("cuotas", 0)
        plan = body.get("plan", 0)
        if "cuotas" in body or "plan" in body:
            err = self._valida_cuotas_plan(body)
            if err:
                return error_400(err)
        tipo = "credito" if cuotas and cuotas > 1 else "contado"
        return self._emitir_venta(estado, body["facturaNro"], body["monto"], tipo, cuotas, plan)

    def _venta_forzada(self, body, estado, tipo):
        err = self._valida_factura_monto(body, requiere_monto=False)
        if err:
            return error_400(err)
        if tipo == "debito":
            return self._emitir_venta(estado, body["facturaNro"], 0, "debito")
        err = self._valida_cuotas_plan(body)
        if err:
            return error_400(err)
        cuotas = body.get("cuotas", 0)
        plan = body.get("plan", 0)
        return self._emitir_venta(estado, body["facturaNro"], 0, "credito", cuotas, plan)

    def _descuento(self, body, estado):
        bin_ = body.get("bin")
        nsu = body.get("nsu")
        monto = body.get("monto")
        if not isinstance(bin_, str) or len(bin_) > 10:
            return error_400("Longitud bin invalida")
        if not isinstance(nsu, str) or len(nsu) > 6:
            return error_400("Longitud nsu invalida")
        if not isinstance(monto, int) or monto < 1 or monto > 999999999:
            return error_400("Monto invalido")

        with estado.lock:
            tx = estado.transacciones.get(nsu)
        if not tx or tx["bin"] != bin_:
            return error_400("No se pudo establecer conexión con el POS")

        resumen = f"DESCUENTO | nsu={nsu} bin={bin_} monto={monto} (factura {tx['factura']})"
        rechazo = self._pedir_aprobacion(estado, resumen)
        if rechazo:
            return error_400(rechazo)

        tarjeta = tx["tarjeta"]
        nro_boleta = rand_digits(12)
        respuesta = {
            "codigoAutorizacion": rand_digits(6),
            "nroBoleta": nro_boleta,
            "codigoComercio": rand_digits(7),
            "nombreTarjeta": tarjeta["nombreTarjeta"],
            "pan": rand_digits(4),
            "mensajeDisplay": "APROBADA",
            "nombreCliente": random.choice(NOMBRES_CLIENTE),
            "issuerId": tarjeta["issuerId"],
            "montoVuelto": 0,
        }
        if tx["tipo"] == "debito":
            respuesta["saldo"] = random.randint(monto, monto * 5)
        with estado.lock:
            del estado.transacciones[nsu]
        estado.registrar_boleta(mask_bin(bin_ + rand_digits(6)), nro_boleta, monto, "Tarjeta")
        return 200, respuesta

    # ---- venta-qr / venta-qr-pix / extraccion-qr ----
    def _venta_qr(self, body, estado):
        err = self._valida_factura_monto(body, requiere_monto=True)
        if err:
            return error_400(err)
        promotions = body.get("promotions")
        if promotions is not None and (not isinstance(promotions, list) or not promotions):
            return error_400("Datos de Promocion invalida")
        monto_vuelto = body.get("montoVuelto", 0)
        resumen = f"VENTA QR | factura={body['facturaNro']} monto={body['monto']} montoVuelto={monto_vuelto}"
        rechazo = self._pedir_aprobacion(estado, resumen)
        if rechazo:
            return error_400(rechazo)
        tarjeta = random.choice(TARJETAS_CREDITO + TARJETAS_DEBITO)
        nro_boleta = rand_digits(12)
        estado.registrar_boleta(mask_bin(tarjeta["bin_prefix"] + rand_digits(15)), nro_boleta, body["monto"], "QR")
        return 200, {
            "codigoAutorizacion": rand_digits(6),
            "codigoComercio": rand_digits(7),
            "issuerId": tarjeta["issuerId"],
            "mensajeDisplay": "APROBADA",
            "montoVuelto": monto_vuelto,
            "nombreCliente": random.choice(NOMBRES_CLIENTE),
            "nombreTarjeta": tarjeta["nombreTarjeta"],
            "nroBoleta": nro_boleta,
            "saldo": 0,
        }

    def _venta_qr_pix(self, body, estado):
        err = self._valida_factura_monto(body, requiere_monto=True)
        if err:
            return error_400(err)
        if not body.get("pix_payer_cpf") or not body.get("pix_payer_phone"):
            return error_400("Datos de PIX invalidos")
        resumen = f"VENTA QR PIX | factura={body['facturaNro']} monto={body['monto']} cpf={body.get('pix_payer_cpf')}"
        rechazo = self._pedir_aprobacion(estado, resumen)
        if rechazo:
            return error_400(rechazo)
        nro_boleta = rand_digits(10)
        estado.registrar_boleta("QR-PIX", nro_boleta, body["monto"], "QR PIX")
        return 200, {
            "codigoAutorizacion": rand_digits(6),
            "codigoComercio": rand_digits(2),
            "issuerId": "PX",
            "mensajeDisplay": "Pago Exitoso",
            "montoVuelto": 0,
            "nombreCliente": "QR PIX",
            "nombreTarjeta": "QR PIX",
            "nroBoleta": nro_boleta,
            "saldo": body["monto"],
            "montoRs": round(body["monto"] / 3217, 2),  # cotizacion aproximada simulada Gs->BRL
        }

    def _extraccion_qr(self, body, estado):
        monto = body.get("monto")
        if not isinstance(monto, int) or monto < 1 or monto > 999999999:
            return error_400("Monto invalido")
        resumen = f"EXTRACCION QR | monto={monto}"
        rechazo = self._pedir_aprobacion(estado, resumen)
        if rechazo:
            return error_400(rechazo)
        tarjeta = random.choice(TARJETAS_DEBITO)
        comision = max(1000, int(monto * 0.02))
        nro_boleta = rand_digits(12)
        estado.registrar_boleta(mask_bin(tarjeta["bin_prefix"] + rand_digits(9)), nro_boleta, monto, "Extraccion QR")
        return 200, {
            "codigoAutorizacion": rand_digits(6),
            "codigoComercio": rand_digits(7),
            "issuerId": tarjeta["issuerId"],
            "mensajeDisplay": "APROBADA",
            "nombreCliente": random.choice(NOMBRES_CLIENTE),
            "nombreTarjeta": "QR " + tarjeta["nombreTarjeta"],
            "nroBoleta": nro_boleta,
            "montoExtraccion": monto,
            "montoComision": comision,
            "saldo": monto + comision,
        }

    # ---- canje / canje-qr ----
    def _venta_canje(self, body, estado, path):
        err = self._valida_factura_monto(body, requiere_monto=True)
        if err:
            return error_400(err)
        etiqueta = "VENTA CANJE QR" if path.endswith("canje-qr") else "VENTA CANJE"
        resumen = f"{etiqueta} | factura={body['facturaNro']} monto={body['monto']}"
        rechazo = self._pedir_aprobacion(estado, resumen)
        if rechazo:
            return error_400(rechazo)
        nro_boleta = rand_digits(12)
        estado.registrar_boleta("CANJE-LEALTAD", nro_boleta, body["monto"], "Canje")
        return 200, {
            "codigoAutorizacion": rand_digits(6),
            "codigoComercio": rand_digits(7),
            "issuerId": "LTC",
            "mensajeDisplay": "APROBADA",
            "montoVuelto": 0,
            "nombreCliente": random.choice(NOMBRES_CLIENTE),
            "nombreTarjeta": "VISA - CLASICA - BANCO ITAU PY",
            "nroBoleta": nro_boleta,
            "saldo": body["monto"],
        }

    # ---- billetera ----
    def _venta_billetera(self, body, estado):
        err = self._valida_factura_monto(body, requiere_monto=True)
        if err:
            return error_400(err)
        billetera = body.get("billetera")
        cuenta = body.get("cuenta")
        if billetera not in BILLETERAS:
            return error_400("Billetera invalida")
        if not isinstance(cuenta, str) or not cuenta.isdigit() or len(cuenta) > 16:
            return error_400("Cuenta invalida")
        info = BILLETERAS[billetera]
        resumen = f"VENTA BILLETERA {billetera} | factura={body['facturaNro']} monto={body['monto']} cuenta={cuenta}"
        rechazo = self._pedir_aprobacion(estado, resumen)
        if rechazo:
            return error_400(rechazo)
        nro_boleta = rand_digits(12)
        estado.registrar_boleta(f"BILLETERA-{billetera}", nro_boleta, body["monto"], "Billetera")
        return 200, {
            "codigoAutorizacion": rand_digits(6),
            "codigoComercio": rand_digits(7),
            "issuerId": info["issuerId"],
            "mensajeDisplay": "APROBADA",
            "montoVuelto": 0,
            "nombreCliente": info["issuerId"],
            "nombreTarjeta": info["nombreTarjeta"],
            "nroBoleta": nro_boleta,
            "saldo": 0,
        }

    # ---- consulta-anulacion / anulacion ----
    def _consulta_anulacion(self, body, estado):
        nro_boleta = (body.get("nroBoleta") or "").strip()
        cant_registro = body.get("cantRegistro", 10)
        with estado.lock:
            boletas = list(estado.boletas)
        if nro_boleta and nro_boleta != "0":
            listado = [b for b in boletas if b["nroBoleta"] == nro_boleta]
        else:
            if not isinstance(cant_registro, int) or cant_registro < 0 or cant_registro > 50:
                return error_400("Cantidad de registro invalida (maximo 50)")
            listado = boletas[:cant_registro]
        return 200, {"listado": [
            {k: v for k, v in b.items() if k != "anulada"} for b in listado
        ]}

    def _anulacion(self, body, estado):
        nro_boleta = body.get("nroBoleta")
        if not nro_boleta:
            return error_400("Numero de boleta requerido")
        with estado.lock:
            boleta = next((b for b in estado.boletas if b["nroBoleta"] == nro_boleta), None)
        if not boleta:
            return error_400("No se pudo establecer conexión con el POS")
        resumen = f"ANULACION | nroBoleta={nro_boleta} monto={boleta['monto']}"
        rechazo = self._pedir_aprobacion(estado, resumen)
        if rechazo:
            return error_400(rechazo)
        with estado.lock:
            boleta["anulada"] = True
        return 200, {
            "codigoAutorizacion": "",
            "codigoComercio": "",
            "mensajeDisplay": "APROBADA",
            "montoVuelto": 0,
            "nombreCliente": random.choice(NOMBRES_CLIENTE),
            "nombreTarjeta": "",
            "nroBoleta": nro_boleta,
            "pan": rand_digits(4),
            "saldo": int(boleta["monto"]),
        }


def main():
    ap = argparse.ArgumentParser(description="Simulador POS CajaPOS Bancard (API REST v1.5.0 / doc v1.9)")
    ap.add_argument("--port", type=int, default=3000)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--interactive", action="store_true", help="Pedir aprobar/rechazar/timeout cada venta por consola")
    ap.add_argument("--delay", type=float, default=0.0, help="Segundos de demora simulada por request (toda ruta, incluido /pos/eco)")
    ap.add_argument("--delay-cliente", type=parse_rango_segundos, default=(0.0, 0.0),
                     help="Segundos de demora simulando al cliente completando la transaccion en el POS "
                          "(todo excepto /pos/eco). Acepta un numero fijo ('6') o un rango aleatorio ('30-60').")
    ap.add_argument("--random", dest="random_outcomes", action="store_true",
                     help="Resultados aleatorios en modo automatico (sin --interactive): eco puede fallar, "
                          "ventas pueden ser rechazadas o hacer timeout, en vez de aprobar siempre.")
    ap.add_argument("--fail-rate", type=float, default=0.15,
                     help="Con --random: probabilidad (0-1) de que una venta sea rechazada. Default 0.15.")
    ap.add_argument("--timeout-rate", type=float, default=0.03,
                     help="Con --random: probabilidad (0-1) de que una venta haga timeout (sin respuesta). Default 0.03.")
    ap.add_argument("--eco-fail-rate", type=float, default=0.05,
                     help="Con --random: probabilidad (0-1) de que falle el /pos/eco (POS no responde). Default 0.05.")
    args = ap.parse_args()

    estado = Estado(interactivo=args.interactive, delay=args.delay, delay_cliente=args.delay_cliente,
                     random_outcomes=args.random_outcomes, fail_rate=args.fail_rate,
                     timeout_rate=args.timeout_rate, eco_fail_rate=args.eco_fail_rate)
    Handler.estado = estado

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Simulador CajaPOS Bancard escuchando en http://{args.host}:{args.port}")
    if args.interactive:
        print("Modo: INTERACTIVO (pide aprobacion por consola)")
    elif args.random_outcomes:
        print(f"Modo: AUTOMATICO ALEATORIO (fail_rate={args.fail_rate}, timeout_rate={args.timeout_rate}, "
              f"eco_fail_rate={args.eco_fail_rate})")
    else:
        print("Modo: AUTOMATICO (aprueba todo)")
    if args.delay_cliente != (0.0, 0.0):
        lo, hi = args.delay_cliente
        rango = f"{lo}s" if lo == hi else f"{lo}-{hi}s (aleatorio)"
        print(f"Delay cliente: {rango} en cada endpoint (excepto /pos/eco)")
    print("Endpoints: /pos/eco /pos/venta-ux /pos/venta/debito /pos/venta/credito /pos/descuento")
    print("           /pos/venta-qr /pos/venta-qr-pix /pos/extraccion-qr")
    print("           /pos/venta-canje /pos/venta-canje-qr /pos/venta-billetera")
    print("           /pos/consulta-anulacion /pos/anulacion")
    print("Ctrl+C para detener.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo simulador...")
        server.shutdown()


if __name__ == "__main__":
    main()
