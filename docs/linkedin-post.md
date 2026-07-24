# Publicación para LinkedIn

## Versión recomendada

🚀 **Nuevo plugin open source: integración Bancard POS para Oracle APEX**

Desarrollé un plugin de **Dynamic Action para Oracle APEX** que permite iniciar cobros directamente en un terminal físico Bancard desde el navegador del cajero.

La comunicación se realiza mediante la API REST local del POS, sin depender de que el servidor de aplicaciones tenga acceso a la red donde se encuentra el terminal. Esto resulta especialmente útil cuando Oracle APEX u ORDS están en la nube o en un segmento de red diferente al punto de venta.

### Características principales

✅ Comunicación directa navegador → terminal POS  
✅ Sin backend intermedio para ejecutar la operación  
✅ Múltiples medios de pago Bancard  
✅ Estados de conexión, procesamiento, aprobación, rechazo y timeout  
✅ Resultados crudos escritos en Page Items de Oracle APEX  
✅ SweetAlert2 incluido en el plugin  
✅ Simulador local y demo interactivo para probar sin hardware físico  
✅ Exports verificados para APEX 20.2 y 24.2  

El plugin es genérico y no está acoplado al modelo de datos o las reglas de negocio de una empresa. Cada aplicación puede realizar su propio mapeo de emisores, referencias, montos y resultados.

🔗 Código fuente y documentación:

`https://github.com/silviosotelo/apex-bancard-pos-plugin`

Proyecto independiente y no oficial. Bancard y Oracle APEX son marcas de sus respectivos titulares.

#OracleAPEX #PLSQL #JavaScript #Bancard #POS #Payments #OpenSource #Paraguay #Fintech #SoftwareDevelopment

---

## Versión breve

Construí un plugin open source para iniciar cobros en terminales Bancard directamente desde una Dynamic Action de Oracle APEX.

La operación se ejecuta desde el navegador del cajero hacia el POS en la red local, evitando depender de que ORDS o el servidor APEX tengan acceso directo al terminal.

Incluye soporte para múltiples medios de pago, Page Items de salida, SweetAlert2, simulador local y una demo interactiva.

Repositorio:

`https://github.com/silviosotelo/apex-bancard-pos-plugin`

#OracleAPEX #Bancard #JavaScript #OpenSource #Paraguay
