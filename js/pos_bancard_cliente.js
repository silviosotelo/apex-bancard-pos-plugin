window.bancardPosCliente = (function () {

  var TIMEOUT_ECO_MS = 5000;
  // Un cliente real puede tardar bastante en completar la operacion en el
  // POS (insertar/pasar tarjeta, PIN, reintentos). 90s da margen razonable
  // por encima de una demora simulada de hasta 60s (ver simulator/README.md,
  // --delay-cliente) sin quedar pegado al limite.
  var TIMEOUT_OPERACION_MS = 90000;

  function fetchConTimeout(pUrl, pBody, pTimeoutMs) {
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, pTimeoutMs);
    return fetch(pUrl, {
      method: 'POST',
      // Content-Type: 'text/plain', NO 'application/json' -- a proposito.
      // 'application/json' hace que el navegador considere esto un pedido
      // "no simple" y mande un preflight OPTIONS antes del POST real
      // (regla CORS). Terminales POS reales (probado contra un SmartPOS
      // Bancard fisico) no manejan OPTIONS y cortan la conexion sin
      // responder nada (net::ERR_EMPTY_RESPONSE) -- ni siquiera llega a
      // rechazar el pedido, el navegador nunca manda el POST real. Con
      // 'text/plain' el pedido entra en la lista de "CORS-safelisted"
      // (junto con application/x-www-form-urlencoded y multipart/form-data)
      // y el navegador manda el POST directo, sin preflight -- el terminal
      // igual lee el body como JSON, no valida el header.
      headers: { 'Content-Type': 'text/plain' },
      body: JSON.stringify(pBody),
      signal: controller.signal
    }).then(function (response) {
      clearTimeout(timer);
      return response.json().then(function (json) {
        return { status: response.status, body: json };
      });
    }).catch(function (error) {
      clearTimeout(timer);
      if (error.name === 'AbortError') {
        throw new Error('El POS no respondio dentro del tiempo de espera (' + pTimeoutMs + 'ms).');
      }
      throw new Error('No se pudo conectar al POS (' + pUrl + '): ' + error.message
        + '. Si el navegador bloqueo el pedido (mixed content / red local), en esta maquina: '
        + 'candado de la barra de direcciones -> Configuracion de sitios -> habilitar '
        + '"Red local" y "Contenido no seguro" para este sitio.');
    });
  }

  function validarError(pResultado, pNombreOperacion) {
    if (pResultado.status === 400 || pResultado.status === 500) {
      var mensaje = (pResultado.body && pResultado.body.message) || ('Error desconocido en ' + pNombreOperacion);
      throw new Error('POS respondio error en ' + pNombreOperacion + ': ' + mensaje);
    }
  }

  function eco(pBaseUrl) {
    return fetchConTimeout(pBaseUrl + '/pos/eco', { eco: 1 }, TIMEOUT_ECO_MS).then(function (resultado) {
      validarError(resultado, '/pos/eco');
      return resultado;
    });
  }

  // ---- Tarjeta: venta-ux / venta/debito / venta/credito + descuento (flujo de 2 pasos) ----
  function ventaTarjeta(pBaseUrl, pMedio, pMonto, pFacturaNro, pCuotas, pPlan) {
    var endpoint;
    var body = { facturaNro: pFacturaNro };
    var cuotas = pCuotas || 0;
    var plan = pPlan || 0;

    if (pMedio === 'TARJETA_DEBITO') {
      endpoint = '/pos/venta/debito'; // sin monto
    } else if (pMedio === 'TARJETA_CREDITO') {
      endpoint = '/pos/venta/credito'; // sin monto, con cuotas/plan
      body.cuotas = cuotas;
      body.plan = plan;
    } else {
      endpoint = '/pos/venta-ux'; // con monto (contado o con cuotas)
      body.monto = pMonto;
      if (cuotas > 0) {
        body.cuotas = cuotas;
        body.plan = plan;
      }
    }

    return fetchConTimeout(pBaseUrl + endpoint, body, TIMEOUT_OPERACION_MS).then(function (resultado) {
      validarError(resultado, endpoint);
      return resultado.body;
    });
  }

  function descuento(pBaseUrl, pBin, pNsu, pMonto) {
    var body = { bin: pBin, nsu: pNsu, monto: pMonto };
    return fetchConTimeout(pBaseUrl + '/pos/descuento', body, TIMEOUT_OPERACION_MS).then(function (resultado) {
      validarError(resultado, '/pos/descuento');
      return resultado.body;
    });
  }

  function ventaConDescuento(pBaseUrl, pMedio, pMonto, pFacturaNro, pCuotas, pPlan) {
    return ventaTarjeta(pBaseUrl, pMedio, pMonto, pFacturaNro, pCuotas, pPlan)
      .then(function (ventaResultado) {
        return descuento(pBaseUrl, ventaResultado.bin, ventaResultado.nsu, pMonto);
      });
  }

  // ---- QR / QR PIX / extraccion QR (respuesta directa, sin paso de descuento) ----
  function ventaQr(pBaseUrl, pMonto, pFacturaNro, pMontoVuelto, pPromotions) {
    var body = { facturaNro: pFacturaNro, monto: pMonto };
    if (pMontoVuelto) { body.montoVuelto = pMontoVuelto; }
    if (pPromotions) { body.promotions = pPromotions; }
    return fetchConTimeout(pBaseUrl + '/pos/venta-qr', body, TIMEOUT_OPERACION_MS).then(function (resultado) {
      validarError(resultado, '/pos/venta-qr');
      return resultado.body;
    });
  }

  function ventaQrPix(pBaseUrl, pMonto, pFacturaNro, pPixPayerCpf, pPixPayerPhone) {
    var body = { facturaNro: pFacturaNro, monto: pMonto, pix_payer_cpf: pPixPayerCpf, pix_payer_phone: pPixPayerPhone };
    return fetchConTimeout(pBaseUrl + '/pos/venta-qr-pix', body, TIMEOUT_OPERACION_MS).then(function (resultado) {
      validarError(resultado, '/pos/venta-qr-pix');
      return resultado.body;
    });
  }

  function extraccionQr(pBaseUrl, pMonto) {
    var body = { monto: pMonto };
    return fetchConTimeout(pBaseUrl + '/pos/extraccion-qr', body, TIMEOUT_OPERACION_MS).then(function (resultado) {
      validarError(resultado, '/pos/extraccion-qr');
      return resultado.body;
    });
  }

  // ---- Canje de puntos / canje via QR (respuesta directa) ----
  function ventaCanje(pBaseUrl, pMonto, pFacturaNro, pViaQr) {
    var endpoint = pViaQr ? '/pos/venta-canje-qr' : '/pos/venta-canje';
    var body = { facturaNro: pFacturaNro, monto: pMonto };
    return fetchConTimeout(pBaseUrl + endpoint, body, TIMEOUT_OPERACION_MS).then(function (resultado) {
      validarError(resultado, endpoint);
      return resultado.body;
    });
  }

  // ---- Billetera electronica (respuesta directa) ----
  function ventaBilletera(pBaseUrl, pMonto, pFacturaNro, pBilletera, pCuenta) {
    var body = { facturaNro: pFacturaNro, monto: pMonto, billetera: pBilletera, cuenta: pCuenta };
    return fetchConTimeout(pBaseUrl + '/pos/venta-billetera', body, TIMEOUT_OPERACION_MS).then(function (resultado) {
      validarError(resultado, '/pos/venta-billetera');
      return resultado.body;
    });
  }

  // ---- Despacho por medio de pago ----
  function ejecutarMedioDePago(pMedio, pBaseUrl, pMonto, pFacturaNro, pOpciones) {
    switch (pMedio) {
      case 'TARJETA_DEBITO':
        return ventaConDescuento(pBaseUrl, 'TARJETA_DEBITO', pMonto, pFacturaNro, 0, 0);
      case 'TARJETA_CREDITO':
        return ventaConDescuento(pBaseUrl, 'TARJETA_CREDITO', pMonto, pFacturaNro, pOpciones.cuotas || 0, pOpciones.plan || 0);
      case 'TARJETA_CUOTAS':
        return ventaConDescuento(pBaseUrl, 'TARJETA_CONTADO', pMonto, pFacturaNro, pOpciones.cuotas || 0, pOpciones.plan || 0);
      case 'QR':
        return ventaQr(pBaseUrl, pMonto, pFacturaNro, pOpciones.montoVuelto, pOpciones.promotions);
      case 'QR_PIX':
        return ventaQrPix(pBaseUrl, pMonto, pFacturaNro, pOpciones.pix_payer_cpf, pOpciones.pix_payer_phone);
      case 'EXTRACCION_QR':
        return extraccionQr(pBaseUrl, pMonto);
      case 'CANJE':
        return ventaCanje(pBaseUrl, pMonto, pFacturaNro, false);
      case 'CANJE_QR':
        return ventaCanje(pBaseUrl, pMonto, pFacturaNro, true);
      case 'BILLETERA':
        return ventaBilletera(pBaseUrl, pMonto, pFacturaNro, pOpciones.billetera, pOpciones.cuenta);
      case 'TARJETA_CONTADO':
      default:
        return ventaConDescuento(pBaseUrl, 'TARJETA_CONTADO', pMonto, pFacturaNro, 0, 0);
    }
  }

  function parsearOpciones(pJsonCrudo) {
    if (!pJsonCrudo || String(pJsonCrudo).trim() === '') { return {}; }
    try {
      return JSON.parse(pJsonCrudo);
    } catch (e) {
      console.error('[pos_bancard_cliente] JSON invalido en Datos Adicionales: ' + pJsonCrudo);
      return {};
    }
  }

  // ---- Loader SweetAlert2 (cargado por el plugin via p_javascript_file_urls) ----
  // No se usa Swal.showLoading()/hideLoading(): ese mecanismo convierte el
  // boton de "Confirmar" en el spinner, y depende de encontrar un boton
  // visible para reemplazar -- fragil (con showConfirmButton:false no hay
  // boton que convertir; sin eso, el boton "Confirmar" puede quedar visible
  // si el swap no se revierte bien antes del siguiente Swal.fire()). En vez
  // de depender de ese acople, el spinner se arma a mano en el html del
  // modal (reusando la clase .swal2-loader que ya trae el CSS del bundle),
  // con showConfirmButton:false fijo -- nunca hay boton, nunca hay que
  // revertir nada.
  function htmlCargando(pTexto) {
    return '<div class="swal2-loader" style="display:inline-block"></div>'
      + '<div style="margin-top:0.75em">' + pTexto + '</div>';
  }

  function mostrarCargando(pTitulo, pTexto) {
    if (!window.Swal) { return; }
    Swal.fire({
      title: pTitulo,
      html: htmlCargando(pTexto),
      allowOutsideClick: false,
      allowEscapeKey: false,
      showConfirmButton: false
    });
  }

  function actualizarCargando(pTitulo, pTexto) {
    if (!window.Swal) { return; }
    Swal.update({ title: pTitulo, html: htmlCargando(pTexto) });
  }

  function cerrarCargando() {
    if (window.Swal) { Swal.close(); }
  }

  function mostrarExito(pTitulo, pTexto) {
    if (!window.Swal) { return; }
    Swal.fire({ icon: 'success', title: pTitulo, text: pTexto, confirmButtonText: 'Aceptar' });
  }

  function mostrarError(pTitulo, pTexto) {
    if (window.Swal) {
      Swal.fire({ icon: 'error', title: pTitulo, text: pTexto, confirmButtonText: 'Aceptar' });
    } else {
      // Sin SweetAlert2 cargado (archivo del plugin no disponible): igual
      // hay que avisar el error, se usa la notificacion nativa de APEX.
      apex.message.showErrors([{ type: 'error', location: 'page', message: pTexto, unsafe: false }]);
    }
  }

  function execute(pThis) {
    // APEX 20.2 invoca las acciones de plugin con el contexto en "this",
    // sin pasar ningun argumento posicional (confirmado contra el
    // dispatcher real de Dynamic Actions, no solo el demo standalone que
    // llama a execute(...) a mano). pThis || this cubre ambos casos.
    pThis = pThis || this;
    var itemIp                = pThis.action.attribute01;
    var itemPuerto             = pThis.action.attribute02;
    var itemMedioPago          = pThis.action.attribute03;
    var itemMonto              = pThis.action.attribute04;
    var itemOpciones           = pThis.action.attribute05;
    var itemNroBoleta          = pThis.action.attribute06;
    var itemIssuerId           = pThis.action.attribute07;
    var itemMontoCobrado       = pThis.action.attribute08;
    var itemFechaHora          = pThis.action.attribute09;
    var itemFacturaRef         = pThis.action.attribute10;
    var itemResultadoCompleto  = pThis.action.attribute11;

    var ip          = apex.item(itemIp).getValue();
    var puerto      = apex.item(itemPuerto).getValue();
    var medio       = (apex.item(itemMedioPago).getValue() || 'TARJETA_CONTADO').toUpperCase();
    // Monto: numero plano, sin formato de miles. Cada app convierte su propio
    // formato de entrada (si lo tiene) a numero antes de setear este item.
    var monto       = parseFloat(apex.item(itemMonto).getValue());
    var opciones    = parsearOpciones(itemOpciones ? apex.item(itemOpciones).getValue() : null);
    var baseUrl     = 'http://' + ip + ':' + puerto;
    var facturaNro  = Date.now();

    if (!ip || !puerto) {
      mostrarError('No se puede cobrar', 'No hay IP/Puerto de POS configurado en los items del plugin.');
      return;
    }
    if (!monto || monto <= 0) {
      mostrarError('No se puede cobrar', 'Monto invalido para cobrar con POS.');
      return;
    }

    mostrarCargando('Conectando con el POS...', 'Verificando conexion (eco).');

    eco(baseUrl)
      .then(function () {
        actualizarCargando('Esperando el pago...', 'Complete la operacion en el terminal POS (tarjeta, QR, billetera, etc.).');
        return ejecutarMedioDePago(medio, baseUrl, monto, facturaNro, opciones);
      })
      .then(function (resultado) {
        cerrarCargando();
        // Valores crudos, sin mapear ni formatear: cada app decide como
        // traducir issuerId a su propio catalogo de marcas y como formatear
        // monto/fecha para su propio proceso de guardado.
        // suppressChangeEvent=false (a proposito): la app consumidora puede
        // engancharse con una Dynamic Action "Change" sobre estos items para
        // mapear el resultado crudo a su propio formulario.
        apex.item(itemNroBoleta).setValue(String(resultado.nroBoleta || resultado.codigoAutorizacion || ''), null, false);
        apex.item(itemIssuerId).setValue(resultado.issuerId || '', null, false);
        apex.item(itemMontoCobrado).setValue(String(monto), null, false);
        apex.item(itemFechaHora).setValue(new Date().toISOString(), null, false);
        apex.item(itemFacturaRef).setValue(String(facturaNro), null, false);
        if (itemResultadoCompleto) {
          apex.item(itemResultadoCompleto).setValue(JSON.stringify(resultado), null, false);
        }
        mostrarExito('Pago registrado', 'La operacion se realizo correctamente en el POS.');
      })
      .catch(function (error) {
        cerrarCargando();
        mostrarError('El POS rechazo la operacion', error.message);
      });
  }

  return {
    execute: execute,
    // expuestas para testing standalone
    _eco: eco,
    _ventaTarjeta: ventaTarjeta,
    _descuento: descuento,
    _ventaQr: ventaQr,
    _ventaQrPix: ventaQrPix,
    _extraccionQr: extraccionQr,
    _ventaCanje: ventaCanje,
    _ventaBilletera: ventaBilletera,
    _ejecutarMedioDePago: ejecutarMedioDePago
  };
})();
