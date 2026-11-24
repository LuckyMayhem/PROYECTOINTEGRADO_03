/**
 * Safari POS - Deslogueo Automático por Inactividad (30 minutos AFK)
 * Se activa únicamente si el usuario se encuentra autenticado (data-authenticated="true" en <body>).
 */
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        const body = document.body;
        if (!body || body.getAttribute('data-authenticated') !== 'true') {
            return;
        }

        const TIEMPO_INACTIVIDAD_MS = 30 * 60 * 1000; // 30 minutos = 1.800.000 ms
        let temporizadorInactividad = null;

        function cerrarSesionPorInactividad() {
            console.warn("Sesión cerrada automáticamente por inactividad (30 minutos AFK sin interacción).");
            window.location.href = '/logout/?motivo=inactividad';
        }

        function reiniciarTemporizador() {
            if (temporizadorInactividad) {
                clearTimeout(temporizadorInactividad);
            }
            temporizadorInactividad = setTimeout(cerrarSesionPorInactividad, TIEMPO_INACTIVIDAD_MS);
        }

        // Escuchar eventos pasivos de interacción (teclado, ratón, tacto, scroll)
        const eventos = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'];
        eventos.forEach(function(evt) {
            window.addEventListener(evt, reiniciarTemporizador, { passive: true });
        });

        // Inicializar el temporizador al cargar el DOM
        reiniciarTemporizador();
    });
})();
