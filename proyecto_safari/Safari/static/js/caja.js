/**
 * Safari POS - Módulo Terminal de Caja POS (cajero.html)
 * Gestiona pedidos en barra inmediata, liquidación de mesas de salón,
 * catálogo táctil, carrito de compras, emisión de boleta y comprobante térmico.
 */
(function() {
    'use strict';

    let PRODUCTOS = [];
    let carrito = []; // [{ id, nombre, precio, cantidad, stock }]
    let modoActivo = 'barra'; // 'barra' | 'mesa'
    let mesaCuentaActiva = null; // Detalle de la comanda de mesa cargada para liquidar

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

    function mostrarAlerta(tipo, mensaje) {
        const cont = document.getElementById('alertContainer');
        if (!cont) return;
        cont.innerHTML = `
            <div class="alert alert-${tipo} alert-dismissible fade show shadow-sm" role="alert">
                <i class="bi bi-info-circle-fill me-2"></i> ${mensaje}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        setTimeout(() => { cont.innerHTML = ''; }, 4500);
    }

    function cambiarSeccionCajero(seccion) {
        modoActivo = seccion === 'mesas' ? 'mesa' : 'barra';
        const btnBarra = document.getElementById('btnTabBarra');
        const btnMesas = document.getElementById('btnTabMesas');
        const secBarra = document.getElementById('contenedorSeccionBarra');
        const secMesas = document.getElementById('contenedorSeccionMesas');

        if (seccion === 'barra') {
            if (btnBarra) btnBarra.classList.add('active');
            if (btnMesas) btnMesas.classList.remove('active');
            if (secBarra) secBarra.classList.remove('d-none');
            if (secMesas) secMesas.classList.add('d-none');
            renderizarCarrito();
        } else {
            if (btnBarra) btnBarra.classList.remove('active');
            if (btnMesas) btnMesas.classList.add('active');
            if (secBarra) secBarra.classList.add('d-none');
            if (secMesas) secMesas.classList.remove('d-none');
            const totalMesa = mesaCuentaActiva ? mesaCuentaActiva.total : 0;
            const totalMesaEl = document.getElementById('totalMontoMesa');
            if (totalMesaEl) {
                totalMesaEl.textContent = `$${totalMesa.toLocaleString()} CLP`;
            }
        }
    }

    function cambiarModalidad(nuevoModo) {
        cambiarSeccionCajero(nuevoModo === 'mesa' ? 'mesas' : 'barra');
    }

    function agregarAlCarrito(prodId) {
        if (modoActivo !== 'barra') {
            // Cambiar automáticamente a modo barra
            const radioBarra = document.getElementById('modoBarra');
            if (radioBarra) {
                radioBarra.checked = true;
                cambiarModalidad('barra');
            }
        }

        const prod = PRODUCTOS.find(p => p.id === prodId);
        if (!prod) return;

        if (prod.stock <= 0) {
            mostrarAlerta('danger', `El producto "${prod.nombre}" no tiene stock disponible.`);
            return;
        }

        const cantMax = Math.min(50, prod.stock);
        if (cantMax <= 0) {
            mostrarAlerta('danger', `El producto "${prod.nombre}" no tiene stock disponible.`);
            return;
        }

        const itemEnCarrito = carrito.find(i => i.id === prodId);
        if (itemEnCarrito) {
            if (itemEnCarrito.cantidad < cantMax) {
                itemEnCarrito.cantidad += 1;
            } else {
                mostrarAlerta('warning', `Límite máximo alcanzado para "${prod.nombre}" (${cantMax} un., máx 50 por pedido).`);
            }
        } else {
            carrito.push({
                id: prod.id,
                nombre: prod.nombre,
                precio: prod.precio,
                cantidad: 1,
                stock: prod.stock
            });
        }
        renderizarCarrito();
    }

    function cambiarCantidad(prodId, delta) {
        const item = carrito.find(i => i.id === prodId);
        if (!item) return;

        const cantMax = Math.min(50, item.stock);
        item.cantidad += delta;
        if (item.cantidad <= 0) {
            carrito = carrito.filter(i => i.id !== prodId);
        } else if (item.cantidad > cantMax) {
            item.cantidad = cantMax;
            mostrarAlerta('warning', `No puede agregar más de ${cantMax} unidades (límite de 50 o stock disponible).`);
        }
        renderizarCarrito();
    }

    function limpiarCarrito() {
        carrito = [];
        const notasInput = document.getElementById('inputNotasComanda');
        if (notasInput) notasInput.value = '';
        renderizarCarrito();
    }

    function renderizarCarrito() {
        const lista = document.getElementById('listaCarrito');
        const vacioMsg = document.getElementById('carritoVacioMsg');
        const totalEl = document.getElementById('totalMonto');
        if (!lista || !vacioMsg || !totalEl) return;

        lista.innerHTML = '';
        if (carrito.length === 0) {
            vacioMsg.style.display = 'block';
            if (modoActivo === 'barra') {
                totalEl.textContent = '$0 CLP';
            }
            return;
        }

        vacioMsg.style.display = 'none';
        let total = 0;

        carrito.forEach(item => {
            const subtotal = item.precio * item.cantidad;
            total += subtotal;

            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-center px-0 py-2 border-0 border-bottom';
            li.innerHTML = `
                <div class="me-auto">
                    <strong class="d-block small text-dark">${item.nombre}</strong>
                    <small class="text-muted">$${item.precio.toLocaleString()} c/u</small>
                </div>
                <div class="d-flex align-items-center">
                    <button type="button" class="btn btn-sm btn-outline-secondary px-2 py-0 fw-bold" data-action="cambiar-cantidad" data-id="${item.id}" data-delta="-1">-</button>
                    <span class="px-2 fw-bold small">${item.cantidad}</span>
                    <button type="button" class="btn btn-sm btn-outline-secondary px-2 py-0 fw-bold" data-action="cambiar-cantidad" data-id="${item.id}" data-delta="1" ${item.cantidad >= Math.min(50, item.stock) ? 'disabled' : ''}>+</button>
                </div>
                <div class="text-end fw-bold small ms-2 text-success">
                    $${subtotal.toLocaleString()}
                </div>
            `;
            lista.appendChild(li);
        });

        if (modoActivo === 'barra') {
            totalEl.textContent = `$${total.toLocaleString()} CLP`;
        }
    }

    /**
     * Venta Rápida en Barra (Inmediata):
     * Emite boleta correlativa de inmediato (BOL-XXXX), descuenta stock y envía comanda a cocina.
     */
    async function procesarVenta() {
        if (carrito.length === 0) {
            mostrarAlerta('warning', 'Agregue productos al pedido antes de cobrar.');
            return;
        }

        const btn = document.getElementById('btnEmitirVenta');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Procesando...`;
        }

        const radioPago = document.querySelector('input[name="metodoPagoRadio"]:checked');
        const metodoPago = radioPago ? radioPago.value : 'efectivo';
        const meseroSel = document.getElementById('selectMesero');
        const meseroId = meseroSel ? meseroSel.value : '';
        const mesaSel = document.getElementById('selectMesa');
        const notasInput = document.getElementById('inputNotasComanda');
        const notas = notasInput ? notasInput.value.trim() : '';

        const payload = {
            tipo_venta: 'barra',
            mesa: mesaSel ? mesaSel.value : 'Barra Principal',
            mesero_id: meseroId ? parseInt(meseroId, 10) : null,
            metodo_pago: metodoPago,
            notas: notas,
            items: carrito.map(i => ({ id: i.id, cantidad: i.cantidad })),
            total: carrito.reduce((sum, i) => sum + (i.precio * i.cantidad), 0)
        };

        try {
            const response = await fetch('/cajero/registrar-venta/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();
            if (data.success) {
                // Armar Comprobante / Voucher Térmico
                const tkFolio = document.getElementById('tkFolio');
                const tkFecha = document.getElementById('tkFecha');
                const tkMesa = document.getElementById('tkMesa');
                const tkMetodoPago = document.getElementById('tkMetodoPago');
                const tkTotal = document.getElementById('tkTotal');

                if (tkFolio) tkFolio.innerText = data.folio;
                if (tkFecha) tkFecha.innerText = new Date().toLocaleString('es-CL');
                if (tkMesa) tkMesa.innerText = `${payload.mesa} (Barra Inmediata)`;
                if (tkMetodoPago) tkMetodoPago.innerText = metodoPago.toUpperCase();
                if (tkTotal) tkTotal.innerText = `$${payload.total.toLocaleString()} CLP`;

                const detalleTbody = document.getElementById('tkDetalle');
                if (detalleTbody) {
                    detalleTbody.innerHTML = '';
                    carrito.forEach(i => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td>${i.cantidad}</td>
                            <td>${i.nombre}</td>
                            <td class="text-end">$${(i.precio * i.cantidad).toLocaleString()}</td>
                        `;
                        detalleTbody.appendChild(tr);
                    });
                }

                // Mostrar modal del comprobante
                const modalEl = document.getElementById('modalVoucher');
                if (modalEl && window.bootstrap) {
                    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
                    modal.show();
                }

                // Limpiar carrito local y notas
                carrito = [];
                if (notasInput) notasInput.value = '';
                renderizarCarrito();
            } else {
                mostrarAlerta('danger', data.error || 'No se pudo procesar la venta.');
            }
        } catch (err) {
            mostrarAlerta('danger', 'Error de conexión con el servidor al registrar venta.');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<i class="bi bi-check-circle-fill me-1"></i> Pagar y Emitir Boleta (Barra)`;
            }
        }
    }

    /**
     * Carga el detalle de la comanda activa de una mesa física seleccionada.
     */
    async function cargarCuentaMesa(mesaId) {
        const infoMesa = document.getElementById('infoMesaSeleccionada');
        const sinMesaMsg = document.getElementById('sinMesaSeleccionadaMsg');
        const btnLiquidar = document.getElementById('btnLiquidarMesa');
        const totalEl = document.getElementById('totalMontoMesa') || document.getElementById('totalMonto');
        const badgeMesa = document.getElementById('badgeMesaActivaCobro');
        const selectMesaCobro = document.getElementById('selectMesaCobro');

        if (!mesaId) {
            mesaCuentaActiva = null;
            if (infoMesa) infoMesa.classList.add('d-none');
            if (sinMesaMsg) sinMesaMsg.classList.remove('d-none');
            if (btnLiquidar) btnLiquidar.disabled = true;
            if (totalEl) totalEl.textContent = '$0 CLP';
            if (badgeMesa) badgeMesa.textContent = 'Ninguna';
            return;
        }

        if (selectMesaCobro && selectMesaCobro.value !== String(mesaId)) {
            selectMesaCobro.value = String(mesaId);
        }

        try {
            const resp = await fetch(`/cajero/mesa-cuenta/${mesaId}/`);
            const data = await resp.json();

            if (data.success) {
                mesaCuentaActiva = data;

                // Actualizar encabezado del detalle de mesa
                const elNombre = document.getElementById('detalleMesaNombre');
                const elFolio = document.getElementById('detalleMesaFolio');
                const elMesero = document.getElementById('detalleMesaMesero');
                const elEstado = document.getElementById('detalleMesaEstadoCocina');
                const contNotas = document.getElementById('contenedorNotasMesa');
                const elNotas = document.getElementById('detalleMesaNotas');

                if (elNombre) elNombre.textContent = data.mesa_nombre;
                if (elFolio) elFolio.textContent = data.folio;
                if (elMesero) elMesero.textContent = data.mesero || 'Garzón';
                if (badgeMesa) badgeMesa.textContent = data.mesa_nombre;
                if (elEstado) {
                    if (data.listo_para_cobro) {
                        elEstado.textContent = 'LISTO PARA COBRO';
                        elEstado.className = 'badge bg-warning text-dark fw-bold';
                    } else {
                        elEstado.textContent = (data.estado_comanda || 'EN ESPERA').toUpperCase();
                        elEstado.className = `badge ${data.estado_comanda === 'listo' ? 'bg-success' : (data.estado_comanda === 'preparacion' ? 'bg-warning text-dark' : 'bg-primary')}`;
                    }
                }

                if (data.notas && data.notas.trim() !== '') {
                    if (contNotas) contNotas.classList.remove('d-none');
                    if (elNotas) elNotas.textContent = `"${data.notas}"`;
                } else {
                    if (contNotas) contNotas.classList.add('d-none');
                }

                // Renderizar lista de ítems de la comanda
                const listaItems = document.getElementById('listaItemsMesa');
                if (listaItems) {
                    listaItems.innerHTML = '';
                    if (Array.isArray(data.items) && data.items.length > 0) {
                        data.items.forEach(it => {
                            const li = document.createElement('li');
                            li.className = 'list-group-item d-flex justify-content-between align-items-center px-0 py-2 border-0 border-bottom';
                            li.innerHTML = `
                                <div class="me-auto">
                                    <strong class="d-block small text-dark">${it.nombre}</strong>
                                    <small class="text-muted">$${it.precio.toLocaleString()} c/u</small>
                                </div>
                                <div class="d-flex align-items-center">
                                    <span class="badge bg-secondary px-2 py-1 font-xs">${it.cantidad} un.</span>
                                </div>
                                <div class="text-end fw-bold small ms-2 text-primary">
                                    $${it.subtotal.toLocaleString()}
                                </div>
                            `;
                            listaItems.appendChild(li);
                        });
                    } else {
                        listaItems.innerHTML = `<li class="list-group-item text-muted small py-2">${data.items_texto || 'Detalle no disponible'}</li>`;
                    }
                }

                if (totalEl) totalEl.textContent = `$${data.total.toLocaleString()} CLP`;
                if (infoMesa) infoMesa.classList.remove('d-none');
                if (sinMesaMsg) sinMesaMsg.classList.add('d-none');
                if (btnLiquidar) btnLiquidar.disabled = false;
            } else {
                mostrarAlerta('danger', data.error || 'No se pudo cargar la cuenta de la mesa.');
                mesaCuentaActiva = null;
                if (btnLiquidar) btnLiquidar.disabled = true;
            }
        } catch (err) {
            mostrarAlerta('danger', 'Error al obtener la comanda de la mesa.');
        }
    }

    /**
     * Liquidar Mesa de Salón:
     * El cliente solicita la cuenta, el cajero liquida la mesa en su terminal:
     * - Descuenta el stock en este momento.
     * - Emite boleta correlativa oficial (BOL-XXXX).
     * - Marca comanda como pagada y desocupa la mesa ('desocupada').
     */
    async function liquidarMesa() {
        if (!mesaCuentaActiva) {
            mostrarAlerta('warning', 'Seleccione una mesa con cuenta activa para liquidar.');
            return;
        }

        const btn = document.getElementById('btnLiquidarMesa');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Liquidando...`;
        }

        const radioPagoMesa = document.querySelector('input[name="metodoPagoMesaRadio"]:checked');
        const radioPagoBarra = document.querySelector('input[name="metodoPagoRadio"]:checked');
        const metodoPago = radioPagoMesa ? radioPagoMesa.value : (radioPagoBarra ? radioPagoBarra.value : 'efectivo');

        const payload = {
            mesa_id: mesaCuentaActiva.mesa_id,
            comanda_id: mesaCuentaActiva.comanda_id,
            metodo_pago: metodoPago
        };

        try {
            const resp = await fetch('/cajero/liquidar-mesa/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(payload)
            });

            const data = await resp.json();
            if (data.success) {
                // Armar Comprobante / Voucher Térmico de la Boleta emitida
                const tkFolio = document.getElementById('tkFolio');
                const tkFecha = document.getElementById('tkFecha');
                const tkMesa = document.getElementById('tkMesa');
                const tkMetodoPago = document.getElementById('tkMetodoPago');
                const tkTotal = document.getElementById('tkTotal');

                if (tkFolio) tkFolio.innerText = data.folio;
                if (tkFecha) tkFecha.innerText = new Date().toLocaleString('es-CL');
                if (tkMesa) tkMesa.innerText = `${data.mesa} (Mesa de Salón)`;
                if (tkMetodoPago) tkMetodoPago.innerText = metodoPago.toUpperCase();
                if (tkTotal) tkTotal.innerText = `$${data.total.toLocaleString()} CLP`;

                const detalleTbody = document.getElementById('tkDetalle');
                if (detalleTbody) {
                    detalleTbody.innerHTML = '';
                    if (Array.isArray(mesaCuentaActiva.items)) {
                        mesaCuentaActiva.items.forEach(i => {
                            const tr = document.createElement('tr');
                            tr.innerHTML = `
                                <td>${i.cantidad}</td>
                                <td>${i.nombre}</td>
                                <td class="text-end">$${i.subtotal.toLocaleString()}</td>
                            `;
                            detalleTbody.appendChild(tr);
                        });
                    }
                }

                // Mostrar modal del comprobante
                const modalEl = document.getElementById('modalVoucher');
                if (modalEl && window.bootstrap) {
                    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
                    modal.show();
                }

                mostrarAlerta('success', data.message || `Mesa ${data.mesa} liquidada. Boleta ${data.folio} emitida.`);

                // Quitar tarjeta del grid visual de mesas
                const cardMesa = document.getElementById(`cardMesaItem-${mesaCuentaActiva.mesa_id}`);
                if (cardMesa) cardMesa.remove();

                // Quitar mesa del selector de mesas con cuenta
                const selectMesaCobro = document.getElementById('selectMesaCobro');
                if (selectMesaCobro) {
                    const optToRemove = selectMesaCobro.querySelector(`option[value="${mesaCuentaActiva.mesa_id}"]`);
                    if (optToRemove) optToRemove.remove();
                    selectMesaCobro.value = '';
                }

                // Actualizar contadores y badges de cuentas pendientes
                const count = document.querySelectorAll('.item-mesa-card').length;
                const badgeTab = document.getElementById('badgeCuentasPendientesTab');
                const badgeTotal = document.getElementById('badgeTotalMesasPendientes');
                if (badgeTab) {
                    badgeTab.textContent = count;
                    if (count === 0) badgeTab.classList.add('d-none');
                }
                if (badgeTotal) {
                    badgeTotal.textContent = `${count} Mesas Activas`;
                }

                const grid = document.getElementById('gridMesasPendientes');
                if (grid && count === 0) {
                    grid.innerHTML = `
                        <div class="col-12 text-center py-5 text-muted" id="sinMesasPendientesMsg">
                            <i class="bi bi-check2-circle fs-1 text-success d-block mb-2"></i>
                            <strong class="d-block fs-6">No hay cuentas pendientes en este momento.</strong>
                            <span class="small">Todas las mesas de salón están desocupadas o al día.</span>
                        </div>
                    `;
                }

                // Limpiar estado
                mesaCuentaActiva = null;
                const infoMesa = document.getElementById('infoMesaSeleccionada');
                const sinMesaMsg = document.getElementById('sinMesaSeleccionadaMsg');
                const totalMesaEl = document.getElementById('totalMontoMesa') || document.getElementById('totalMonto');
                const badgeMesaActiva = document.getElementById('badgeMesaActivaCobro');
                if (infoMesa) infoMesa.classList.add('d-none');
                if (sinMesaMsg) sinMesaMsg.classList.remove('d-none');
                if (totalMesaEl) totalMesaEl.textContent = '$0 CLP';
                if (badgeMesaActiva) badgeMesaActiva.textContent = 'Ninguna';
            } else {
                mostrarAlerta('danger', data.error || 'No se pudo liquidar la mesa.');
            }
        } catch (err) {
            mostrarAlerta('danger', 'Error de conexión al liquidar mesa.');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<i class="bi bi-receipt me-1"></i> Liquidar Mesa y Emitir Boleta`;
            }
        }
    }

    function normalizarTexto(texto) {
        return (texto || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim();
    }

    function filtrarProductos() {
        const input = document.getElementById('filtroBuscar');
        if (!input) return;
        const q = normalizarTexto(input.value);
        document.querySelectorAll('.item-producto').forEach(item => {
            const nombre = normalizarTexto(item.getAttribute('data-nombre') || '');
            const categoria = normalizarTexto(item.getAttribute('data-categoria') || '');
            const coincide = (q === '') || nombre.includes(q) || categoria.includes(q);
            item.classList.toggle('d-none', !coincide);
        });
    }

    function filtrarMesasPendientes() {
        const input = document.getElementById('filtroMesasPendientes');
        if (!input) return;
        const q = normalizarTexto(input.value);
        document.querySelectorAll('.item-mesa-card').forEach(item => {
            const nombre = normalizarTexto(item.getAttribute('data-mesa-nombre') || '');
            const mesero = normalizarTexto(item.getAttribute('data-mesero') || '');
            const folio = normalizarTexto(item.getAttribute('data-folio') || '');
            const coincide = (q === '') || nombre.includes(q) || mesero.includes(q) || folio.includes(q);
            item.classList.toggle('d-none', !coincide);
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        // Cargar catálogo de productos desde script JSON seguro
        const scriptData = document.getElementById('productos-data');
        if (scriptData) {
            try {
                PRODUCTOS = JSON.parse(scriptData.textContent);
            } catch (e) {
                console.error("Error al parsear catálogo de productos:", e);
            }
        }

        // Pestañas / Separación visual entre Ventas en Barra y Cuentas por Mesa
        document.body.addEventListener('click', function(e) {
            const btnSeccion = e.target.closest('[data-action="cambiar-seccion-cajero"]');
            if (btnSeccion) {
                e.preventDefault();
                const seccion = btnSeccion.getAttribute('data-seccion');
                if (seccion) {
                    cambiarSeccionCajero(seccion);
                }
                return;
            }

            const btnCargarMesa = e.target.closest('[data-action="cargar-mesa-para-cobro"]');
            if (btnCargarMesa) {
                e.preventDefault();
                const mesaId = btnCargarMesa.getAttribute('data-mesa-id');
                if (mesaId) {
                    cargarCuentaMesa(mesaId);
                }
                return;
            }
        });

        // Selector de Modalidad (Venta en Barra vs Cobro de Mesa)
        const radiosModalidad = document.querySelectorAll('input[name="modalidadVentaRadio"]');
        radiosModalidad.forEach(radio => {
            radio.addEventListener('change', function() {
                cambiarModalidad(this.value);
            });
        });

        // Selector de Mesa a Liquidar
        const selectMesaCobro = document.getElementById('selectMesaCobro');
        if (selectMesaCobro) {
            selectMesaCobro.addEventListener('change', function() {
                const mesaId = this.value;
                cargarCuentaMesa(mesaId);
            });
        }

        // Botón Liquidar Mesa
        const btnLiquidar = document.getElementById('btnLiquidarMesa');
        if (btnLiquidar) {
            btnLiquidar.addEventListener('click', function(e) {
                e.preventDefault();
                liquidarMesa();
            });
        }

        // Delegación de clic para agregar producto al carrito desde la cuadrícula
        const catalogo = document.getElementById('contenedorProductos');
        if (catalogo) {
            catalogo.addEventListener('click', function(e) {
                const card = e.target.closest('[data-action="agregar-al-carrito"]');
                if (card) {
                    const prodId = parseInt(card.getAttribute('data-id'), 10);
                    if (!isNaN(prodId)) {
                        agregarAlCarrito(prodId);
                    }
                }
            });
        }

        // Delegación de clic para cambiar cantidades dentro del carrito
        const listaCarrito = document.getElementById('listaCarrito');
        if (listaCarrito) {
            listaCarrito.addEventListener('click', function(e) {
                const btn = e.target.closest('[data-action="cambiar-cantidad"]');
                if (btn) {
                    const prodId = parseInt(btn.getAttribute('data-id'), 10);
                    const delta = parseInt(btn.getAttribute('data-delta'), 10);
                    if (!isNaN(prodId) && !isNaN(delta)) {
                        cambiarCantidad(prodId, delta);
                    }
                }
            });
        }

        // Botón limpiar carrito
        const btnLimpiar = document.getElementById('btnLimpiarCarrito');
        if (btnLimpiar) {
            btnLimpiar.addEventListener('click', function(e) {
                e.preventDefault();
                limpiarCarrito();
            });
        }

        // Botón emitir venta en barra
        const btnVenta = document.getElementById('btnEmitirVenta');
        if (btnVenta) {
            btnVenta.addEventListener('click', function(e) {
                e.preventDefault();
                procesarVenta();
            });
        }

        // Filtro buscador de productos
        const inputFiltro = document.getElementById('filtroBuscar');
        if (inputFiltro) {
            inputFiltro.addEventListener('input', filtrarProductos);
            inputFiltro.addEventListener('keyup', filtrarProductos);
        }

        // Filtro buscador de mesas pendientes
        const inputFiltroMesas = document.getElementById('filtroMesasPendientes');
        if (inputFiltroMesas) {
            inputFiltroMesas.addEventListener('input', filtrarMesasPendientes);
            inputFiltroMesas.addEventListener('keyup', filtrarMesasPendientes);
        }

        // Botón imprimir comprobante térmico
        document.querySelectorAll('[data-action="imprimir-voucher"]').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                window.print();
            });
        });

        // Botón cerrar modal voucher y recargar
        document.querySelectorAll('[data-action="cerrar-recargar"]').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                window.location.reload();
            });
        });
    });
})();
