/**
 * Safari POS - Módulos Mantenedores CRUD (mantenedores/*.html)
 * Control unificado de modales, edición y confirmaciones de seguridad.
 */
(function() {
    'use strict';

    function getCurrentAdminId() {
        const modalForm = document.getElementById('formUsuarioCrud');
        if (modalForm && modalForm.getAttribute('data-current-admin-id')) {
            return modalForm.getAttribute('data-current-admin-id');
        }
        return document.body.getAttribute('data-current-admin-id') || '';
    }

    // --- MENUS ---
    function limpiarFormMenu() {
        const idEl = document.getElementById('menuId');
        const nomEl = document.getElementById('menuNombre');
        const descEl = document.getElementById('menuDescripcion');
        const estEl = document.getElementById('menuEstado');
        const titEl = document.getElementById('modalMenuTitulo');
        const btnEl = document.getElementById('btnGuardarMenu');

        if (idEl) idEl.value = '';
        if (nomEl) nomEl.value = '';
        if (descEl) descEl.value = '';
        if (estEl) estEl.value = 'activo';
        if (titEl) titEl.innerHTML = '<i class="bi bi-journal-bookmark-fill text-warning me-2"></i> Crear Nueva Categoría';
        if (btnEl) btnEl.innerHTML = '<i class="bi bi-save me-1"></i> Crear Categoría';
    }

    function editarMenu(btn) {
        const form = document.getElementById('formMenu');
        if (form) {
            form.querySelectorAll('input, select, textarea').forEach(function(el) {
                el.disabled = false;
                el.readOnly = false;
            });
        }

        const idEl = document.getElementById('menuId');
        const nomEl = document.getElementById('menuNombre');
        const descEl = document.getElementById('menuDescripcion');
        const estEl = document.getElementById('menuEstado');
        const titEl = document.getElementById('modalMenuTitulo');
        const btnEl = document.getElementById('btnGuardarMenu');

        if (idEl) idEl.value = btn.getAttribute('data-id') || '';
        if (nomEl) nomEl.value = btn.getAttribute('data-nombre') || '';
        if (descEl) descEl.value = btn.getAttribute('data-descripcion') || '';
        if (estEl) estEl.value = btn.getAttribute('data-estado') || 'activo';
        if (titEl) titEl.innerHTML = '<i class="bi bi-pencil-square text-warning me-2"></i> Editar Categoría';
        if (btnEl) btnEl.innerHTML = '<i class="bi bi-check-circle me-1"></i> Actualizar Categoría';

        const modalEl = document.getElementById('modalMenu');
        if (modalEl && window.bootstrap) {
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        }
    }

    // --- MESAS ---
    function limpiarFormMesa() {
        const idEl = document.getElementById('mesaId');
        const numEl = document.getElementById('mesaNumero');
        const nomEl = document.getElementById('mesaNombre');
        const capEl = document.getElementById('mesaCapacidad');
        const estEl = document.getElementById('mesaEstado');
        const titEl = document.getElementById('modalMesaTitulo');
        const btnEl = document.getElementById('btnGuardarMesa');

        if (idEl) idEl.value = '';
        if (numEl) numEl.value = '';
        if (nomEl) nomEl.value = '';
        if (capEl) capEl.value = '4';
        if (estEl) estEl.value = 'disponible';
        if (titEl) titEl.innerHTML = '<i class="bi bi-square-fill text-warning me-2"></i> Crear Nueva Mesa';
        if (btnEl) btnEl.innerHTML = '<i class="bi bi-save me-1"></i> Crear Mesa';
    }

    function editarMesa(btn) {
        const form = document.getElementById('formMesa');
        if (form) {
            form.querySelectorAll('input, select, textarea').forEach(function(el) {
                el.disabled = false;
                el.readOnly = false;
            });
        }

        const idEl = document.getElementById('mesaId');
        const numEl = document.getElementById('mesaNumero');
        const nomEl = document.getElementById('mesaNombre');
        const capEl = document.getElementById('mesaCapacidad');
        const estEl = document.getElementById('mesaEstado');
        const titEl = document.getElementById('modalMesaTitulo');
        const btnEl = document.getElementById('btnGuardarMesa');

        if (idEl) idEl.value = btn.getAttribute('data-id') || '';
        if (numEl) numEl.value = btn.getAttribute('data-numero') || '';
        if (nomEl) nomEl.value = btn.getAttribute('data-nombre') || '';
        if (capEl) capEl.value = btn.getAttribute('data-capacidad') || '4';

        let est = btn.getAttribute('data-estado') || 'disponible';
        if (est === 'desocupada') est = 'disponible';
        if (estEl) estEl.value = est;

        if (titEl) titEl.innerHTML = '<i class="bi bi-pencil-square text-warning me-2"></i> Editar Mesa';
        if (btnEl) btnEl.innerHTML = '<i class="bi bi-check-circle me-1"></i> Actualizar Mesa';

        const modalEl = document.getElementById('modalMesa');
        if (modalEl && window.bootstrap) {
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        }
    }

    // --- PUNTOS DE VENTA ---
    function limpiarFormPdv() {
        const idEl = document.getElementById('pdvId');
        const nomEl = document.getElementById('pdvNombre');
        const ubiEl = document.getElementById('pdvUbicacion');
        const estEl = document.getElementById('pdvEstado');
        const titEl = document.getElementById('modalPdvTitulo');
        const btnEl = document.getElementById('btnGuardarPdv');

        if (idEl) idEl.value = '';
        if (nomEl) nomEl.value = '';
        if (ubiEl) ubiEl.value = '';
        if (estEl) estEl.value = 'activo';
        if (titEl) titEl.innerHTML = '<i class="bi bi-display text-warning me-2"></i> Crear Nuevo Punto de Venta';
        if (btnEl) btnEl.innerHTML = '<i class="bi bi-save me-1"></i> Crear Caja';
    }

    function editarPdv(btn) {
        const form = document.getElementById('formPdv');
        if (form) {
            form.querySelectorAll('input, select, textarea').forEach(function(el) {
                el.disabled = false;
                el.readOnly = false;
            });
        }

        const idEl = document.getElementById('pdvId');
        const nomEl = document.getElementById('pdvNombre');
        const ubiEl = document.getElementById('pdvUbicacion');
        const estEl = document.getElementById('pdvEstado');
        const titEl = document.getElementById('modalPdvTitulo');
        const btnEl = document.getElementById('btnGuardarPdv');

        if (idEl) idEl.value = btn.getAttribute('data-id') || '';
        if (nomEl) nomEl.value = btn.getAttribute('data-nombre') || '';
        if (ubiEl) ubiEl.value = btn.getAttribute('data-ubicacion') || '';
        if (estEl) estEl.value = btn.getAttribute('data-estado') || 'activo';
        if (titEl) titEl.innerHTML = '<i class="bi bi-pencil-square text-warning me-2"></i> Editar Punto de Venta';
        if (btnEl) btnEl.innerHTML = '<i class="bi bi-check-circle me-1"></i> Actualizar Caja';

        const modalEl = document.getElementById('modalPdv');
        if (modalEl && window.bootstrap) {
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        }
    }

    // --- PRODUCTOS ---
    function limpiarFormProductoCrud() {
        if (window.limpiarErroresFormulario) {
            window.limpiarErroresFormulario('#formProducto');
        }
        const idEl = document.getElementById('prodId');
        const codEl = document.getElementById('prodCodigo');
        const nomEl = document.getElementById('prodNombre');
        const descEl = document.getElementById('prodDescripcion');
        const precEl = document.getElementById('prodPrecio');
        const stockEl = document.getElementById('prodStock');
        const menuEl = document.getElementById('prodMenu');
        const titEl = document.getElementById('modalProductoTitulo');
        const btnEl = document.getElementById('btnGuardarProducto');

        if (idEl) idEl.value = '';
        if (codEl) codEl.value = '';
        if (nomEl) nomEl.value = '';
        if (descEl) descEl.value = '';
        if (precEl) precEl.value = '';
        if (stockEl) stockEl.value = '10';
        if (menuEl) menuEl.value = '';
        if (titEl) titEl.innerHTML = '<i class="bi bi-egg-fried text-warning me-2"></i> Crear Nuevo Producto';
        if (btnEl) btnEl.innerHTML = '<i class="bi bi-save me-1"></i> Crear Producto';
    }

    function editarProductoCrud(btn) {
        if (window.limpiarErroresFormulario) {
            window.limpiarErroresFormulario('#formProducto');
        }
        const form = document.getElementById('formProducto');
        if (form) {
            form.querySelectorAll('input, select, textarea').forEach(function(el) {
                el.disabled = false;
                el.readOnly = false;
            });
        }
        const idEl = document.getElementById('prodId');
        const codEl = document.getElementById('prodCodigo');
        const nomEl = document.getElementById('prodNombre');
        const descEl = document.getElementById('prodDescripcion');
        const precEl = document.getElementById('prodPrecio');
        const stockEl = document.getElementById('prodStock');
        const menuEl = document.getElementById('prodMenu');
        const titEl = document.getElementById('modalProductoTitulo');
        const btnEl = document.getElementById('btnGuardarProducto');

        if (idEl) idEl.value = btn.getAttribute('data-id') || '';
        if (codEl) codEl.value = btn.getAttribute('data-codigo') || '';
        if (nomEl) nomEl.value = btn.getAttribute('data-nombre') || '';
        if (descEl) descEl.value = btn.getAttribute('data-descripcion') || '';
        if (precEl) precEl.value = parseFloat(btn.getAttribute('data-precio') || 0);
        if (stockEl) stockEl.value = btn.getAttribute('data-stock') || 0;
        if (menuEl) menuEl.value = btn.getAttribute('data-menu') || '';
        if (titEl) titEl.innerHTML = '<i class="bi bi-pencil-square text-warning me-2"></i> Editar Producto';
        if (btnEl) btnEl.innerHTML = '<i class="bi bi-check-circle me-1"></i> Actualizar Producto';

        const modalEl = document.getElementById('modalProducto');
        if (modalEl && window.bootstrap) {
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        }
    }

    // --- USUARIOS CRUD ---
    function verificarCambioRol() {
        const rolEl = document.getElementById('userRol');
        const userIdEl = document.getElementById('userId');
        const seccion = document.getElementById('seccionConfirmAdmin');
        const confirmUser = document.getElementById('adminConfirmUser');
        const confirmPass = document.getElementById('adminConfirmPass');
        if (!rolEl || !userIdEl || !seccion || !confirmUser || !confirmPass) return;

        const rol = rolEl.value;
        const userId = userIdEl.value;
        const currentAdminId = getCurrentAdminId();

        const esCrearOtroAdmin = (rol === 'administrador' && (!userId || String(userId) !== String(currentAdminId)));

        if (esCrearOtroAdmin) {
            seccion.style.display = 'block';
            seccion.classList.remove('d-none');
            confirmUser.required = true;
            confirmPass.required = true;
        } else {
            seccion.style.display = 'none';
            seccion.classList.add('d-none');
            confirmUser.required = false;
            confirmPass.required = false;
        }
    }

    function limpiarFormUsuarioCrud() {
        const titEl = document.getElementById('modalUsuarioTitulo');
        const btnEl = document.getElementById('btnGuardarUsuario');
        const userId = document.getElementById('userId');
        const userRut = document.getElementById('userRut');
        const userNombre = document.getElementById('userNombre');
        const userCorreo = document.getElementById('userCorreo');
        const userUsername = document.getElementById('userUsername');
        const userPassword = document.getElementById('userPassword');
        const passObligatorio = document.getElementById('passObligatorio');
        const userRol = document.getElementById('userRol');
        const userEstado = document.getElementById('userEstado');

        if (userId) userId.value = '';
        if (userRut) userRut.value = '';
        if (userNombre) userNombre.value = '';
        if (userCorreo) userCorreo.value = '';
        if (userUsername) userUsername.value = '';
        if (userPassword) {
            userPassword.value = '';
            userPassword.required = true;
        }
        if (passObligatorio) {
            passObligatorio.style.display = 'inline';
            passObligatorio.classList.remove('d-none');
        }
        if (userRol) userRol.value = 'cajero';
        if (userEstado) userEstado.value = 'activo';
        if (titEl) titEl.innerHTML = '<i class="bi bi-person-plus-fill text-warning me-2"></i> Crear Nuevo Usuario';
        if (btnEl) btnEl.innerHTML = '<i class="bi bi-save me-1"></i> Crear Usuario';

        verificarCambioRol();
    }

    function editarUsuarioCrud(btn) {
        const targetUserId = btn.getAttribute('data-id') || '';
        const currentAdminId = getCurrentAdminId();
        if (targetUserId && currentAdminId && String(targetUserId) === String(currentAdminId)) {
            alert('No puedes desactivar ni modificar tu propia cuenta de administrador en sesión');
            return;
        }

        const form = document.getElementById('formUsuario');
        if (form) {
            form.querySelectorAll('input, select, textarea').forEach(function(el) {
                el.disabled = false;
                el.readOnly = false;
            });
        }

        const titEl = document.getElementById('modalUsuarioTitulo');
        const btnEl = document.getElementById('btnGuardarUsuario');
        const userId = document.getElementById('userId');
        const userRut = document.getElementById('userRut');
        const userNombre = document.getElementById('userNombre');
        const userCorreo = document.getElementById('userCorreo');
        const userUsername = document.getElementById('userUsername');
        const userPassword = document.getElementById('userPassword');
        const passObligatorio = document.getElementById('passObligatorio');
        const userRol = document.getElementById('userRol');
        const userEstado = document.getElementById('userEstado');

        if (userId) userId.value = targetUserId;
        if (userRut) userRut.value = btn.getAttribute('data-rut') || '';
        if (userNombre) userNombre.value = btn.getAttribute('data-nombre') || '';
        if (userCorreo) userCorreo.value = btn.getAttribute('data-correo') || '';
        if (userUsername) userUsername.value = btn.getAttribute('data-username') || '';
        if (userRol) userRol.value = btn.getAttribute('data-rol') || 'cajero';
        if (userEstado) userEstado.value = btn.getAttribute('data-estado') || 'activo';

        if (userPassword) {
            userPassword.value = '';
            userPassword.required = false;
        }
        if (passObligatorio) {
            passObligatorio.style.display = 'none';
            passObligatorio.classList.add('d-none');
        }
        if (titEl) titEl.innerHTML = '<i class="bi bi-pencil-square text-warning me-2"></i> Editar Usuario';
        if (btnEl) btnEl.innerHTML = '<i class="bi bi-check-circle me-1"></i> Actualizar Usuario';

        verificarCambioRol();

        const modalEl = document.getElementById('modalUsuario');
        if (modalEl && window.bootstrap) {
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        }
    }

    document.addEventListener('DOMContentLoaded', function() {
        // Confirmaciones de eliminación seguras en mantenedores
        document.body.addEventListener('click', function(e) {
            const link = e.target.closest('[data-action="confirm-delete"]');
            if (link) {
                const msg = link.getAttribute('data-confirm-msg') || '¿Confirma que desea eliminar este elemento?';
                if (!confirm(msg)) {
                    e.preventDefault();
                }
            }
        });

        // Menus
        document.querySelectorAll('[data-action="nuevo-menu"]').forEach(function(btn) {
            btn.addEventListener('click', limpiarFormMenu);
        });
        document.body.addEventListener('click', function(e) {
            const btn = e.target.closest('[data-action="editar-menu"]');
            if (btn) {
                e.preventDefault();
                editarMenu(btn);
            }
        });

        // Mesas
        document.querySelectorAll('[data-action="nueva-mesa"]').forEach(function(btn) {
            btn.addEventListener('click', limpiarFormMesa);
        });
        document.body.addEventListener('click', function(e) {
            const btn = e.target.closest('[data-action="editar-mesa"]');
            if (btn) {
                e.preventDefault();
                editarMesa(btn);
            }
        });

        // Puntos de Venta
        document.querySelectorAll('[data-action="nuevo-pdv"]').forEach(function(btn) {
            btn.addEventListener('click', limpiarFormPdv);
        });
        document.body.addEventListener('click', function(e) {
            const btn = e.target.closest('[data-action="editar-pdv"]');
            if (btn) {
                e.preventDefault();
                editarPdv(btn);
            }
        });

        // Productos CRUD
        document.querySelectorAll('[data-action="nuevo-producto-crud"]').forEach(function(btn) {
            btn.addEventListener('click', limpiarFormProductoCrud);
        });
        document.body.addEventListener('click', function(e) {
            const btn = e.target.closest('[data-action="editar-producto-crud"]');
            if (btn) {
                e.preventDefault();
                editarProductoCrud(btn);
            }
        });

        // Usuarios CRUD
        document.querySelectorAll('[data-action="nuevo-usuario-crud"]').forEach(function(btn) {
            btn.addEventListener('click', limpiarFormUsuarioCrud);
        });
        document.body.addEventListener('click', function(e) {
            const btn = e.target.closest('[data-action="editar-usuario-crud"]');
            if (btn) {
                e.preventDefault();
                editarUsuarioCrud(btn);
            }
        });

        const userRolSelect = document.getElementById('userRol');
        if (userRolSelect) {
            userRolSelect.addEventListener('change', verificarCambioRol);
        }

        // Subvista usuarios/registrar.html: cambio de rol
        const selectRolReg = document.getElementById('selectRol');
        if (selectRolReg) {
            selectRolReg.addEventListener('change', function() {
                const sec = document.getElementById('seccionAdminConfirm');
                if (sec) {
                    sec.style.display = (this.value === 'administrador') ? 'block' : 'none';
                    if (this.value === 'administrador') {
                        sec.classList.remove('d-none');
                    } else {
                        sec.classList.add('d-none');
                    }
                }
            });
        }

        // Subvista usuarios/actualizar.html: cambio de rol
        const selectRolAct = document.getElementById('selectRolActualizar');
        if (selectRolAct) {
            selectRolAct.addEventListener('change', function() {
                const sec = document.getElementById('seccionAdminConfirmActualizar');
                const form = selectRolAct.closest('form');
                const userId = form ? (form.getAttribute('data-target-user-id') || '') : '';
                const currentAdminId = form ? (form.getAttribute('data-current-admin-id') || '') : '';
                if (sec) {
                    const debeMostrar = (this.value === 'administrador' && String(userId) !== String(currentAdminId));
                    sec.style.display = debeMostrar ? 'block' : 'none';
                    if (debeMostrar) {
                        sec.classList.remove('d-none');
                    } else {
                        sec.classList.add('d-none');
                    }
                }
            });
        }

        // Desacoplar la navegación de los mantenedores de atributos ocultos manipulables en el DOM
        sincronizarNavegacionMantenedores();
    });

    function sincronizarNavegacionMantenedores() {
        const path = window.location.pathname;
        const navLinks = document.querySelectorAll('nav .nav-pills .nav-link');
        navLinks.forEach(function(link) {
            const href = link.getAttribute('href');
            if (!href) return;
            if (href === path || (href !== '/mantenedores/' && path.startsWith(href))) {
                link.classList.add('active');
            } else if (href === '/mantenedores/' && path === '/mantenedores/') {
                link.classList.add('active');
            } else if (href !== '#') {
                link.classList.remove('active');
            }
        });
    }
})();
