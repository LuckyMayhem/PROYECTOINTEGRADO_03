/**
 * Safari POS - Módulo Compartido de Arqueo y Cuadratura de Caja
 * Utilizado en Terminal de Caja (cajero.html) y Panel Admin (administrador.html).
 * Incluye arqueo detallado por billetes y monedas y cálculo en tiempo real.
 */
(function() {
    'use strict';

    let datosArqueoActivo = null;

    function getCookie(name) {
        if (name === 'csrftoken') {
            const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
            if (csrfInput && csrfInput.value) return csrfInput.value;
        }
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    async function abrirModalCierreCaja() {
        try {
            const resp = await fetch('/caja/resumen/');
            const data = await resp.json();
            if (data.success) {
                datosArqueoActivo = data;
                const cajeroEl = document.getElementById('arqCajero');
                const fechaEl = document.getElementById('arqFechaAp');
                const fondoEl = document.getElementById('arqFondoInicial');
                const efecEl = document.getElementById('arqEfectivo');
                const tarjEl = document.getElementById('arqTarjeta');
                const transEl = document.getElementById('arqTransferencia');
                const totVentasEl = document.getElementById('arqTotalVentas');
                const efecEspEl = document.getElementById('arqEfectivoEsperado');

                if (cajeroEl) cajeroEl.innerText = data.cajero_apertura;
                if (fechaEl) fechaEl.innerText = data.fecha_apertura;
                if (fondoEl) fondoEl.innerText = `$${Number(data.monto_inicial || 0).toLocaleString('es-CL')} CLP`;
                if (efecEl) efecEl.innerText = `$${Number(data.total_efectivo || 0).toLocaleString('es-CL')} CLP`;
                if (tarjEl) tarjEl.innerText = `$${Number(data.total_tarjeta || 0).toLocaleString('es-CL')} CLP`;
                if (transEl) transEl.innerText = `$${Number(data.total_transferencia || 0).toLocaleString('es-CL')} CLP`;
                if (totVentasEl) totVentasEl.innerText = `$${Number(data.total_ventas || 0).toLocaleString('es-CL')} CLP`;
                if (efecEspEl) efecEspEl.innerText = `$${Number(data.efectivo_esperado || 0).toLocaleString('es-CL')} CLP`;

                // Reiniciar campos de desglose de efectivo
                document.querySelectorAll('.input-denominacion').forEach(function(inp) {
                    inp.value = '';
                });

                const subBilEl = document.getElementById('subtotalBilletes');
                if (subBilEl) subBilEl.innerText = '$0 CLP';
                const subMonEl = document.getElementById('subtotalMonedas');
                if (subMonEl) subMonEl.innerText = '$0 CLP';

                const totalArqueoEl = document.getElementById('totalArqueoCalculado');
                if (totalArqueoEl) totalArqueoEl.innerText = '$0 CLP';

                const inputMontoReal = document.getElementById('inputMontoReal');
                if (inputMontoReal) inputMontoReal.value = '0';

                const alertaDiff = document.getElementById('alertaDiferencia');
                if (alertaDiff) {
                    alertaDiff.style.display = 'none';
                    alertaDiff.classList.add('d-none');
                }

                const modalEl = document.getElementById('modalCerrarCaja');
                if (modalEl && window.bootstrap) {
                    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
                    modal.show();
                }
            } else {
                alert(data.error || 'No fue posible obtener el resumen de caja.');
            }
        } catch (err) {
            alert('Error al consultar el estado de la caja.');
        }
    }

    /**
     * Calcula en tiempo real el total de billetes y monedas sumados:
     * Total = (b20*20000) + (b10*10000) + (b5*5000) + (b1*1000) + (m500*500) + (m100*100) + (m50*50) + (m5*5) + (m1*1)
     */
    function calcularTotalDenominaciones() {
        const b20 = parseInt(document.getElementById('cantBilletes20000')?.value, 10) || 0;
        const b10 = parseInt(document.getElementById('cantBilletes10000')?.value, 10) || 0;
        const b5  = parseInt(document.getElementById('cantBilletes5000')?.value, 10) || 0;
        const b1  = parseInt(document.getElementById('cantBilletes1000')?.value, 10) || 0;

        const m500 = parseInt(document.getElementById('cantMonedas500')?.value, 10) || 0;
        const m100 = parseInt(document.getElementById('cantMonedas100')?.value, 10) || 0;
        const m50  = parseInt(document.getElementById('cantMonedas50')?.value, 10) || 0;
        const m5   = parseInt(document.getElementById('cantMonedas5')?.value, 10) || 0;
        const m1   = parseInt(document.getElementById('cantMonedas1')?.value, 10) || 0;

        const subBilletes = (b20 * 20000) + (b10 * 10000) + (b5 * 5000) + (b1 * 1000);
        const subMonedas = (m500 * 500) + (m100 * 100) + (m50 * 50) + (m5 * 5) + (m1 * 1);
        const total = subBilletes + subMonedas;

        const subBilEl = document.getElementById('subtotalBilletes');
        if (subBilEl) subBilEl.innerText = `$${subBilletes.toLocaleString('es-CL')} CLP`;

        const subMonEl = document.getElementById('subtotalMonedas');
        if (subMonEl) subMonEl.innerText = `$${subMonedas.toLocaleString('es-CL')} CLP`;

        const totalArqueoEl = document.getElementById('totalArqueoCalculado');
        if (totalArqueoEl) totalArqueoEl.innerText = `$${total.toLocaleString('es-CL')} CLP`;

        const inputReal = document.getElementById('inputMontoReal');
        if (inputReal) {
            inputReal.value = total;
        }

        calcularDiferenciaLive();
        return total;
    }

    function calcularDiferenciaLive() {
        if (!datosArqueoActivo) return;
        const inputReal = document.getElementById('inputMontoReal');
        if (!inputReal) return;

        const realVal = parseFloat(inputReal.value) || 0;
        const esperado = datosArqueoActivo.efectivo_esperado || 0;
        const diff = realVal - esperado;

        const alerta = document.getElementById('alertaDiferencia');
        const monto = document.getElementById('montoDiferencia');
        const sub = document.getElementById('subtituloDiferencia');
        if (!alerta || !monto || !sub) return;

        alerta.style.display = 'block';
        alerta.classList.remove('d-none');
        alerta.className = 'alert text-center py-2 mb-0 ';

        if (diff === 0) {
            alerta.classList.add('alert-success');
            monto.innerText = '$0 CLP';
            sub.innerText = 'Caja Cuadrada exactamente (Monto coincide con lo esperado)';
        } else if (diff > 0) {
            alerta.classList.add('alert-primary');
            monto.innerText = `+$${diff.toLocaleString('es-CL')} CLP`;
            sub.innerText = 'Sobrante de Caja (Hay más dinero físico que el registrado en sistema)';
        } else {
            alerta.classList.add('alert-danger');
            monto.innerText = `-$${Math.abs(diff).toLocaleString('es-CL')} CLP`;
            sub.innerText = 'Faltante de Caja (Falta dinero respecto a ventas registradas)';
        }
    }

    async function ejecutarCierreCaja() {
        const b20 = parseInt(document.getElementById('cantBilletes20000')?.value, 10) || 0;
        const b10 = parseInt(document.getElementById('cantBilletes10000')?.value, 10) || 0;
        const b5  = parseInt(document.getElementById('cantBilletes5000')?.value, 10) || 0;
        const b1  = parseInt(document.getElementById('cantBilletes1000')?.value, 10) || 0;

        const m500 = parseInt(document.getElementById('cantMonedas500')?.value, 10) || 0;
        const m100 = parseInt(document.getElementById('cantMonedas100')?.value, 10) || 0;
        const m50  = parseInt(document.getElementById('cantMonedas50')?.value, 10) || 0;
        const m5   = parseInt(document.getElementById('cantMonedas5')?.value, 10) || 0;
        const m1   = parseInt(document.getElementById('cantMonedas1')?.value, 10) || 0;

        const inputReal = document.getElementById('inputMontoReal');
        const realVal = inputReal ? inputReal.value.trim() : '';

        if (!confirm('¿Confirma el cierre y arqueo definitivo de la caja?')) return;

        try {
            const resp = await fetch('/caja/cerrar/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    billetes_20000: b20,
                    billetes_10000: b10,
                    billetes_5000: b5,
                    billetes_1000: b1,
                    monedas_500: m500,
                    monedas_100: m100,
                    monedas_50: m50,
                    monedas_5: m5,
                    monedas_1: m1,
                    monto_real: realVal
                })
            });

            const data = await resp.json();
            if (data.success) {
                alert(data.message);
                window.location.reload();
            } else {
                alert(data.error || 'No se pudo cerrar la caja.');
            }
        } catch (err) {
            alert('Error de conexión al cerrar la caja.');
        }
    }

    async function ejecutarAperturaCaja() {
        const cajeroSel = document.getElementById('selectCajeroApertura');
        const montoInp = document.getElementById('inputMontoInicial');
        if (!cajeroSel || !montoInp) return;

        const cajeroId = cajeroSel.value;
        const montoInicial = montoInp.value;

        if (montoInicial === '' || parseFloat(montoInicial) < 0) {
            alert('Debe ingresar un monto inicial (fondo de caja) mayor o igual a 0.');
            return;
        }

        try {
            const resp = await fetch('/caja/abrir/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    cajero_id: cajeroId,
                    monto_inicial: montoInicial
                })
            });

            const data = await resp.json();
            if (data.success) {
                alert(data.message);
                window.location.reload();
            } else {
                alert(data.error || 'No se pudo abrir la caja.');
            }
        } catch (err) {
            alert('Error de conexión al abrir la caja.');
        }
    }

    document.addEventListener('DOMContentLoaded', function() {
        // Conectar botones que abren el modal de arqueo/cierre de caja
        document.querySelectorAll('[data-action="abrir-modal-cierre-caja"]').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                abrirModalCierreCaja();
            });
        });

        // Conectar cálculo en tiempo real ante cambios en cualquier denominación
        document.querySelectorAll('.input-denominacion').forEach(function(inp) {
            inp.addEventListener('input', calcularTotalDenominaciones);
        });

        // Conectar cálculo directo si se modifica el input del total manual
        const inputReal = document.getElementById('inputMontoReal');
        if (inputReal) {
            inputReal.addEventListener('input', calcularDiferenciaLive);
        }

        // Conectar botón de cierre de caja
        document.querySelectorAll('[data-action="ejecutar-cierre-caja"]').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                ejecutarCierreCaja();
            });
        });

        // Conectar botón de apertura de caja
        document.querySelectorAll('[data-action="ejecutar-apertura-caja"]').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                ejecutarAperturaCaja();
            });
        });
    });

    // Exponer en objeto global para compatibilidad
    window.Cuadratura = {
        abrirModalCierreCaja: abrirModalCierreCaja,
        calcularTotalDenominaciones: calcularTotalDenominaciones,
        calcularDiferenciaLive: calcularDiferenciaLive,
        ejecutarCierreCaja: ejecutarCierreCaja,
        ejecutarAperturaCaja: ejecutarAperturaCaja,
        getCookie: getCookie
    };
})();
