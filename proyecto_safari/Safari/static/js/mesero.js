/**
 * Safari POS - Módulo de Mesero (mesero.html)
 * Navegación por pestañas (Tabs) estilo Google Chrome:
 * Tab 1: Listos para Servir (Prioritario / Alerta de Cocina)
 * Tab 2: Mesas Disponibles
 * Tab 3: Mesas Ocupadas
 * Tab 4: Mesas Servidas / Cobro
 * Polling periódico cada 5-8s para sincronización con cocina y contadores en vivo.
 */
(function() {
    'use strict';

    const STORAGE_KEY_TAB = 'tab_mesero_activa';
    const TABS_VALIDAS = ['listos_servir', 'disponibles', 'ocupadas', 'servidas'];
    const INTERVALO_POLLING_MS = 6000; // 6 segundos

    let PRODUCTOS = [];
    let itemsPedidoActual = {}; // { prodId: cantidad }
    let pollingIntervalId = null;
    let ultimoTotalListos = -1;

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

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function mostrarAlertaMesero(tipo, mensaje) {
        const contenedor = document.getElementById('alertContainerMesero');
        if (!contenedor) return;

        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${tipo} alert-dismissible fade show shadow-sm text-dark`;
        alertDiv.setAttribute('role', 'alert');

        const icono = tipo === 'success' ? 'bi-check-circle-fill' : 'bi-exclamation-triangle-fill';
        alertDiv.innerHTML = `
            <i class="bi ${icono} me-2"></i> ${escapeHtml(mensaje)}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Cerrar"></button>
        `;

        contenedor.appendChild(alertDiv);
        setTimeout(function() {
            alertDiv.remove();
        }, 4500);
    }

    // =========================================================================
    // GESTIÓN DE PESTAÑAS (TABS CHROME STYLE)
    // =========================================================================

    function obtenerTabActiva() {
        try {
            const stored = sessionStorage.getItem(STORAGE_KEY_TAB);
            if (stored && TABS_VALIDAS.includes(stored)) {
                return stored;
            }
        } catch (e) {
            console.warn('sessionStorage no disponible:', e);
        }

        const navStrip = document.querySelector('.chrome-tabstrip');
        if (navStrip && navStrip.dataset.tabActiva && TABS_VALIDAS.includes(navStrip.dataset.tabActiva)) {
            return navStrip.dataset.tabActiva;
        }

        const tabActivaEl = document.querySelector('.chrome-tab.active');
        if (tabActivaEl && tabActivaEl.dataset.tabTarget && TABS_VALIDAS.includes(tabActivaEl.dataset.tabTarget)) {
            return tabActivaEl.dataset.tabTarget;
        }

        return 'disponibles';
    }

    function activarTab(tabId) {
        if (!TABS_VALIDAS.includes(tabId)) tabId = 'disponibles';

        // 1. Actualizar estado visual de los botones de pestañas
        document.querySelectorAll('.chrome-tab').forEach(tab => {
            const esActiva = (tab.dataset.tabTarget === tabId);
            tab.classList.toggle('active', esActiva);
            tab.setAttribute('aria-selected', esActiva ? 'true' : 'false');
        });

        // 2. Alternar visibilidad de los paneles de contenido
        document.querySelectorAll('.tab-pane-mesero').forEach(panel => {
            panel.classList.add('d-none');
        });

        const panelActivo = document.getElementById(`tab-pane-${tabId}`);
        if (panelActivo) {
            panelActivo.classList.remove('d-none');
        }

        // 3. Persistir en sessionStorage
        try {
            sessionStorage.setItem(STORAGE_KEY_TAB, tabId);
        } catch (e) {}

        const navStrip = document.querySelector('.chrome-tabstrip');
        if (navStrip) navStrip.dataset.tabActiva = tabId;
    }

    // =========================================================================
    // MARCAR COMO SERVIDO / ENTREGADO (AJAX)
    // =========================================================================

    async function marcarComandaServida(comandaId, mesaId, mesaNombre, btnEl) {
        if (btnEl) {
            btnEl.disabled = true;
            btnEl.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Marcando como servido...`;
        }

        try {
            const resp = await fetch('/mesero/marcar-entregado/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    comanda_id: comandaId ? parseInt(comandaId, 10) : null,
                    mesa_id: mesaId ? parseInt(mesaId, 10) : null
                })
            });

            const data = await resp.json();
            if (data.success) {
                mostrarAlertaMesero('success', `✓ Comanda ${data.folio || ''} servida exitosamente en ${data.mesa_nombre || mesaNombre}.`);

                // Remover la tarjeta de la comanda lista del DOM con animación suave
                const card = document.getElementById(`cardComandaListo-${comandaId}`);
                if (card) {
                    card.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                    card.style.opacity = '0';
                    card.style.transform = 'scale(0.95)';
                    setTimeout(() => {
                        card.remove();
                        const itemsRestantes = document.querySelectorAll('.item-comanda-listo').length;
                        if (itemsRestantes === 0) {
                            const emptyState = document.getElementById('empty-state-listos_servir');
                            if (emptyState) emptyState.classList.remove('d-none');
                        }
                    }, 300);
                }

                // Ejecutar sondeo inmediato para refrescar las demás pestañas y contadores
                ejecutarPolling();
            } else {
                mostrarAlertaMesero('danger', data.error || 'No se pudo marcar la comanda como servida.');
                if (btnEl) {
                    btnEl.disabled = false;
                    btnEl.innerHTML = `<i class="bi bi-check-circle-fill me-1"></i> Marcar como Servido / Entregado`;
                }
            }
        } catch (e) {
            mostrarAlertaMesero('danger', 'Error de conexión con el servidor al marcar la comanda.');
            if (btnEl) {
                btnEl.disabled = false;
                btnEl.innerHTML = `<i class="bi bi-check-circle-fill me-1"></i> Marcar como Servido / Entregado`;
            }
        }
    }

    // =========================================================================
    // POLLING EN TIEMPO REAL (CADA 5-8 SEGUNDOS)
    // =========================================================================

    function renderizarComandasListas(comandas) {
        const grid = document.getElementById('gridListosServir');
        const emptyState = document.getElementById('empty-state-listos_servir');
        if (!grid) return;

        if (!Array.isArray(comandas) || comandas.length === 0) {
            grid.innerHTML = '';
            if (emptyState) emptyState.classList.remove('d-none');
            return;
        }

        if (emptyState) emptyState.classList.add('d-none');

        // Comprobar si los IDs son idénticos para no re-renderizar innecesariamente el DOM
        const idsActuales = Array.from(grid.querySelectorAll('.item-comanda-listo')).map(el => el.id.replace('cardComandaListo-', ''));
        const idsNuevos = comandas.map(c => String(c.id));
        if (JSON.stringify(idsActuales) === JSON.stringify(idsNuevos)) {
            return; // Sin cambios en la lista
        }

        grid.innerHTML = '';
        comandas.forEach(cmd => {
            const col = document.createElement('div');
            col.className = 'col item-comanda-listo';
            col.id = `cardComandaListo-${cmd.id}`;
            col.innerHTML = `
                <div class="card h-100 shadow-sm mesa-card mesa-card-listo">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <strong class="fs-5 text-warning">${escapeHtml(cmd.mesa)}</strong>
                        <span class="badge bg-success"><i class="bi bi-bell-fill me-1"></i> ¡LISTO!</span>
                    </div>
                    <div class="card-body p-3 d-flex flex-column justify-content-between">
                        <div>
                            <div class="d-flex justify-content-between small text-muted mb-2">
                                <span>Folio: <strong class="text-white">${escapeHtml(cmd.folio)}</strong></span>
                                <span>Hora: <strong class="text-white">${escapeHtml(cmd.hora || '')}</strong></span>
                            </div>
                            ${cmd.es_reemision ? `
                                <div class="badge bg-danger mb-2 font-2xs d-inline-block">
                                    <i class="bi bi-arrow-repeat me-1"></i> RE-COCINADO: ${escapeHtml(cmd.motivo_reemision || 'Cambio')}
                                </div>
                            ` : ''}
                            <div class="bg-dark p-2 rounded border border-secondary mb-2 text-start">
                                <strong class="text-warning font-xs d-block mb-1"><i class="bi bi-basket me-1"></i> Detalle a Servir:</strong>
                                <div class="text-light small">${escapeHtml(cmd.items)}</div>
                            </div>
                            ${cmd.notas ? `
                                <div class="alert alert-warning py-1 px-2 small mb-2 text-dark font-2xs">
                                    <i class="bi bi-chat-left-dots-fill me-1"></i> ${escapeHtml(cmd.notas)}
                                </div>
                            ` : ''}
                            <div class="text-end small text-muted">
                                Total: <strong class="text-success">$${Number(cmd.total).toLocaleString('es-CL')} CLP</strong>
                            </div>
                        </div>
                        <div class="pt-3">
                            <button type="button" class="btn btn-success fw-bold w-100 shadow-sm" data-action="marcar-comanda-servida" data-comanda-id="${cmd.id}" data-mesa-id="${cmd.mesa_id || ''}" data-mesa-nombre="${escapeHtml(cmd.mesa)}">
                                <i class="bi bi-check-circle-fill me-1"></i> Marcar como Servido / Entregado
                            </button>
                        </div>
                    </div>
                </div>
            `;
            grid.appendChild(col);
        });
    }

    async function ejecutarPolling() {
        try {
            const resp = await fetch('/api/mesero/estado/');
            if (!resp.ok) return;

            const data = await resp.json();
            if (!data.success) return;

            const c = data.contadores || {};

            // 1. Actualizar contadores numéricos en las pestañas
            const elCListos = document.getElementById('tab-counter-listos-servir');
            const elCDisp = document.getElementById('tab-counter-disponibles');
            const elCOcup = document.getElementById('tab-counter-ocupadas');
            const elCServ = document.getElementById('tab-counter-servidas');

            if (elCListos) {
                elCListos.textContent = c.listos_servir !== undefined ? c.listos_servir : '0';
                if (c.listos_servir > 0) {
                    elCListos.classList.add('animate-pulse');
                } else {
                    elCListos.classList.remove('animate-pulse');
                }
            }
            if (elCDisp) elCDisp.textContent = c.disponibles !== undefined ? c.disponibles : '0';
            if (elCOcup) elCOcup.textContent = c.ocupadas !== undefined ? c.ocupadas : '0';
            if (elCServ) elCServ.textContent = c.servidas !== undefined ? c.servidas : '0';

            // 2. Alerta visual cuando Cocina termina una orden nueva
            if (ultimoTotalListos >= 0 && c.listos_servir > ultimoTotalListos) {
                mostrarAlertaMesero('success', `🔔 ¡Atención! Cocina terminó una comanda. Hay ${c.listos_servir} pedido(s) listos para servir.`);
            }
            ultimoTotalListos = c.listos_servir;

            // 3. Renderizar las comandas listas en Tab 1
            if (Array.isArray(data.comandas_listas)) {
                renderizarComandasListas(data.comandas_listas);
            }

        } catch (e) {
            console.warn('Error en polling de mesero:', e);
        }
    }

    function iniciarPolling() {
        if (pollingIntervalId) clearInterval(pollingIntervalId);
        pollingIntervalId = setInterval(ejecutarPolling, INTERVALO_POLLING_MS);
    }

    // =========================================================================
    // FUNCIONALIDADES EXISTENTES (CATÁLOGO, MODALES, PEDIDOS Y RE-ÓRDENES)
    // =========================================================================

    function cargarProductosData() {
        const scriptEl = document.getElementById('productos-data');
        if (scriptEl && scriptEl.textContent) {
            try {
                PRODUCTOS = JSON.parse(scriptEl.textContent);
            } catch (e) {
                PRODUCTOS = [];
            }
        }
    }

    function abrirModalPedido(mesaId, mesaNombre) {
        itemsPedidoActual = {};
        const inputMesaId = document.getElementById('pedidoMesaId');
        const tituloMesa = document.getElementById('pedidoMesaTitulo');
        const inputNotas = document.getElementById('pedidoNotas');
        const alertaError = document.getElementById('alertaErrorPedido');
        const totalDisplay = document.getElementById('pedidoTotalDisplay');

        if (inputMesaId) inputMesaId.value = mesaId;
        if (tituloMesa) tituloMesa.innerText = mesaNombre;
        if (inputNotas) inputNotas.value = '';
        if (alertaError) {
            alertaError.classList.add('d-none');
            alertaError.innerText = '';
        }
        if (totalDisplay) totalDisplay.innerText = '$0 CLP';

        // Reset contadores visibles
        document.querySelectorAll('[id^="cant-pedido-"]').forEach(span => {
            span.innerText = '0';
        });

        const modalEl = document.getElementById('modalTomarPedido');
        if (modalEl && window.bootstrap) {
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        }
    }

    function normalizarTexto(texto) {
        return (texto || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim();
    }

    function modificarCantidadPedido(prodId, delta) {
        const prod = PRODUCTOS.find(p => p.id === prodId);
        if (!prod) return;

        if (delta > 0 && prod.stock <= 0) {
            alert(`El producto "${prod.nombre}" está agotado sin stock disponible.`);
            return;
        }

        const actual = itemsPedidoActual[prodId] || 0;
        const nueva = actual + delta;

        if (nueva < 0) return;
        const cantMax = Math.min(50, prod.stock);
        if (nueva > cantMax) {
            alert(`Límite máximo por pedido para "${prod.nombre}" es ${cantMax} unidades (máx 50 o stock disponible).`);
            return;
        }

        if (nueva === 0) {
            delete itemsPedidoActual[prodId];
        } else {
            itemsPedidoActual[prodId] = nueva;
        }

        const span = document.getElementById(`cant-pedido-${prodId}`);
        if (span) span.innerText = nueva;

        calcularTotalPedido();
    }

    function calcularTotalPedido() {
        let total = 0;
        for (const [pId, cant] of Object.entries(itemsPedidoActual)) {
            const prod = PRODUCTOS.find(p => p.id === parseInt(pId, 10));
            if (prod) {
                total += cant * prod.precio;
            }
        }

        const totalDisplay = document.getElementById('pedidoTotalDisplay');
        if (totalDisplay) {
            totalDisplay.innerText = `$${total.toLocaleString('es-CL')} CLP`;
        }
    }

    async function enviarComandaCocina() {
        const mesaId = document.getElementById('pedidoMesaId')?.value;
        const notas = document.getElementById('pedidoNotas')?.value || '';
        const alertaError = document.getElementById('alertaErrorPedido');
        const btn = document.getElementById('btnEnviarComandaCocina');

        const items = [];
        for (const [pId, cant] of Object.entries(itemsPedidoActual)) {
            if (cant > 0) {
                items.push({ id: parseInt(pId, 10), cantidad: cant });
            }
        }

        if (items.length === 0) {
            if (alertaError) {
                alertaError.innerText = 'Debe seleccionar al menos un producto para la comanda.';
                alertaError.classList.remove('d-none');
            }
            return;
        }

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Enviando a Cocina...`;
        }

        try {
            const response = await fetch('/mesero/tomar-pedido/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    mesa_id: parseInt(mesaId, 10),
                    items: items,
                    notas: notas
                })
            });

            const data = await response.json();
            if (data.success) {
                // Cerrar modal
                const modalEl = document.getElementById('modalTomarPedido');
                if (modalEl && window.bootstrap) {
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                }

                mostrarAlertaMesero('success', `✓ ${data.message}`);

                // Cambiar automáticamente a Tab de Mesas Ocupadas y recargar estado
                activarTab('ocupadas');
                setTimeout(function() {
                    window.location.reload();
                }, 900);
            } else {
                if (alertaError) {
                    alertaError.innerText = data.error || 'No se pudo generar la comanda.';
                    alertaError.classList.remove('d-none');
                }
            }
        } catch (err) {
            if (alertaError) {
                alertaError.innerText = 'Error de conexión con el servidor.';
                alertaError.classList.remove('d-none');
            }
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<i class="bi bi-send-fill me-1"></i> Enviar Comanda a Cocina (En Espera)`;
            }
        }
    }

    async function cambiarMesa(mesaId, accion) {
        try {
            const response = await fetch('/mesero/cambiar-mesa/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ mesa_id: mesaId, accion: accion })
            });

            const data = await response.json();
            if (data.success) {
                mostrarAlertaMesero('info', `Mesa actualizada a estado ${data.estado || ''}.`);
                setTimeout(function() {
                    window.location.reload();
                }, 600);
            }
        } catch (err) {
            console.error('Error al cambiar estado de mesa:', err);
        }
    }

    function filtrarProductosPedido() {
        const input = document.getElementById('filtroProductoPedido');
        if (!input) return;
        const q = normalizarTexto(input.value);
        document.querySelectorAll('.item-catalogo-pedido').forEach(el => {
            const nombre = normalizarTexto(el.getAttribute('data-nombre') || '');
            const categoria = normalizarTexto(el.getAttribute('data-categoria') || '');
            const coincide = (q === '') || nombre.includes(q) || categoria.includes(q);
            el.classList.toggle('d-none', !coincide);
        });
    }

    async function solicitarCuentaMesa(mesaId, mesaNombre) {
        if (!confirm(`¿Confirmar finalización de atención y solicitar cuenta a caja para ${mesaNombre}?\n\nLa mesa quedará en estado LISTO_PARA_COBRO para liquidar en caja.`)) {
            return;
        }

        const btn = document.getElementById(`btnSolicitarCuenta-${mesaId}`);
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Solicitando...`;
        }

        try {
            const response = await fetch('/mesero/solicitar-cuenta/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ mesa_id: mesaId })
            });

            const data = await response.json();
            if (data.success) {
                mostrarAlertaMesero('success', `✓ ${data.message}`);
                setTimeout(function() {
                    window.location.reload();
                }, 800);
            } else {
                mostrarAlertaMesero('danger', data.error || 'No se pudo solicitar la cuenta.');
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = `<i class="bi bi-receipt-cutoff me-1"></i> Finalizar Venta / Solicitar Cuenta`;
                }
            }
        } catch (err) {
            mostrarAlertaMesero('danger', 'Error de conexión al solicitar la cuenta de la mesa.');
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<i class="bi bi-receipt-cutoff me-1"></i> Finalizar Venta / Solicitar Cuenta`;
            }
        }
    }

    // =========================================================================
    // INICIALIZACIÓN Y EVENT LISTENERS
    // =========================================================================

    document.addEventListener('DOMContentLoaded', function() {
        cargarProductosData();

        // 1. Activar la pestaña adecuada (sessionStorage o servidor)
        const tabInicial = obtenerTabActiva();
        activarTab(tabInicial);

        // 2. Iniciar polling periódico
        iniciarPolling();

        // 3. Delegación de eventos para la barra de pestañas (Tabs)
        document.body.addEventListener('click', function(e) {
            const tabBtn = e.target.closest('.chrome-tab');
            if (tabBtn && tabBtn.dataset.tabTarget) {
                e.preventDefault();
                activarTab(tabBtn.dataset.tabTarget);
                return;
            }

            // Botón: Marcar como Servido / Entregado
            const btnServido = e.target.closest('[data-action="marcar-comanda-servida"]');
            if (btnServido) {
                e.preventDefault();
                const comandaId = btnServido.getAttribute('data-comanda-id');
                const mesaId = btnServido.getAttribute('data-mesa-id');
                const mesaNombre = btnServido.getAttribute('data-mesa-nombre') || 'Mesa';
                marcarComandaServida(comandaId, mesaId, mesaNombre, btnServido);
                return;
            }

            // Botón: Solicitar cuenta de mesa
            const btnSolicitarCuenta = e.target.closest('[data-action="solicitar-cuenta-mesa"]');
            if (btnSolicitarCuenta) {
                e.preventDefault();
                const mesaId = parseInt(btnSolicitarCuenta.getAttribute('data-mesa-id'), 10);
                const mesaNombre = btnSolicitarCuenta.getAttribute('data-mesa-nombre') || 'Mesa';
                if (!isNaN(mesaId)) {
                    solicitarCuentaMesa(mesaId, mesaNombre);
                }
                return;
            }

            // Botón: Alternar estado de mesa (ocupar/desocupar)
            const btnCambiar = e.target.closest('[data-action="cambiar-mesa"]');
            if (btnCambiar) {
                e.preventDefault();
                const mesaId = parseInt(btnCambiar.getAttribute('data-mesa-id'), 10);
                const tipoAccion = btnCambiar.getAttribute('data-tipo-accion');
                if (!isNaN(mesaId) && tipoAccion) {
                    cambiarMesa(mesaId, tipoAccion);
                }
                return;
            }

            // Botón: Abrir modal de pedido
            const btnAbrirPedido = e.target.closest('[data-action="abrir-modal-pedido"]');
            if (btnAbrirPedido) {
                e.preventDefault();
                const mesaId = parseInt(btnAbrirPedido.getAttribute('data-mesa-id'), 10);
                const mesaNombre = btnAbrirPedido.getAttribute('data-mesa-nombre') || 'Mesa';
                if (!isNaN(mesaId)) {
                    abrirModalPedido(mesaId, mesaNombre);
                }
                return;
            }

            // Botones de cantidad dentro del modal de pedido (+ / -)
            const btnSumar = e.target.closest('[data-action="sumar-producto-pedido"]');
            if (btnSumar) {
                e.preventDefault();
                const pId = parseInt(btnSumar.getAttribute('data-id'), 10);
                if (!isNaN(pId)) modificarCantidadPedido(pId, 1);
                return;
            }

            const btnRestar = e.target.closest('[data-action="restar-producto-pedido"]');
            if (btnRestar) {
                e.preventDefault();
                const pId = parseInt(btnRestar.getAttribute('data-id'), 10);
                if (!isNaN(pId)) modificarCantidadPedido(pId, -1);
                return;
            }

            // Botón: Enviar comanda a cocina
            const btnEnviar = e.target.closest('[data-action="enviar-comanda-cocina"]');
            if (btnEnviar) {
                e.preventDefault();
                enviarComandaCocina();
                return;
            }

            // Abrir modal de re-orden para garzón
            const btnAbrirReorden = e.target.closest('[data-action="abrir-modal-reorden-mesero"]');
            if (btnAbrirReorden) {
                e.preventDefault();
                const mesaId = btnAbrirReorden.getAttribute('data-mesa-id');
                const mesaNombre = btnAbrirReorden.getAttribute('data-mesa-nombre') || 'Mesa';
                const comandaId = btnAbrirReorden.getAttribute('data-comanda-id');

                const inputMesaId = document.getElementById('reordenMeseroMesaId');
                const inputCmdId = document.getElementById('reordenMeseroComandaId');
                const tituloMesa = document.getElementById('reordenMeseroTitulo');
                const selectMotivo = document.getElementById('reordenMeseroMotivoSelect');
                const textoMotivo = document.getElementById('reordenMeseroMotivoTexto');
                const alertaError = document.getElementById('alertaErrorReordenMesero');

                if (inputMesaId) inputMesaId.value = mesaId;
                if (inputCmdId) inputCmdId.value = comandaId || '';
                if (tituloMesa) tituloMesa.textContent = mesaNombre;
                if (selectMotivo) selectMotivo.value = '';
                if (textoMotivo) textoMotivo.value = '';
                if (alertaError) alertaError.classList.add('d-none');

                const modalEl = document.getElementById('modalReordenMesero');
                if (modalEl && window.bootstrap) {
                    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
                    modal.show();
                }
                return;
            }

            // Confirmar re-orden desde terminal de mesero
            const btnConfirmarReorden = e.target.closest('[data-action="confirmar-reorden-mesero"]');
            if (btnConfirmarReorden) {
                e.preventDefault();
                const inputCmdId = document.getElementById('reordenMeseroComandaId');
                const inputMesaId = document.getElementById('reordenMeseroMesaId');
                const textoMotivo = document.getElementById('reordenMeseroMotivoTexto');
                const selectMotivo = document.getElementById('reordenMeseroMotivoSelect');
                const alertaError = document.getElementById('alertaErrorReordenMesero');

                let comandaId = inputCmdId ? inputCmdId.value : null;
                const mesaId = inputMesaId ? inputMesaId.value : null;
                const motivo = (textoMotivo && textoMotivo.value.trim()) || (selectMotivo && selectMotivo.value) || 'Cliente solicita recalentar / cambio';

                btnConfirmarReorden.disabled = true;
                btnConfirmarReorden.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Enviando...`;

                const ejecutarEnvio = (cId) => {
                    fetch('/cocina/reorden/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        },
                        body: JSON.stringify({ comanda_id: cId, motivo: motivo })
                    })
                    .then(res => res.json())
                    .then(data => {
                        if (data.success) {
                            window.location.reload();
                        } else {
                            if (alertaError) {
                                alertaError.textContent = data.error || 'No se pudo registrar la re-orden.';
                                alertaError.classList.remove('d-none');
                            }
                            btnConfirmarReorden.disabled = false;
                            btnConfirmarReorden.innerHTML = `<i class="bi bi-arrow-repeat me-1"></i> Confirmar y Notificar a Cocina`;
                        }
                    })
                    .catch(() => {
                        if (alertaError) {
                            alertaError.textContent = 'Error de conexión.';
                            alertaError.classList.remove('d-none');
                        }
                        btnConfirmarReorden.disabled = false;
                        btnConfirmarReorden.innerHTML = `<i class="bi bi-arrow-repeat me-1"></i> Confirmar y Notificar a Cocina`;
                    });
                };

                if (!comandaId && mesaId) {
                    fetch(`/cajero/mesa-cuenta/${mesaId}/`)
                    .then(res => res.json())
                    .then(data => {
                        if (data.success && data.comanda_id) {
                            ejecutarEnvio(data.comanda_id);
                        } else {
                            if (alertaError) {
                                alertaError.textContent = 'No se encontró comanda activa para esta mesa.';
                                alertaError.classList.remove('d-none');
                            }
                            btnConfirmarReorden.disabled = false;
                            btnConfirmarReorden.innerHTML = `<i class="bi bi-arrow-repeat me-1"></i> Confirmar y Notificar a Cocina`;
                        }
                    })
                    .catch(() => {
                        btnConfirmarReorden.disabled = false;
                        btnConfirmarReorden.innerHTML = `<i class="bi bi-arrow-repeat me-1"></i> Confirmar y Notificar a Cocina`;
                    });
                } else if (comandaId) {
                    ejecutarEnvio(comandaId);
                } else {
                    btnConfirmarReorden.disabled = false;
                    btnConfirmarReorden.innerHTML = `<i class="bi bi-arrow-repeat me-1"></i> Confirmar y Notificar a Cocina`;
                }
                return;
            }
        });

        // Sincronizar select de motivos con textarea en modal de mesero
        const selectMotivoMesero = document.getElementById('reordenMeseroMotivoSelect');
        const textoMotivoMesero = document.getElementById('reordenMeseroMotivoTexto');
        if (selectMotivoMesero && textoMotivoMesero) {
            selectMotivoMesero.addEventListener('change', function() {
                if (this.value) {
                    textoMotivoMesero.value = this.value;
                }
            });
        }

        // Filtrado en vivo de productos en el modal (tiempo real)
        const inputFiltro = document.getElementById('filtroProductoPedido');
        if (inputFiltro) {
            inputFiltro.addEventListener('input', filtrarProductosPedido);
            inputFiltro.addEventListener('keyup', filtrarProductosPedido);
        }
    });
})();
