/**
 * Safari POS - Módulo Panel de Administración (administrador.html)
 * Gestiona edición de usuarios, validación de permisos de admin y confirmaciones seguras.
 */
(function() {
    'use strict';

    function getCurrentAdminId() {
        const form = document.getElementById('formUsuario');
        if (form && form.getAttribute('data-current-admin-id')) {
            return form.getAttribute('data-current-admin-id');
        }
        return document.body.getAttribute('data-current-admin-id') || '';
    }

    function actualizarConfirmacionAdmin() {
        const rolEl = document.getElementById('userRol');
        const userIdEl = document.getElementById('userId');
        const seccion = document.getElementById('seccionConfirmacionAdmin');
        const inputUser = document.getElementById('adminConfirmUser');
        const inputPass = document.getElementById('adminConfirmPass');
        if (!rolEl || !userIdEl || !seccion || !inputUser || !inputPass) return;

        const rol = rolEl.value;
        const targetUserId = userIdEl.value;
        const currentAdminId = getCurrentAdminId();

        const esCrearOtroAdmin = (rol === 'administrador' && String(targetUserId) !== String(currentAdminId));

        if (esCrearOtroAdmin) {
            seccion.classList.remove('d-none');
            inputUser.required = true;
            inputPass.required = true;
        } else {
            seccion.classList.add('d-none');
            inputUser.required = false;
            inputPass.required = false;
            inputUser.value = '';
            inputPass.value = '';
        }
    }

    function validarConfirmacionAdmin() {
        const rolEl = document.getElementById('userRol');
        const userIdEl = document.getElementById('userId');
        if (!rolEl || !userIdEl) return true;

        const rol = rolEl.value;
        const targetUserId = userIdEl.value;
        const currentAdminId = getCurrentAdminId();
        const esCrearOtroAdmin = (rol === 'administrador' && String(targetUserId) !== String(currentAdminId));

        if (esCrearOtroAdmin) {
            const conf = confirm('¿Está completamente seguro de crear/asignar otro usuario con permisos de Administrador? Tendrá control total sobre el sistema.');
            if (!conf) return false;

            const inputUser = document.getElementById('adminConfirmUser');
            const inputPass = document.getElementById('adminConfirmPass');
            const valUser = inputUser ? inputUser.value.trim() : '';
            const valPass = inputPass ? inputPass.value.trim() : '';

            if (!valUser || !valPass) {
                alert('Debe reingresar sus credenciales de administrador actual para autorizar la creación de otro administrador.');
                return false;
            }
        }
        return true;
    }

    function limpiarFormUsuario() {
        const tit = document.getElementById('modalUsuarioTitulo');
        if (tit) tit.innerText = 'Crear Nueva Cuenta';

        const userId = document.getElementById('userId');
        const userRut = document.getElementById('userRut');
        const userNombre = document.getElementById('userNombre');
        const userCorreo = document.getElementById('userCorreo');
        const userUsername = document.getElementById('userUsername');
        const userRol = document.getElementById('userRol');
        const userEstado = document.getElementById('userEstado');
        const userPassword = document.getElementById('userPassword');
        const userPasswordHelp = document.getElementById('userPasswordHelp');

        if (userId) userId.value = '';
        if (userRut) userRut.value = '';
        if (userNombre) userNombre.value = '';
        if (userCorreo) userCorreo.value = '';
        if (userUsername) userUsername.value = '';
        if (userRol) userRol.value = 'cajero';
        if (userEstado) userEstado.value = 'activo';
        if (userPassword) {
            userPassword.value = '';
            userPassword.required = true;
        }
        if (userPasswordHelp) userPasswordHelp.classList.add('d-none');

        actualizarConfirmacionAdmin();
    }

    function editarUsuario(btn) {
        const targetUserId = btn.getAttribute('data-id') || '';
        const currentAdminId = getCurrentAdminId();
        if (targetUserId && currentAdminId && String(targetUserId) === String(currentAdminId)) {
            alert('No puedes desactivar ni modificar tu propia cuenta de administrador en sesión');
            return;
        }

        const tit = document.getElementById('modalUsuarioTitulo');
        if (tit) tit.innerText = 'Modificar Cuenta de Empleado';

        // Asegurar que todos los inputs del formulario estén completamente habilitados y desbloqueados
        const form = document.getElementById('formUsuario');
        if (form) {
            form.querySelectorAll('input, select, textarea').forEach(function(el) {
                el.disabled = false;
                el.readOnly = false;
            });
        }

        const userId = document.getElementById('userId');
        const userRut = document.getElementById('userRut');
        const userNombre = document.getElementById('userNombre');
        const userCorreo = document.getElementById('userCorreo');
        const userUsername = document.getElementById('userUsername');
        const userRol = document.getElementById('userRol');
        const userEstado = document.getElementById('userEstado');
        const userPassword = document.getElementById('userPassword');
        const userPasswordHelp = document.getElementById('userPasswordHelp');

        if (userId) userId.value = targetUserId;
        if (userRut) userRut.value = btn.getAttribute('data-rut') || '';
        if (userNombre) userNombre.value = btn.getAttribute('data-nombre') || '';
        if (userUsername) userUsername.value = btn.getAttribute('data-username') || '';
        if (userCorreo) userCorreo.value = btn.getAttribute('data-correo') || '';
        if (userRol) userRol.value = btn.getAttribute('data-rol') || 'cajero';
        if (userEstado) userEstado.value = btn.getAttribute('data-estado') || 'activo';

        if (userPassword) {
            userPassword.value = '';
            userPassword.required = false;
        }
        if (userPasswordHelp) userPasswordHelp.classList.remove('d-none');

        actualizarConfirmacionAdmin();

        const modalEl = document.getElementById('modalUsuario');
        if (modalEl && window.bootstrap) {
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        }
    }

    document.addEventListener('DOMContentLoaded', function() {
        // Selector de rol en modal usuario
        const rolEl = document.getElementById('userRol');
        if (rolEl) {
            rolEl.addEventListener('change', actualizarConfirmacionAdmin);
        }

        // Formulario usuario: submit validation
        const formUsuario = document.getElementById('formUsuario');
        if (formUsuario) {
            formUsuario.addEventListener('submit', function(e) {
                if (!validarConfirmacionAdmin()) {
                    e.preventDefault();
                }
            });
        }

        // Botón nuevo usuario
        document.querySelectorAll('[data-action="nuevo-usuario"]').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                limpiarFormUsuario();
            });
        });

        // Botones editar usuario
        document.body.addEventListener('click', function(e) {
            const btn = e.target.closest('[data-action="editar-usuario"]');
            if (btn) {
                e.preventDefault();
                editarUsuario(btn);
            }
        });

        // Confirmaciones de eliminación seguras
        document.body.addEventListener('click', function(e) {
            const link = e.target.closest('[data-action="confirm-delete"]');
            if (link) {
                const msg = link.getAttribute('data-confirm-msg') || '¿Confirma que desea eliminar este elemento?';
                if (!confirm(msg)) {
                    e.preventDefault();
                }
            }
        });
    });
})();
