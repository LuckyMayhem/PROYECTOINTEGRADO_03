/**
 * validaciones.js
 * Capa de defensa activa en frontend contra inyecciones SQL y ataques Cross-Site Scripting (XSS).
 * 
 * Funcionalidades clave:
 * 1. Listener global en todos los <input type="text">, <textarea>, inputs de búsqueda y contraseñas.
 * 2. Bloqueo en tiempo real (keypress, input, paste) de caracteres y secuencias especiales prohibidas:
 *    " # $ % ! / & ( ) = : _ ; ' -- /*
 * 3. Inmunidad ante manipulación desde "Inspeccionar Elemento" (DevTools):
 *    Intercepta el evento 'submit' en fase de captura (capture phase) y aborta el envío si
 *    cualquier campo fue alterado maliciosamente en el DOM para inyectar caracteres especiales.
 * 4. Cumplimiento estricto de Content Security Policy (CSP): Cero scripts o estilos en línea.
 */

(function () {
    'use strict';

    // Límites estrictos de longitud para campos de Inicio de Sesión
    const LIMITES_LOGIN = {
        USUARIO: { MIN: 4, MAX: 30, NOMBRE: 'usuario' },
        PASSWORD: { MIN: 6, MAX: 25, NOMBRE: 'contraseña' }
    };

    // Patrón de caracteres estrictamente prohibidos:
    // " # $ % ! / & ( ) = : _ ; ' < > \ | ^ ~ { } [ ] -- /* */
    const REGEX_PROHIBIDOS_ESTRICTO = /[#$%\!/&()=:_;'"<>\\|^~{}[\]]|--|\/\*|\*\//;
    const REGEX_PROHIBIDOS_ESTRICTO_GLOBAL = /[#$%\!/&()=:_;'"<>\\|^~{}[\]]|--|\/\*|\*\//g;

    // Patrón para identificadores del sistema que requieren guion bajo (_) como usernames preexistentes
    const REGEX_PROHIBIDOS_IDENTIFICADOR = /[#$%\!/&()=:;'"<>\\|^~{}[\]]|--|\/\*|\*\//;
    const REGEX_PROHIBIDOS_IDENTIFICADOR_GLOBAL = /[#$%\!/&()=:;'"<>\\|^~{}[\]]|--|\/\*|\*\//g;

    /**
     * Determina si el campo es de nombre de usuario o login.
     */
    function esCampoUsuario(el) {
        if (!el) return false;
        const nombre = (el.name || '').toLowerCase();
        const id = (el.id || '').toLowerCase();
        return nombre === 'username' || id === 'username' || nombre === 'usuario' || id === 'usuario';
    }

    /**
     * Determina si el campo es de contraseña.
     */
    function esCampoPassword(el) {
        if (!el) return false;
        const nombre = (el.name || '').toLowerCase();
        const id = (el.id || '').toLowerCase();
        const type = (el.type || '').toLowerCase();
        return type === 'password' || nombre === 'password' || id === 'password';
    }

    /**
     * Protege el input de contraseña contra manipulación en DevTools.
     * Si alguien intenta cambiar type="password" a type="text" desde las herramientas de desarrollo
     * para espiar la clave, el MutationObserver lo detecta y lo devuelve instantáneamente a type="password".
     */
    function protegerInputPassword(inputPass) {
        if (!inputPass) return;

        // Asegurar que comience estrictamente como type="password"
        if (inputPass.getAttribute('type') !== 'password' || inputPass.type !== 'password') {
            inputPass.type = 'password';
            inputPass.setAttribute('type', 'password');
        }

        if (inputPass.dataset.proteccionPasswordActiva === 'true') return;
        inputPass.dataset.proteccionPasswordActiva = 'true';

        if (window.MutationObserver) {
            const observer = new MutationObserver(function (mutationsList) {
                for (let i = 0; i < mutationsList.length; i++) {
                    const m = mutationsList[i];
                    if (m.type === 'attributes' && m.attributeName === 'type') {
                        const tipoActual = inputPass.getAttribute('type');
                        if (tipoActual !== 'password' || inputPass.type !== 'password') {
                            inputPass.type = 'password';
                            inputPass.setAttribute('type', 'password');
                            console.warn('[Validaciones Defensivas] Intento de espiar contraseña mediante DevTools detectado. El tipo de campo se restableció instantáneamente a type="password".');
                        }
                    }
                }
            });

            observer.observe(inputPass, {
                attributes: true,
                attributeFilter: ['type']
            });
        }

        // Red de seguridad adicional ante cambios de atributo o eventos
        inputPass.addEventListener('change', function () {
            if (this.type !== 'password' || this.getAttribute('type') !== 'password') {
                this.type = 'password';
                this.setAttribute('type', 'password');
            }
        });
    }

    /**
     * Determina si el campo permite guion bajo (por ejemplo, identificadores de usuario o emails).
     */
    function permiteGuionBajo(el) {
        if (!el) return false;
        if (el.dataset && el.dataset.permitirGuionBajo === 'true') return true;
        const nombre = (el.name || '').toLowerCase();
        const id = (el.id || '').toLowerCase();
        return (
            nombre === 'username' ||
            nombre === 'usuario' ||
            nombre === 'correo' ||
            nombre === 'email' ||
            nombre === 'admin_confirm_username' ||
            id === 'username' ||
            id === 'usuario' ||
            id === 'correo' ||
            id === 'email'
        );
    }

    /**
     * Retorna el patrón regex aplicable según el tipo de campo.
     */
    function obtenerRegexCampo(el, global) {
        if (permiteGuionBajo(el)) {
            return global ? REGEX_PROHIBIDOS_IDENTIFICADOR_GLOBAL : REGEX_PROHIBIDOS_IDENTIFICADOR;
        }
        return global ? REGEX_PROHIBIDOS_ESTRICTO_GLOBAL : REGEX_PROHIBIDOS_ESTRICTO;
    }

    /**
     * Muestra alerta visual de validación defensiva en el DOM.
     */
    function marcarErrorValidacion(el, mensaje) {
        if (!el) return;
        el.classList.add('is-invalid');

        const contenedor = el.closest('.input-group') || el.parentElement;
        if (!contenedor) return;

        let feedback = contenedor.querySelector('.feedback-validacion-defensiva');
        if (!feedback && contenedor.parentElement) {
            feedback = contenedor.parentElement.querySelector(`.feedback-validacion-defensiva[data-for="${el.name || el.id}"]`);
        }

        if (!feedback) {
            feedback = document.createElement('div');
            feedback.className = 'feedback-validacion-defensiva invalid-feedback d-block fw-bold text-danger small mt-1';
            feedback.setAttribute('data-for', el.name || el.id);
            if (el.closest('.input-group') && contenedor.parentNode) {
                contenedor.parentNode.insertBefore(feedback, contenedor.nextSibling);
            } else {
                contenedor.appendChild(feedback);
            }
        }
        feedback.textContent = mensaje;
    }

    /**
     * Remueve la alerta visual de validación si el valor es seguro.
     */
    function limpiarErrorValidacion(el) {
        if (!el) return;
        el.classList.remove('is-invalid');
        const contenedor = el.closest('.input-group') || el.parentElement;
        if (contenedor) {
            const feedbacks = contenedor.querySelectorAll(`.feedback-validacion-defensiva[data-for="${el.name || el.id}"], .feedback-validacion-defensiva`);
            feedbacks.forEach(function (fb) {
                fb.remove();
            });
        }
    }

    /**
     * Sanitiza en tiempo real el valor de un campo eliminando caracteres especiales prohibidos.
     */
    function sanitizarCampoTiempoReal(el) {
        if (!el || typeof el.value !== 'string') return;

        // Sanitizar espacios en blanco en usuario y contraseña de login
        if (esCampoUsuario(el) || esCampoPassword(el)) {
            if (/\s/.test(el.value)) {
                el.value = el.value.replace(/\s+/g, '');
                marcarErrorValidacion(el, `No se permiten espacios en blanco en ${esCampoUsuario(el) ? 'el usuario' : 'la contraseña'}.`);
            }
        }

        const regexGlobal = obtenerRegexCampo(el, true);
        const valorOriginal = el.value;

        if (regexGlobal.test(valorOriginal)) {
            const valorLimpio = valorOriginal.replace(regexGlobal, '');
            el.value = valorLimpio;
            marcarErrorValidacion(el, 'Carácter especial bloqueado ("#$%!/&()=:_;\'", --, /*) por seguridad contra inyección SQL y XSS.');
            console.warn(`[Validaciones Defensivas] Se bloqueó y eliminó un carácter especial en el campo: "${el.name || el.id || 'desconocido'}"`);
        } else if (!esCampoUsuario(el) && !esCampoPassword(el)) {
            limpiarErrorValidacion(el);
        }
    }

    /**
     * Intercepta la pulsación de teclas en tiempo real para bloquear caracteres no permitidos.
     */
    function interceptarKeypress(e) {
        const el = e.target;
        if (!el) return;

        // Permitir teclas de control estándar
        if (e.ctrlKey || e.metaKey || e.altKey) return;

        const char = e.key;
        if (!char || char.length > 1) return; // Teclas especiales (Enter, Backspace, etc.)

        // Bloqueo en tiempo real de espacios en blanco en campos de login (usuario o contraseña)
        if (char === ' ' || e.code === 'Space') {
            if (esCampoUsuario(el) || esCampoPassword(el)) {
                e.preventDefault();
                marcarErrorValidacion(el, `No se permiten espacios en blanco en ${esCampoUsuario(el) ? 'el usuario' : 'la contraseña'}.`);
                console.warn(`[Validaciones Defensivas] Espacio bloqueado en campo: "${el.name || el.id}"`);
                return;
            }
        }

        const regex = obtenerRegexCampo(el, false);
        if (regex.test(char)) {
            e.preventDefault();
            marcarErrorValidacion(el, `El carácter "${char}" está estrictamente prohibido ("#$%!/&()=:_;'", --, /*).`);
            console.warn(`[Validaciones Defensivas] Pulsación bloqueada: "${char}" en el campo "${el.name || el.id}"`);
        }
    }

    /**
     * Intercepta el evento de pegado (paste) para bloquear o limpiar caracteres peligrosos.
     */
    function interceptarPegado(e) {
        const el = e.target;
        if (!el) return;

        let textoPegado = '';
        if (e.clipboardData && e.clipboardData.getData) {
            textoPegado = e.clipboardData.getData('text');
        } else if (window.clipboardData && window.clipboardData.getData) {
            textoPegado = window.clipboardData.getData('Text');
        }

        const regex = obtenerRegexCampo(el, false);
        if (regex.test(textoPegado)) {
            // Se programa sanitización inmediata tras la inserción
            setTimeout(function () {
                sanitizarCampoTiempoReal(el);
            }, 10);
        }
    }

    /**
     * Vincula los listeners de validación y bloqueo estricto a un elemento de formulario.
     */
    function vincularElementoValidacion(el) {
        if (!el || el.dataset.validacionEstrictaActiva === 'true') return;

        const tag = (el.tagName || '').toLowerCase();
        const type = (el.type || '').toLowerCase();

        // Aplicar a inputs de texto, búsqueda, passwords, y textareas
        const esInputTexto = (tag === 'input' && (
            type === 'text' ||
            type === 'search' ||
            type === 'password' ||
            type === 'email' ||
            type === '' ||
            !el.hasAttribute('type')
        ));
        const esTextarea = (tag === 'textarea');

        if (!esInputTexto && !esTextarea) return;

        el.dataset.validacionEstrictaActiva = 'true';

        // Activar protección por MutationObserver si el campo es de tipo contraseña
        if (esCampoPassword(el)) {
            protegerInputPassword(el);
        }

        el.addEventListener('keypress', interceptarKeypress);
        el.addEventListener('input', function () {
            sanitizarCampoTiempoReal(this);
        });
        el.addEventListener('paste', interceptarPegado);
        el.addEventListener('blur', function () {
            sanitizarCampoTiempoReal(this);
        });
    }

    /**
     * Interceptor global de envío de formularios en fase de captura (capture phase: true).
     * Garantiza inmunidad ante manipulaciones en DevTools / Inspeccionar Elemento:
     * 1. Intercepta el submit de login para forzar form.method = 'POST' antes de enviarse.
     * 2. Bloquea el envío si se detectan caracteres prohibidos (#, $, %, !, /, &, (, ), =, :, _, ;, ', ", --, /*).
     * 3. Valida rangos estrictos de longitud y ausencia de espacios en usuario (4-30) y contraseña (6-25).
     */
    document.addEventListener('submit', function (e) {
        const form = e.target;
        if (!form || form.tagName !== 'FORM') return;

        // 1. Evitar exposición de credenciales en URL: Forzar siempre method="POST" en el formulario de login
        const formActionStr = (form.getAttribute('action') || form.action || '').toLowerCase();
        const esFormLogin = (
            form.id === 'formLogin' ||
            formActionStr.includes('/login/') ||
            formActionStr.endsWith('/login') ||
            formActionStr === '/login/' ||
            formActionStr === 'login'
        );

        if (esFormLogin) {
            const metodoActual = (form.getAttribute('method') || form.method || '').toUpperCase();
            if (metodoActual !== 'POST') {
                form.setAttribute('method', 'POST');
                form.method = 'POST';
                console.warn('[Validaciones Defensivas] Formulario de login interceptado con method alterado a GET en DevTools. Se forzó method="POST" antes de enviarse.');
            }
        }

        // 2. Validación de caracteres prohibidos en todos los campos
        const campos = form.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="checkbox"]):not([type="radio"]):not([type="button"]), textarea');
        let formularioValido = true;
        let primerCampoInvalido = null;
        let mensajeBloqueo = '';

        campos.forEach(function (campo) {
            const regex = obtenerRegexCampo(campo, false);
            const valor = campo.value || '';

            if (regex.test(valor)) {
                formularioValido = false;
                mensajeBloqueo = `El campo "${campo.name || campo.id || 'del formulario'}" contiene caracteres o secuencias prohibidas ("#$%!/&()=:_;'", --, /*).`;
                marcarErrorValidacion(campo, mensajeBloqueo);
                if (!primerCampoInvalido) {
                    primerCampoInvalido = campo;
                }
            }
        });

        if (!formularioValido) {
            // Bloquear terminantemente el envío del formulario
            e.preventDefault();
            e.stopImmediatePropagation();

            if (primerCampoInvalido) {
                primerCampoInvalido.focus();
            }

            console.warn('[Validaciones Defensivas] Formulario BLOQUEADO: Se detectó alteración con caracteres prohibidos (DevTools o bypass).');
            alert(`[Alerta de Seguridad]\n\nEl envío del formulario ha sido bloqueado.\n${mensajeBloqueo}\n\nPor favor, corrija los datos para continuar.`);
            return false;
        }

        // 3. Validación estricta de límites de longitud y espacios para Inicio de Sesión
        if (esFormLogin) {
            const inputUser = form.querySelector('input[name="username"], #username, input[name="usuario"]');
            const inputPass = form.querySelector('input[name="password"], input[type="password"], #password');

            if (inputUser) {
                const valUser = inputUser.value || '';
                // Rechazo de espacios en blanco
                if (/\s/.test(valUser)) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    const msgEspacio = 'El usuario no puede contener espacios en blanco.';
                    marcarErrorValidacion(inputUser, msgEspacio);
                    inputUser.focus();
                    alert(`[Alerta de Seguridad]\n\n${msgEspacio}`);
                    return false;
                }
                // Rango de longitud: mínimo 4, máximo 30 caracteres
                if (valUser.length < LIMITES_LOGIN.USUARIO.MIN || valUser.length > LIMITES_LOGIN.USUARIO.MAX) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    const msgRango = `El usuario debe tener entre ${LIMITES_LOGIN.USUARIO.MIN} y ${LIMITES_LOGIN.USUARIO.MAX} caracteres (actual: ${valUser.length}).`;
                    marcarErrorValidacion(inputUser, msgRango);
                    inputUser.focus();
                    alert(`[Alerta de Seguridad]\n\n${msgRango}`);
                    return false;
                }
            }

            if (inputPass) {
                const valPass = inputPass.value || '';
                // Rechazo de espacios en blanco
                if (/\s/.test(valPass)) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    const msgEspacio = 'La contraseña no puede contener espacios en blanco.';
                    marcarErrorValidacion(inputPass, msgEspacio);
                    inputPass.focus();
                    alert(`[Alerta de Seguridad]\n\n${msgEspacio}`);
                    return false;
                }
                // Rango de longitud: mínimo 6, máximo 25 caracteres
                if (valPass.length < LIMITES_LOGIN.PASSWORD.MIN || valPass.length > LIMITES_LOGIN.PASSWORD.MAX) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    const msgRango = `La contraseña debe tener entre ${LIMITES_LOGIN.PASSWORD.MIN} y ${LIMITES_LOGIN.PASSWORD.MAX} caracteres (actual: ${valPass.length}).`;
                    marcarErrorValidacion(inputPass, msgRango);
                    inputPass.focus();
                    alert(`[Alerta de Seguridad]\n\n${msgRango}`);
                    return false;
                }
            }
        }
    }, true); // useCapture = true para máxima prioridad de ejecución

    /**
     * Inicialización en carga del DOM y delegación dinámica.
     */
    document.addEventListener('DOMContentLoaded', function () {
        // Vincular todos los inputs de texto y textareas existentes
        document.querySelectorAll('input, textarea').forEach(vincularElementoValidacion);

        // Activar observador de mutación para inputs de contraseña
        document.querySelectorAll('input[type="password"], input[name="password"], #password').forEach(protegerInputPassword);

        // Observer para nuevos elementos inyectados dinámicamente en el DOM (modales, AJAX)
        if (window.MutationObserver && document.body) {
            const observer = new MutationObserver(function (mutations) {
                mutations.forEach(function (m) {
                    m.addedNodes.forEach(function (node) {
                        if (node.nodeType === 1) {
                            if (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA') {
                                vincularElementoValidacion(node);
                                if (esCampoPassword(node)) protegerInputPassword(node);
                            } else if (node.querySelectorAll) {
                                node.querySelectorAll('input, textarea').forEach(vincularElementoValidacion);
                                node.querySelectorAll('input[type="password"], input[name="password"], #password').forEach(protegerInputPassword);
                            }
                        }
                    });
                });
            });

            observer.observe(document.body, { childList: true, subtree: true });
        }
    });

    // Delegación ante focusin para inputs generados en tiempo real
    document.addEventListener('focusin', function (e) {
        if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) {
            vincularElementoValidacion(e.target);
        }
    });

    // Exponer API en ventana global
    window.ValidacionesDefensivasSafari = {
        validarCampo: function (el) {
            sanitizarCampoTiempoReal(el);
            const regex = obtenerRegexCampo(el, false);
            return !regex.test(el.value || '');
        },
        vincularElemento: vincularElementoValidacion
    };
})();
