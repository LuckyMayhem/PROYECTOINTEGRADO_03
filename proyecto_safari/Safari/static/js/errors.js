/**
 * Safari POS - Controladores de Vistas de Error
 * Maneja recargas y fallbacks de imágenes sin atributos onclick ni onerror inline.
 */
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        // Manejar botones de recarga/reintento
        document.querySelectorAll('[data-action="reload-page"]').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                window.location.reload();
            });
        });

        // Manejar fallback de imágenes de error de forma segura
        document.querySelectorAll('img.error-img').forEach(function(img) {
            img.addEventListener('error', function() {
                const fallback = this.getAttribute('data-fallback');
                if (fallback && this.src !== fallback) {
                    this.src = fallback;
                }
            }, { once: true });
        });
    });
})();
