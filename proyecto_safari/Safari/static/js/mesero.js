/**
 * Safari POS - Módulo de Mesero (mesero.html)
 * Control de ocupación de mesas, toma de pedidos con notas de comanda y estado EN ESPERA.
 */
(function() {
    'use strict';

    let PRODUCTOS = [];
    let itemsPedidoActual = {}; // { prodId: cantidad }

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
        if (nueva > prod.stock) {
            alert(`Stock máximo disponible para ${prod.nombre} es ${prod.stock}.`);
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
                alert(`✓ ${data.message}`);

                // Cerrar modal
                const modalEl = document.getElementById('modalTomarPedido');
                if (modalEl && window.bootstrap) {
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                }

                // Actualizar interfaz de la mesa a OCUPADA
                const badge = document.getElementById(`badgeEstado-${mesaId}`);
                const btnOcupar = document.getElementById(`btnOcupar-${mesaId}`);
                const infoPedido = document.getElementById(`infoPedido-${mesaId}`);
                const folioSpan = document.getElementById(`folioPedido-${mesaId}`);
                const totalSpan = document.getElementById(`totalPedido-${mesaId}`);

                if (badge) {
                    badge.className = 'badge bg-danger';
                    badge.innerText = 'OCUPADA';
                }
                if (btnOcupar) {
                    btnOcupar.className = 'btn btn-sm btn-outline-success';
                    btnOcupar.innerText = 'Desocupar Mesa';
                }
                if (infoPedido) infoPedido.classList.remove('d-none');
                if (folioSpan) folioSpan.innerText = data.folio;
                if (totalSpan) totalSpan.innerText = `$${Number(data.total).toLocaleString('es-CL')} CLP`;

                // Habilitar botón de solicitar cuenta
                const btnSolicitar = document.getElementById(`btnSolicitarCuenta-${mesaId}`);
                if (btnSolicitar) {
                    btnSolicitar.classList.remove('d-none');
                    btnSolicitar.disabled = false;
                    btnSolicitar.innerHTML = `<i class="bi bi-receipt-cutoff me-1"></i> Finalizar Venta / Solicitar Cuenta`;
                }

                const alertaListo = document.getElementById(`alertaListoCobro-${mesaId}`);
                if (alertaListo) alertaListo.classList.add('d-none');

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
                // Actualizar Badge de Estado y Botón de Ocupar/Desocupar
                const badge = document.getElementById(`badgeEstado-${mesaId}`);
                const btn = document.getElementById(`btnOcupar-${mesaId}`);
                const infoPedido = document.getElementById(`infoPedido-${mesaId}`);

                if (badge) badge.innerText = (data.estado || '').toUpperCase();
                if (btn) {
                    if (data.estado === 'ocupada') {
                        if (badge) badge.className = 'badge bg-danger';
                        btn.className = 'btn btn-sm btn-outline-success';
                        btn.innerText = 'Desocupar Mesa';
                        if (infoPedido) infoPedido.classList.remove('d-none');
                    } else {
                        if (badge) badge.className = 'badge bg-success';
                        btn.className = 'btn btn-sm btn-outline-danger';
                        btn.innerText = 'Ocupar Mesa';
                        if (infoPedido) infoPedido.classList.add('d-none');
                    }
                }

                // Actualizar Badge de Comida Entregada y Botón Re-orden
                const badgeComida = document.getElementById(`badgeComida-${mesaId}`);
                const btnReorden = document.getElementById(`btnReordenMesa-${mesaId}`);
                if (badgeComida) {
                    if (data.comida_entregada) {
                        badgeComida.className = 'badge bg-info text-dark py-1 px-2';
                        badgeComida.innerHTML = `<i class="bi bi-check2-circle me-1"></i> Comida Entregada`;
                        if (btnReorden) btnReorden.classList.remove('d-none');
                    } else {
                        badgeComida.className = 'badge bg-secondary py-1 px-2';
                        badgeComida.innerHTML = `<i class="bi bi-clock me-1"></i> Esperando Comida`;
                        if (btnReorden) btnReorden.classList.add('d-none');
                    }
                }
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
        if (!confirm(`¿Confirmar finalización de atención y solicitar cuenta a caja para ${mesaNombre}?\n\nLa mesa quedará bloqueada en estado LISTO_PARA_COBRO para liquidar en caja.`)) {
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
                alert(`✓ ${data.message}`);

                // Actualizar interfaz de la mesa a LISTO_PARA_COBRO
                const card = document.getElementById(`cardMesa-${mesaId}`);
                const badge = document.getElementById(`badgeEstado-${mesaId}`);
                const btnTomar = document.getElementById(`btnTomarPedido-${mesaId}`);
                const alerta = document.getElementById(`alertaListoCobro-${mesaId}`);

                if (card) {
                    card.classList.remove('border-danger', 'border-success');
                    card.classList.add('border-warning');
                }
                if (badge) {
                    badge.className = 'badge bg-warning text-dark';
                    badge.innerText = 'LISTO PARA COBRO';
                }
                if (alerta) {
                    alerta.classList.remove('d-none');
                }
                if (btnTomar) {
                    btnTomar.disabled = true;
                    btnTomar.title = 'Mesa esperando liquidación en caja';
                }
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = `<i class="bi bi-check-circle me-1"></i> Cuenta Solicitada (En Caja)`;
                }
            } else {
                alert(data.error || 'No se pudo solicitar la cuenta.');
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = `<i class="bi bi-receipt-cutoff me-1"></i> Finalizar Venta / Solicitar Cuenta`;
                }
            }
        } catch (err) {
            alert('Error de conexión al solicitar la cuenta de la mesa.');
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<i class="bi bi-receipt-cutoff me-1"></i> Finalizar Venta / Solicitar Cuenta`;
            }
        }
    }

    document.addEventListener('DOMContentLoaded', function() {
        cargarProductosData();

        // Escuchar clics globales del módulo de mesero
        document.body.addEventListener('click', function(e) {
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
                    // Si no estaba en data attribute, buscar vía endpoint de cuenta
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
