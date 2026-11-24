/**
 * Safari POS - Módulo de Cocina (cocinero.html)
 * Control de comandas regulares, re-órdenes prioritarias para cambios/recalentados
 * y refresco automático seguro.
 */
(function() {
    'use strict';

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
        const cont = document.getElementById('alertContainerCocina');
        if (!cont) return;
        cont.innerHTML = `
            <div class="alert alert-${tipo} alert-dismissible fade show shadow-sm" role="alert">
                <i class="bi bi-info-circle-fill me-2"></i> ${mensaje}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        setTimeout(() => { cont.innerHTML = ''; }, 4500);
    }

    async function cambiarEstadoComanda(comandaId, nuevoEstado) {
        try {
            const response = await fetch('/cocina/cambiar-estado/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ comanda_id: comandaId, nuevo_estado: nuevoEstado })
            });

            const data = await response.json();
            if (data.success) {
                if (nuevoEstado === 'entregado') {
                    const col = document.getElementById(`col-comanda-${comandaId}`);
                    if (col) {
                        col.classList.add('comanda-fade-out');
                        setTimeout(() => {
                            col.remove();
                            const restantes = document.querySelectorAll('#contenedorComandas .col, #contenedorReordenes .col');
                            if (restantes.length === 0) {
                                window.location.reload();
                            }
                        }, 400);
                    }
                } else {
                    window.location.reload();
                }
            } else {
                mostrarAlerta('danger', data.error || 'No se pudo actualizar el estado de la comanda.');
            }
        } catch (err) {
            console.error('Error al cambiar estado de comanda:', err);
            mostrarAlerta('danger', 'Error de conexión con el servidor.');
        }
    }

    async function ejecutarReorden(comandaId, motivo) {
        const btn = document.getElementById('btnConfirmarReorden');
        const alertaError = document.getElementById('alertaErrorReorden');

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Re-emitiendo...`;
        }
        if (alertaError) alertaError.classList.add('d-none');

        try {
            const response = await fetch('/cocina/reorden/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    comanda_id: comandaId,
                    motivo: motivo || 'Solicitud de re-orden / cambio de platillo'
                })
            });

            const data = await response.json();
            if (data.success) {
                // Cerrar modal
                const modalEl = document.getElementById('modalReordenComanda');
                if (modalEl && window.bootstrap) {
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                }
                // Recargar para mostrar en la sección prioritaria de re-órdenes
                window.location.reload();
            } else {
                if (alertaError) {
                    alertaError.textContent = data.error || 'No se pudo procesar la re-orden.';
                    alertaError.classList.remove('d-none');
                }
            }
        } catch (err) {
            if (alertaError) {
                alertaError.textContent = 'Error de conexión al re-emitir la comanda.';
                alertaError.classList.remove('d-none');
            }
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<i class="bi bi-arrow-repeat me-1"></i> Confirmar y Enviar a Cocina`;
            }
        }
    }

    document.addEventListener('DOMContentLoaded', function() {
        // Delegación de clic para cambio de estado en cualquier contenedor de comandas
        document.body.addEventListener('click', function(e) {
            const btnEstado = e.target.closest('[data-action="cambiar-estado-comanda"]');
            if (btnEstado) {
                e.preventDefault();
                const comandaId = parseInt(btnEstado.getAttribute('data-comanda-id'), 10);
                const nuevoEstado = btnEstado.getAttribute('data-nuevo-estado');
                if (!isNaN(comandaId) && nuevoEstado) {
                    cambiarEstadoComanda(comandaId, nuevoEstado);
                }
                return;
            }

            // Botón abrir modal de re-orden desde historial entregado
            const btnAbrirReorden = e.target.closest('[data-action="abrir-modal-reorden"]');
            if (btnAbrirReorden) {
                e.preventDefault();
                const comandaId = btnAbrirReorden.getAttribute('data-comanda-id');
                const folio = btnAbrirReorden.getAttribute('data-folio');
                const mesa = btnAbrirReorden.getAttribute('data-mesa');

                const inputId = document.getElementById('reordenComandaId');
                const textoFolio = document.getElementById('reordenModalFolio');
                const selectMotivo = document.getElementById('reordenMotivoSelect');
                const textoMotivo = document.getElementById('reordenMotivoTexto');
                const alertaError = document.getElementById('alertaErrorReorden');

                if (inputId) inputId.value = comandaId;
                if (textoFolio) textoFolio.textContent = `${folio} (${mesa})`;
                if (selectMotivo) selectMotivo.value = '';
                if (textoMotivo) textoMotivo.value = '';
                if (alertaError) alertaError.classList.add('d-none');

                const modalEl = document.getElementById('modalReordenComanda');
                if (modalEl && window.bootstrap) {
                    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
                    modal.show();
                }
                return;
            }

            // Confirmar re-orden
            const btnConfirmar = e.target.closest('[data-action="confirmar-reorden"]');
            if (btnConfirmar) {
                e.preventDefault();
                const inputId = document.getElementById('reordenComandaId');
                const textoMotivo = document.getElementById('reordenMotivoTexto');
                const selectMotivo = document.getElementById('reordenMotivoSelect');

                const comandaId = inputId ? parseInt(inputId.value, 10) : null;
                const motivo = (textoMotivo && textoMotivo.value.trim()) || (selectMotivo && selectMotivo.value) || 'Cambio o recalentado';

                if (comandaId) {
                    ejecutarReorden(comandaId, motivo);
                }
                return;
            }
        });

        // Sincronizar select de motivos rápidos con textarea
        const selectMotivo = document.getElementById('reordenMotivoSelect');
        const textoMotivo = document.getElementById('reordenMotivoTexto');
        if (selectMotivo && textoMotivo) {
            selectMotivo.addEventListener('change', function() {
                if (this.value) {
                    textoMotivo.value = this.value;
                }
            });
        }

        // Auto-refresco cada 12 segundos (se suspende si el usuario inspecciona el historial o modal abierto)
        setInterval(function() {
            const historialEl = document.getElementById('historialEntregados');
            if (historialEl && historialEl.classList.contains('show')) return;
            const modalEl = document.getElementById('modalReordenComanda');
            if (modalEl && modalEl.classList.contains('show')) return;
            window.location.reload();
        }, 12000);
    });
})();
