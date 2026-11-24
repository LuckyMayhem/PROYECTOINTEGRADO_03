/**
 * seguridad_formularios.js
 * Capa de seguridad global contra manipulación de formularios desde el Inspector de Google (DevTools)
 * y Bloqueo / Eliminación estricta de Caracteres Especiales en todos los campos de escritura (login y otros).
 * 
 * Medidas de Seguridad implementadas:
 * 1. Eliminación y Bloqueo en Tiempo Real de Caracteres Especiales:
 *    - Se aplica en TODOS los campos de entrada (<input>, <textarea>) en todas las páginas (login, stock, mantenedores, modales).
 *    - Bloqueo en tiempo real (keydown, input, paste, blur) y rechazo estricto en submit.
 *    - Tipos de campo blindados:
 *      * Contraseña / Login: Bloqueo de caracteres de inyección (< > " ' ; $ ` \ / | ^ * ~ [ ] { } % -- /* */).
 *      * Usuario / Correo: Solo caracteres alfanuméricos y separadores estándar ([a-zA-Z0-9@._-]).
 *      * Numéricos (Precio, Stock, Número, Capacidad, Montos): Solo dígitos 0-9 (bloqueo estricto de -, ., ,, +, e, E).
 *      * RUT: Solo dígitos, puntos, guion y K ([0-9kK.-]).
 *      * Textos generales (Nombre, Descripción, Ubicación, Búsquedas): Bloqueo de caracteres XSS/SQL (< > " ' ; $ ` \ | ^ ~ { } [ ] -- /* */).
 * 2. Bloqueo de cambio de método POST a GET:
 *    - Evita que atacantes o testers modifiquen method="POST" a method="GET" en el Inspector de Elementos.
 *    - Impide que los nombres de los campos (nombre, precio, stock, password, csrf, etc.) y sus valores
 *      sean expuestos o queden visibles en la barra de direcciones (URL) o en el historial del navegador.
 * 3. MutationObserver activo:
 *    - Monitorea en tiempo real cambios en el DOM tanto para métodos de formulario como para nuevos inputs agregados dinámicamente.
 * 4. Intercepción en fase de captura (submit event capture):
 *    - Si un formulario o sus campos contienen datos alterados o método GET, bloquea el envío (preventDefault/stopImmediatePropagation).
 * 5. Sanitizador de URL en carga de página:
 *    - Si la URL contiene parámetros filtrados de formulario por GET involuntario, limpia la barra de direcciones con replaceState.
 */

(function () {
    'use strict';

    // Expresiones regulares para detección y bloqueo de caracteres prohibidos
    const REGEX_CARACTERES_PROHIBIDOS = /[<>"';$`\\|^~{}[\]]|--|\/\*|\*\//;
    const REGEX_CARACTERES_PROHIBIDOS_GLOBAL = /[<>"';$`\\|^~{}[\]]|--|\/\*|\*\//g;
    const REGEX_SOLO_DIGITOS = /^\d+$/;
    const REGEX_SOLO_USUARIO = /^[a-zA-Z0-9@._-]+$/;

    // Lista de parámetros sensibles o nombres de campos que nunca deben exponerse en la URL
    const CAMPOS_FORMULARIO_SENSIBLES = [
        'nombre', 'descripcion', 'precio', 'stock', 'codigo',
        'password', 'csrfmiddlewaretoken', 'rut', 'correo', 'username',
        'menu_id', 'prod_id', 'user_id', 'mesa_id', 'pdv_id', 'monto_inicial', 'monto_real'
    ];

    /**
     * Limpia la barra de direcciones del navegador si detecta campos de formulario en la URL (GET residual).
     */
    function sanitizarUrlExpuesta() {
        if (!window.location.search || !window.history || !window.history.replaceState) {
            return;
        }

        try {
            const params = new URLSearchParams(window.location.search);
            const contieneCamposFormulario = CAMPOS_FORMULARIO_SENSIBLES.some(campo => params.has(campo));

            if (contieneCamposFormulario) {
                const urlLimpia = window.location.pathname;
                window.history.replaceState({}, document.title, urlLimpia);
                console.warn('[Seguridad Safari] Se detectaron campos de formulario expuestos en la URL. Se limpió la barra de direcciones.');
            }
        } catch (e) {
            console.error('[Seguridad Safari] Error al sanitizar URL:', e);
        }
    }

    /**
     * Determina la categoría del campo para aplicar las reglas de caracteres correspondientes.
     */
    function obtenerCategoriaCampo(el) {
        const type = (el.type || '').toLowerCase();
        const name = (el.name || '').toLowerCase();
        const id = (el.id || '').toLowerCase();

        // 1. Campos Numéricos Estrictos
        if (type === 'number' ||
            name.includes('precio') || name.includes('stock') || name.includes('numero') ||
            name.includes('capacidad') || name.includes('monto') || name.includes('cantidad') ||
            id.includes('precio') || id.includes('stock') || id.includes('monto') ||
            id.includes('cantidad') || id === 'inputmontoinicial' || id === 'inputmontoreal') {
            return 'NUMERIC';
        }

        // 2. Campo Contraseña (Login, Registro, Confirmación)
        if (type === 'password' || name.includes('password') || id.includes('password') || id.includes('pass')) {
            return 'PASSWORD';
        }

        // 3. Campo RUT
        if (name.includes('rut') || id.includes('rut')) {
            return 'RUT';
        }

        // 4. Campo Correo / Email
        if (type === 'email' || name.includes('correo') || name.includes('email') || id.includes('correo')) {
            return 'EMAIL';
        }

        // 5. Campo Nombre de Usuario
        if (name.includes('username') || name.includes('usuario') || id.includes('username') || id.includes('user')) {
            return 'USERNAME';
        }

        // 6. Texto General (Nombre, Descripción, Ubicación, Búsquedas, etc.)
        return 'TEXT';
    }

    /**
     * Muestra mensaje de advertencia visual en el input.
     */
    function marcarErrorCampo(input, mensaje) {
        if (!input) return;
        input.classList.add('is-invalid');
        input.classList.remove('is-valid');

        const contenedor = input.closest('.input-group') || input.parentElement;
        if (!contenedor) return;

        let feedback = contenedor.parentElement ? contenedor.parentElement.querySelector(`.feedback-seguridad[data-for="${input.name || input.id}"]`) : null;
        if (!feedback) {
            feedback = contenedor.querySelector(`.feedback-seguridad[data-for="${input.name || input.id}"]`);
        }

        if (!feedback) {
            feedback = document.createElement('div');
            feedback.className = 'feedback-seguridad invalid-feedback d-block fw-semibold text-danger small mt-1';
            feedback.setAttribute('data-for', input.name || input.id);
            if (input.closest('.input-group')) {
                contenedor.parentNode.insertBefore(feedback, contenedor.nextSibling);
            } else {
                input.parentNode.appendChild(feedback);
            }
        }
        feedback.textContent = mensaje;
    }

    /**
     * Remueve la marca de error si el campo está limpio.
     */
    function limpiarErrorCampo(input) {
        if (!input) return;
        input.classList.remove('is-invalid');
        const contenedor = input.closest('.input-group') ? input.closest('.input-group').parentNode : input.parentElement;
        if (contenedor) {
            const feedback = contenedor.querySelector(`.feedback-seguridad[data-for="${input.name || input.id}"]`);
            if (feedback) feedback.remove();
        }
    }

    /**
     * Limpia en tiempo real cualquier carácter especial según la categoría del campo.
     */
    function sanitizarValorEnTiempoReal(input) {
        if (!input || typeof input.value !== 'string') return;
        const categoria = obtenerCategoriaCampo(input);
        const valorOriginal = input.value;
        let valorLimpio = valorOriginal;

        switch (categoria) {
            case 'NUMERIC':
                // Solo dígitos enteros positivos (0-9)
                valorLimpio = valorOriginal.replace(/\D/g, '');
                break;

            case 'PASSWORD':
                // Bloquea caracteres especiales XSS/SQL en contraseñas
                valorLimpio = valorOriginal.replace(/[<>"';$`\\|^~{}[\]%]|--|\/\*|\*\//g, '');
                break;

            case 'USERNAME':
                // Solo caracteres alfanuméricos y separadores estándar
                valorLimpio = valorOriginal.replace(/[^a-zA-Z0-9@._-]/g, '');
                break;

            case 'EMAIL':
                // Solo caracteres permitidos en correos
                valorLimpio = valorOriginal.replace(/[^a-zA-Z0-9@._-]/g, '');
                break;

            case 'RUT':
                // Solo dígitos, puntos, guion y K
                valorLimpio = valorOriginal.replace(/[^0-9kK.-]/g, '');
                break;

            case 'TEXT':
            default:
                // Bloquea caracteres especiales peligrosos en campos de texto generales
                valorLimpio = valorOriginal.replace(REGEX_CARACTERES_PROHIBIDOS_GLOBAL, '');
                break;
        }

        if (valorOriginal !== valorLimpio) {
            input.value = valorLimpio;
            console.warn(`[Seguridad Safari] Carácter especial eliminado en el campo "${input.name || input.id}".`);
        } else {
            limpiarErrorCampo(input);
        }
    }

    /**
     * Previene en keydown la escritura de teclas no permitidas.
     */
    function interceptarKeydown(e) {
        const input = e.target;
        if (!input) return;

        // Permitir teclas de control del teclado
        const teclasPermitidas = [
            'Backspace', 'Tab', 'Enter', 'Escape', 'ArrowLeft', 'ArrowRight',
            'ArrowUp', 'ArrowDown', 'Delete', 'Home', 'End'
        ];
        if (teclasPermitidas.includes(e.key) || e.ctrlKey || e.metaKey || e.altKey) {
            return;
        }

        const categoria = obtenerCategoriaCampo(input);

        if (categoria === 'NUMERIC') {
            // Bloqueo explícito de signos negativos, puntos, comas, signos más y notación exponencial
            if (['-', '.', ',', '+', 'e', 'E'].includes(e.key) || !/^\d$/.test(e.key)) {
                e.preventDefault();
            }
        } else if (categoria === 'PASSWORD') {
            // Bloqueo de caracteres prohibidos en contraseña
            if (['<', '>', '"', "'", ';', '$', '`', '\\', '|', '^', '~', '{', '}', '[', ']', '%'].includes(e.key)) {
                e.preventDefault();
            }
        } else if (categoria === 'USERNAME' || categoria === 'EMAIL') {
            if (!/^[a-zA-Z0-9@._-]$/.test(e.key)) {
                e.preventDefault();
            }
        } else if (categoria === 'RUT') {
            if (!/^[0-9kK.-]$/.test(e.key)) {
                e.preventDefault();
            }
        } else {
            // General TEXT: Bloquear caracteres especiales potencialmente dañinos
            if (['<', '>', '"', "'", ';', '$', '`', '\\', '|', '^', '~', '{', '}', '[', ']'].includes(e.key)) {
                e.preventDefault();
            }
        }
    }

    /**
     * Intercepta el pegado de texto para limpiarlo antes de que se inserte en el campo.
     */
    function interceptarPaste(e) {
        const input = e.target;
        if (!input) return;

        // Se programa una sanitización inmediata tras el evento paste
        setTimeout(function () {
            sanitizarValorEnTiempoReal(input);
        }, 10);
    }

    /**
     * Valida un campo individual antes del envío del formulario.
     * Retorna true si es válido o false si contiene caracteres especiales no permitidos.
     */
    function validarCampoEnSubmit(input) {
        if (!input || input.disabled) return true;
        const categoria = obtenerCategoriaCampo(input);
        const valor = input.value;

        // Campos vacíos se validan por el atributo 'required' nativo o por JS específico
        if (!valor || valor.trim().length === 0) {
            return true;
        }

        switch (categoria) {
            case 'NUMERIC':
                if (!REGEX_SOLO_DIGITOS.test(valor.trim())) {
                    marcarErrorCampo(input, 'Este campo debe contener únicamente números enteros positivos.');
                    return false;
                }
                break;

            case 'PASSWORD':
                if (REGEX_CARACTERES_PROHIBIDOS.test(valor)) {
                    marcarErrorCampo(input, 'La contraseña no puede contener caracteres especiales no permitidos (<, >, ", \', ;, $, --, /*).');
                    return false;
                }
                break;

            case 'USERNAME':
                if (!REGEX_SOLO_USUARIO.test(valor.trim())) {
                    marcarErrorCampo(input, 'El usuario o correo contiene caracteres especiales no permitidos.');
                    return false;
                }
                break;

            case 'EMAIL':
                if (!/^[a-zA-Z0-9@._-]+$/.test(valor.trim())) {
                    marcarErrorCampo(input, 'El correo electrónico contiene caracteres no permitidos.');
                    return false;
                }
                break;

            case 'RUT':
                if (!/^[0-9kK.-]+$/.test(valor.trim())) {
                    marcarErrorCampo(input, 'El RUT contiene caracteres no permitidos.');
                    return false;
                }
                break;

            case 'TEXT':
            default:
                if (REGEX_CARACTERES_PROHIBIDOS.test(valor)) {
                    marcarErrorCampo(input, 'Este campo contiene caracteres especiales prohibidos (<, >, ", \', ;, $, --, /*).');
                    return false;
                }
                break;
        }

        limpiarErrorCampo(input);
        return true;
    }

    /**
     * Aplica los listeners de sanitización a un input de escritura.
     */
    function vincularCampoDeEscritura(input) {
        if (!input || input.dataset.seguridadSanitizacionActiva === 'true') return;

        const tag = (input.tagName || '').toLowerCase();
        const type = (input.type || '').toLowerCase();

        // Omitir campos que no son de escritura de texto/números
        if (['hidden', 'checkbox', 'radio', 'submit', 'button', 'reset', 'file'].includes(type)) {
            return;
        }

        input.dataset.seguridadSanitizacionActiva = 'true';

        input.addEventListener('keydown', interceptarKeydown);
        input.addEventListener('input', function () {
            sanitizarValorEnTiempoReal(this);
        });
        input.addEventListener('paste', interceptarPaste);
        input.addEventListener('blur', function () {
            sanitizarValorEnTiempoReal(this);
        });
    }

    /**
     * Protege un formulario individual para garantizar que use POST y valide todos sus campos.
     */
    function protegerFormulario(form) {
        if (!form || form.dataset.seguridadPostActiva === 'true') return;
        form.dataset.seguridadPostActiva = 'true';

        // Si el formulario explícitamente permite GET (ej: formulario de solo búsqueda sin campos sensibles), omitir cambio a POST
        if (form.dataset.permiteGet !== 'true') {
            const metodoAttr = (form.getAttribute('method') || '').toUpperCase();
            if (metodoAttr !== 'POST') {
                form.setAttribute('method', 'POST');
                form.method = 'POST';
            }

            // Observer contra modificaciones de method en DevTools
            if (window.MutationObserver) {
                const observer = new MutationObserver(function (mutations) {
                    mutations.forEach(function (m) {
                        if (m.type === 'attributes' && m.attributeName === 'method') {
                            const nuevoMetodo = (form.getAttribute('method') || '').toUpperCase();
                            if (nuevoMetodo !== 'POST') {
                                form.setAttribute('method', 'POST');
                                form.method = 'POST';
                                console.warn('[Seguridad Safari] Intento de manipulación en DevTools detectado: method alterado a GET. Se restableció automáticamente a POST para proteger los nombres de los campos.');
                            }
                        }
                    });
                });

                observer.observe(form, { attributes: true, attributeFilter: ['method'] });
            }
        }

        // Vincular todos los campos de escritura dentro del formulario
        form.querySelectorAll('input, textarea').forEach(vincularCampoDeEscritura);
    }

    /**
     * Interceptor global en fase de captura del evento submit.
     * Se ejecuta ANTES de cualquier otro manejador y antes de que el navegador procese el envío.
     */
    document.addEventListener('submit', function (evento) {
        const form = evento.target;
        if (!form || form.tagName !== 'FORM') return;

        // 1. Bloqueo de manipulación DevTools (cambio de method POST a GET)
        if (form.dataset.permiteGet !== 'true') {
            const metodo = (form.getAttribute('method') || form.method || 'GET').toUpperCase();
            if (metodo !== 'POST') {
                evento.preventDefault();
                evento.stopImmediatePropagation();

                form.setAttribute('method', 'POST');
                form.method = 'POST';

                console.warn('[Seguridad Safari] Bloqueo de envío GET no autorizado. Se forzó method="POST" para evitar exponer campos en la URL.');
                alert('Alerta de Seguridad: No se permite enviar este formulario mediante el método GET. Los nombres y datos de los campos no deben ser expuestos en la URL. El método ha sido restablecido a POST seguro.');
                return false;
            }
        }

        // 2. Validación estricta de ausencia de caracteres especiales en todos los campos de escritura
        const campos = form.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]), textarea');
        let formValido = true;
        let primerInvalido = null;

        campos.forEach(function (campo) {
            sanitizarValorEnTiempoReal(campo);
            const esValido = validarCampoEnSubmit(campo);
            if (!esValido) {
                formValido = false;
                if (!primerInvalido) primerInvalido = campo;
            }
        });

        if (!formValido) {
            evento.preventDefault();
            evento.stopImmediatePropagation();
            if (primerInvalido) {
                primerInvalido.focus();
            }
            console.warn('[Seguridad Safari] Envío detenido: se detectaron caracteres especiales no permitidos en el formulario.');
            return false;
        }
    }, true); // useCapture = true para máxima prioridad de intercepción

    // Delegación global para interceptar cualquier input o textarea creado dinámicamente
    document.addEventListener('focusin', function (e) {
        const target = e.target;
        if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) {
            vincularCampoDeEscritura(target);
        }
    });

    // Inicializar protección y sanitización al cargar el DOM
    document.addEventListener('DOMContentLoaded', function () {
        sanitizarUrlExpuesta();

        // Proteger todos los formularios y sus campos
        document.querySelectorAll('form').forEach(protegerFormulario);

        // Vincular cualquier input suelto (ej: buscadores fuera de forms o filtros en modales)
        document.querySelectorAll('input, textarea').forEach(vincularCampoDeEscritura);

        // Observar inputs y formularios agregados dinámicamente al DOM (modales, AJAX)
        if (window.MutationObserver && document.body) {
            const bodyObserver = new MutationObserver(function (mutations) {
                mutations.forEach(function (m) {
                    m.addedNodes.forEach(function (node) {
                        if (node.nodeType === 1) {
                            if (node.tagName === 'FORM') {
                                protegerFormulario(node);
                            } else if (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA') {
                                vincularCampoDeEscritura(node);
                            } else if (node.querySelectorAll) {
                                node.querySelectorAll('form').forEach(protegerFormulario);
                                node.querySelectorAll('input, textarea').forEach(vincularCampoDeEscritura);
                            }
                        }
                    });
                });
            });

            bodyObserver.observe(document.body, { childList: true, subtree: true });
        }
    });

    // Exponer API de seguridad en el ámbito global
    window.seguridadFormulariosSafari = {
        sanitizarUrlExpuesta: sanitizarUrlExpuesta,
        sanitizarCampo: sanitizarValorEnTiempoReal,
        protegerFormulario: protegerFormulario,
        vincularCampo: vincularCampoDeEscritura
    };

    window.protegerFormulariosContraGet = function () {
        sanitizarUrlExpuesta();
        document.querySelectorAll('form').forEach(protegerFormulario);
        document.querySelectorAll('input, textarea').forEach(vincularCampoDeEscritura);
    };

})();
