/**
 * Safari POS - Módulo Gestión de Stock e Inventario (stock.html)
 * Control de reposición rápida de existencias y edición de catálogo.
 */
(function() {
    'use strict';

    let prodStockIdSeleccionado = null;

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

    function limpiarFormProducto() {
        if (window.limpiarErroresFormulario) {
            window.limpiarErroresFormulario('form[action*="/stock/guardar/"]');
        }
        const tit = document.getElementById('modalProductoTitulo');
        if (tit) tit.innerText = 'Registrar Nuevo Producto';

        const prodId = document.getElementById('prodId');
        const prodNombre = document.getElementById('prodNombre');
        const prodDesc = document.getElementById('prodDescripcion');
        const prodPrecio = document.getElementById('prodPrecio');
        const prodStock = document.getElementById('prodStock');

        if (prodId) prodId.value = '';
        if (prodNombre) prodNombre.value = '';
        if (prodDesc) prodDesc.value = '';
        if (prodPrecio) prodPrecio.value = '';
        if (prodStock) prodStock.value = '0';
    }

    function editarProducto(btn) {
        if (window.limpiarErroresFormulario) {
            window.limpiarErroresFormulario('form[action*="/stock/guardar/"]');
        }
        const tit = document.getElementById('modalProductoTitulo');
        if (tit) tit.innerText = 'Modificar Producto';

        const prodId = document.getElementById('prodId');
        const prodNombre = document.getElementById('prodNombre');
        const prodDesc = document.getElementById('prodDescripcion');
        const prodPrecio = document.getElementById('prodPrecio');
        const prodStock = document.getElementById('prodStock');

        if (prodId) prodId.value = btn.getAttribute('data-id') || '';
        if (prodNombre) prodNombre.value = btn.getAttribute('data-nombre') || '';
        if (prodDesc) prodDesc.value = btn.getAttribute('data-descripcion') || '';
        if (prodPrecio) prodPrecio.value = btn.getAttribute('data-precio') || '';
        if (prodStock) prodStock.value = btn.getAttribute('data-stock') || '0';

        const modalEl = document.getElementById('modalProducto');
        if (modalEl && window.bootstrap) {
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        }
    }

    function abrirModalStock(btn) {
        prodStockIdSeleccionado = btn.getAttribute('data-id');
        const nombre = btn.getAttribute('data-nombre') || '';
        const stock = btn.getAttribute('data-stock') || '0';

        const nomEl = document.getElementById('stockModalProdNombre');
        const actEl = document.getElementById('stockModalActual');
        const cantInp = document.getElementById('cantidadSumar');

        if (nomEl) nomEl.innerText = nombre;
        if (actEl) actEl.innerText = `Stock actual: ${stock} unidades`;
        if (cantInp) cantInp.value = '10';

        const modalEl = document.getElementById('modalStock');
        if (modalEl && window.bootstrap) {
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        }
    }

    async function confirmarAgregarStock() {
        const cantInp = document.getElementById('cantidadSumar');
        const cant = parseInt(cantInp ? cantInp.value : '0', 10);
        if (!prodStockIdSeleccionado || isNaN(cant) || cant <= 0) return;

        try {
            const response = await fetch('/stock/agregar/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ producto_id: prodStockIdSeleccionado, cantidad_agregar: cant })
            });
            const data = await response.json();
            if (data.success) {
                window.location.reload();
            } else {
                alert(data.error || 'Error al reponer stock.');
            }
        } catch (err) {
            console.error('Error al reponer stock:', err);
        }
    }

    document.addEventListener('DOMContentLoaded', function() {
        // Botón nuevo producto
        document.querySelectorAll('[data-action="nuevo-producto"]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                limpiarFormProducto();
            });
        });

        // Botones editar producto
        document.body.addEventListener('click', function(e) {
            const btn = e.target.closest('[data-action="editar-producto"]');
            if (btn) {
                e.preventDefault();
                editarProducto(btn);
            }
        });

        // Botones abrir modal agregar stock
        document.body.addEventListener('click', function(e) {
            const btn = e.target.closest('[data-action="abrir-modal-stock"]');
            if (btn) {
                e.preventDefault();
                abrirModalStock(btn);
            }
        });

        // Botón confirmar agregar stock
        document.querySelectorAll('[data-action="confirmar-agregar-stock"]').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                confirmarAgregarStock();
            });
        });

        // Confirmaciones de eliminación
        document.body.addEventListener('click', function(e) {
            const link = e.target.closest('[data-action="confirm-delete"]');
            if (link) {
                const msg = link.getAttribute('data-confirm-msg') || '¿Confirma que desea eliminar este producto?';
                if (!confirm(msg)) {
                    e.preventDefault();
                }
            }
        });
    });
})();
