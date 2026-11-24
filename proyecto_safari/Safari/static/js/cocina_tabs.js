/**
 * cocina_tabs.js
 * Lógica modular para el Monitor de Cocina de Safari POS.
 * Implementa navegación por pestañas (Tabs) estilo navegador Chrome dividida en 5 secciones:
 * 1. En Espera
 * 2. Preparación
 * 3. Listo
 * 4. Entregado
 * 5. Re-Cocinando (prioridad para órdenes re-emitidas / cambios / recalentados)
 * 
 * Cumplimiento estricto de Content Security Policy (CSP):
 * - Cero listeners o código inline en plantillas HTML.
 * - Delegación de eventos y persistencia de pestaña activa en localStorage.
 */

(function () {
    'use strict';

    const STORAGE_KEY_TAB = 'tab_cocina_activa';
    const TABS_VALIDAS = ['en_espera', 'preparacion', 'listo', 'entregado', 'recocinando'];

    /**
     * Obtiene el token CSRF para peticiones seguras POST.
     */
    function getCsrfToken() {
        const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
        if (csrfInput && csrfInput.value) return csrfInput.value;

        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.startsWith('csrftoken=')) {
                    return decodeURIComponent(cookie.substring('csrftoken='.length));
                }
            }
        }
        return '';
    }

    /**
     * Muestra alertas visuales temporales para el cocinero.
     */
    function mostrarAlertaCocina(tipo, mensaje) {
        const contenedor = document.getElementById('alertContainerCocina');
        if (!contenedor) return;

        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${tipo} alert-dismissible fade show shadow-sm`;
        alertDiv.setAttribute('role', 'alert');

        const icono = tipo === 'success' ? 'bi-check-circle-fill' : 'bi-exclamation-triangle-fill';
        alertDiv.innerHTML = `
            <i class="bi ${icono} me-2"></i> ${mensaje}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Cerrar"></button>
        `;

        contenedor.appendChild(alertDiv);
        setTimeout(function () {
            alertDiv.remove();
        }, 4000);
    }

    /**
     * Obtiene el identificador de la pestaña actualmente activa.
     * Prioriza sessionStorage para restaurar exactamente la misma pestaña sin saltos visuales.
     */
    function obtenerTabActiva() {
        // 1. Prioridad: sessionStorage guardada por la interacción del usuario
        try {
            const stored = sessionStorage.getItem('tab_cocina_activa');
            if (stored && TABS_VALIDAS.includes(stored)) {
                return stored;
            }
        } catch (e) {
            console.warn('sessionStorage no disponible:', e);
        }

        // 2. Hash en la URL (#preparacion, #en_espera, etc.)
        const hash = window.location.hash.replace('#', '').trim();
        if (TABS_VALIDAS.includes(hash)) return hash;

        // 3. Pestaña activa renderizada por el servidor en el DOM
        const navStrip = document.querySelector('.chrome-tabstrip') || document.querySelector('main');
        if (navStrip && navStrip.dataset.tabActiva && TABS_VALIDAS.includes(navStrip.dataset.tabActiva)) {
            return navStrip.dataset.tabActiva;
        }

        // 4. Pestaña con clase active en el DOM
        const tabActivaEl = document.querySelector('.chrome-tab.active');
        if (tabActivaEl && tabActivaEl.dataset.tabTarget && TABS_VALIDAS.includes(tabActivaEl.dataset.tabTarget)) {
            return tabActivaEl.dataset.tabTarget;
        }

        return 'en_espera';
    }

    /**
     * Activa una pestaña específica, ocultando las demás sin recargar la página.
     * Guarda la pestaña activa en sessionStorage.
     */
    function activarTab(targetTab) {
        if (!TABS_VALIDAS.includes(targetTab)) {
            targetTab = 'en_espera';
        }

        const tabId = targetTab;
        // 1. Guardar de forma persistente en sessionStorage
        try {
            sessionStorage.setItem('tab_cocina_activa', tabId);
        } catch (e) {
            console.warn('Error al guardar en sessionStorage:', e);
        }

        // 2. Actualizar estado visual de las pestañas Chrome
        const tabs = document.querySelectorAll('.chrome-tab');
        tabs.forEach(function (tab) {
            if (tab.dataset.tabTarget === targetTab) {
                tab.classList.add('active');
                tab.setAttribute('aria-selected', 'true');
            } else {
                tab.classList.remove('active');
                tab.setAttribute('aria-selected', 'false');
            }
        });

        // 3. Mostrar únicamente el contenedor del estado seleccionado
        const panes = document.querySelectorAll('.tab-pane-cocina');
        panes.forEach(function (pane) {
            if (pane.dataset.estadoPane === targetTab) {
                pane.classList.remove('d-none');
            } else {
                pane.classList.add('d-none');
            }
        });

        // 4. Actualizar hash en la URL sin saltos de scroll
        if (window.history && window.history.replaceState) {
            window.history.replaceState(null, null, '#' + targetTab);
        }
    }

    /**
     * Recalcula en tiempo real los contadores numéricos de cada pestaña.
     */
    function actualizarContadores() {
        TABS_VALIDAS.forEach(function (estado) {
            const pane = document.querySelector(`.tab-pane-cocina[data-estado-pane="${estado}"]`);
            const badge = document.getElementById(`tab-counter-${estado}`);
            const emptyState = document.getElementById(`empty-state-${estado}`);

            if (pane && badge) {
                const totalTarjetas = pane.querySelectorAll('.card-comanda-col').length;
                badge.textContent = totalTarjetas;

                if (emptyState) {
                    if (totalTarjetas === 0) {
                        emptyState.classList.remove('d-none');
                    } else {
                        emptyState.classList.add('d-none');
                    }
                }
            }
        });
    }

    /**
     * Envía la transición de estado de una comanda al backend vía POST,
     * garantizando que el cocinero permanezca en la pestaña activa actual.
     */
    async function cambiarEstadoComanda(comandaId, nuevoEstado, botonTrigger) {
        const tabActivaActual = obtenerTabActiva();
        try {
            sessionStorage.setItem('tab_cocina_activa', tabActivaActual);
        } catch (e) {}

        if (botonTrigger) {
            botonTrigger.disabled = true;
            botonTrigger.dataset.originalHtml = botonTrigger.innerHTML;
            botonTrigger.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Procesando...`;
        }

        try {
            const response = await fetch('/cocina/cambiar-estado/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    comanda_id: comandaId,
                    nuevo_estado: nuevoEstado,
                    tab_activa: tabActivaActual
                })
            });

            // Garantizar persistencia inmediata en sessionStorage
            try {
                sessionStorage.setItem('tab_cocina_activa', tabActivaActual);
            } catch (e) {}

            const data = await response.json();

            if (data.success) {
                // Remover la tarjeta con efecto visual fluido
                const colTarjeta = document.getElementById(`col-comanda-${comandaId}`);
                if (colTarjeta) {
                    colTarjeta.classList.add('comanda-fade-out');
                    setTimeout(function () {
                        colTarjeta.remove();
                        actualizarContadores();
                        mostrarAlertaCocina('success', `Comanda #${comandaId} actualizada.`);
                    }, 300);
                } else {
                    // Si se recarga la página, restaurará exactamente la misma pestaña
                    window.location.reload();
                }
            } else {
                mostrarAlertaCocina('danger', data.error || 'No se pudo actualizar el estado de la comanda.');
                if (botonTrigger && botonTrigger.dataset.originalHtml) {
                    botonTrigger.disabled = false;
                    botonTrigger.innerHTML = botonTrigger.dataset.originalHtml;
                }
            }
        } catch (error) {
            console.error('Error al actualizar comanda:', error);
            mostrarAlertaCocina('danger', 'Error de comunicación con el servidor.');
            if (botonTrigger && botonTrigger.dataset.originalHtml) {
                botonTrigger.disabled = false;
                botonTrigger.innerHTML = botonTrigger.dataset.originalHtml;
            }
        }
    }

    /**
     * Ejecuta la re-emisión de un platillo a estado RE_ORDEN.
     * Mantiene al cocinero en la pestaña activa donde se encontraba.
     */
    async function confirmarReordenComanda(comandaId, motivo) {
        const tabActivaActual = obtenerTabActiva();
        try {
            sessionStorage.setItem('tab_cocina_activa', tabActivaActual);
        } catch (e) {}

        const btnConfirmar = document.getElementById('btnConfirmarReorden');
        const alertaError = document.getElementById('alertaErrorReorden');

        if (btnConfirmar) {
            btnConfirmar.disabled = true;
            btnConfirmar.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Re-emitiendo...`;
        }
        if (alertaError) alertaError.classList.add('d-none');

        try {
            const response = await fetch('/cocina/reorden/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    comanda_id: comandaId,
                    motivo: motivo || 'Solicitud de re-orden / recalentado o cambio'
                })
            });

            const data = await response.json();

            if (data.success) {
                // Cerrar modal
                const modalEl = document.getElementById('modalReordenComanda');
                if (modalEl && window.bootstrap) {
                    const modalInst = bootstrap.Modal.getInstance(modalEl);
                    if (modalInst) modalInst.hide();
                }

                // Guardar la pestaña activa para que tras el reload se mantenga en la pestaña activa
                try {
                    sessionStorage.setItem('tab_cocina_activa', tabActivaActual);
                } catch (e) {}

                // Recargar para sincronizar las nuevas secciones de re-orden
                window.location.reload();
            } else {
                if (alertaError) {
                    alertaError.textContent = data.error || 'No se pudo procesar la re-orden.';
                    alertaError.classList.remove('d-none');
                }
                if (btnConfirmar) {
                    btnConfirmar.disabled = false;
                    btnConfirmar.innerHTML = `<i class="bi bi-arrow-repeat me-1"></i> Confirmar y Enviar a Cocina`;
                }
            }
        } catch (error) {
            console.error('Error al re-emitir comanda:', error);
            if (alertaError) {
                alertaError.textContent = 'Error de conexión con el servidor al re-emitir la comanda.';
                alertaError.classList.remove('d-none');
            }
            if (btnConfirmar) {
                btnConfirmar.disabled = false;
                btnConfirmar.innerHTML = `<i class="bi bi-arrow-repeat me-1"></i> Confirmar y Enviar a Cocina`;
            }
        }
    }

    /**
     * Inicialización del DOM y delegación de eventos.
     */
    document.addEventListener('DOMContentLoaded', function () {
        // 1. Restaurar o activar la pestaña guardada desde sessionStorage
        const tabInicial = obtenerTabActiva();
        activarTab(tabInicial);
        actualizarContadores();

        // 2. Listener global para clics en pestañas Chrome
        document.body.addEventListener('click', function (e) {
            const tabBtn = e.target.closest('.chrome-tab');
            if (tabBtn) {
                e.preventDefault();
                const targetTab = tabBtn.dataset.tabTarget;
                if (targetTab) {
                    const tabId = targetTab;
                    try {
                        sessionStorage.setItem('tab_cocina_activa', tabId);
                    } catch (err) {
                        console.warn('Error al guardar en sessionStorage:', err);
                    }
                    activarTab(targetTab);
                }
                return;
            }

            // 3. Botones de transición de estado en las tarjetas
            // 'Iniciar Preparación' (data-nuevo-estado="preparacion")
            // 'Marcar Listo' (data-nuevo-estado="listo")
            // 'Entregar' (data-nuevo-estado="entregado")
            const btnEstado = e.target.closest('[data-action="cambiar-estado-comanda"]');
            if (btnEstado) {
                e.preventDefault();
                const comandaId = parseInt(btnEstado.getAttribute('data-comanda-id'), 10);
                const nuevoEstado = btnEstado.getAttribute('data-nuevo-estado');
                if (!isNaN(comandaId) && nuevoEstado) {
                    cambiarEstadoComanda(comandaId, nuevoEstado, btnEstado);
                }
                return;
            }

            // 4. Botón 'Re-hacer / Re-orden' dentro de la pestaña Entregado
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

            // 5. Botón Confirmar Re-orden en el modal
            const btnConfirmar = e.target.closest('[data-action="confirmar-reorden"]');
            if (btnConfirmar) {
                e.preventDefault();
                const inputId = document.getElementById('reordenComandaId');
                const textoMotivo = document.getElementById('reordenMotivoTexto');
                const selectMotivo = document.getElementById('reordenMotivoSelect');

                const comandaId = inputId ? parseInt(inputId.value, 10) : null;
                const motivo = (textoMotivo && textoMotivo.value.trim()) || (selectMotivo && selectMotivo.value) || 'Cambio o recalentado';

                if (comandaId) {
                    confirmarReordenComanda(comandaId, motivo);
                }
                return;
            }
        });

        // 6. Sincronizar select de motivos frecuentes con textarea en modal
        const selectMotivo = document.getElementById('reordenMotivoSelect');
        const textoMotivo = document.getElementById('reordenMotivoTexto');
        if (selectMotivo && textoMotivo) {
            selectMotivo.addEventListener('change', function () {
                if (this.value) {
                    textoMotivo.value = this.value;
                }
            });
        }

        // 7. Auto-refresco periódico (15s) preservando la pestaña activa en sessionStorage
        setInterval(function () {
            const modalEl = document.getElementById('modalReordenComanda');
            if (modalEl && modalEl.classList.contains('show')) return;
            const tabActual = obtenerTabActiva();
            try {
                sessionStorage.setItem('tab_cocina_activa', tabActual);
            } catch (e) {}
            window.location.reload();
        }, 15000);
    });

    // Exponer API en ventana global
    window.CocinaTabsSafari = {
        activarTab: activarTab,
        obtenerTabActiva: obtenerTabActiva,
        actualizarContadores: actualizarContadores
    };
})();
