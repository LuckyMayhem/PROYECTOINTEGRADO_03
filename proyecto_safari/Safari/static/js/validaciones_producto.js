/**
 * validaciones_producto.js
 * Capa estricta de validación JavaScript en el frontend para formularios de Productos
 * (Crear y Actualizar Productos en Safari POS)
 * 
 * Medidas de Seguridad implementadas:
 * - Validación en tiempo real (input, blur, keydown) y en evento submit.
 * - Validación estricta de longitudes y bloqueo de cadenas con solo espacios en blanco.
 * - Expresión Regular para bloqueo de caracteres XSS/Inyección: <, >, ", ', ;, --
 * - Validación numérica estricta para Precio y Stock (bloqueo de -, ., ,, .., ,,, .-).
 * - Defensa activa contra DevTools: No depende de atributos HTML (required, pattern, min, max).
 */

(function () {
    'use strict';

    // Expresión Regular de caracteres prohibidos para mitigar XSS y ataques de inyección básica
    const REGEX_CARACTERES_PROHIBIDOS = /[<>"';]|--/;

    // Expresión Regular numérica estricta: únicamente dígitos enteros positivos
    const REGEX_SOLO_DIGITOS = /^\d+$/;

    /**
     * Muestra el mensaje de error bajo el campo correspondiente y aplica estilos de Bootstrap.
     */
    function mostrarError(input, mensaje) {
        if (!input) return;
        input.classList.add('is-invalid');
        input.classList.remove('is-valid');

        // Determinar el contenedor padre adecuado (considerando .input-group)
        const contenedor = input.closest('.input-group') || input.parentElement;
        let feedback = contenedor.parentElement.querySelector(`.feedback-error-js[data-for="${input.name || input.id}"]`);
        
        if (!feedback) {
            feedback = contenedor.querySelector(`.feedback-error-js[data-for="${input.name || input.id}"]`);
        }

        if (!feedback) {
            feedback = document.createElement('div');
            feedback.className = 'feedback-error-js invalid-feedback d-block fw-semibold text-danger small mt-1';
            feedback.setAttribute('data-for', input.name || input.id);

            if (input.closest('.input-group')) {
                contenedor.parentNode.insertBefore(feedback, contenedor.nextSibling);
            } else {
                input.parentNode.appendChild(feedback);
            }
        }

        feedback.innerHTML = `<i class="bi bi-exclamation-triangle-fill me-1"></i> ${mensaje}`;
    }

    /**
     * Limpia el mensaje de error y marca el campo como válido.
     */
    function limpiarError(input) {
        if (!input) return;
        input.classList.remove('is-invalid');
        input.classList.add('is-valid');

        const contenedor = input.closest('.input-group') ? input.closest('.input-group').parentNode : input.parentElement;
        const feedback = contenedor.querySelector(`.feedback-error-js[data-for="${input.name || input.id}"]`);
        if (feedback) {
            feedback.remove();
        }
    }

    /**
     * Valida el campo Nombre del Producto:
     * - Obligatorio (no solo espacios en blanco).
     * - Longitud entre 3 y 100 caracteres.
     * - Sin caracteres prohibidos (<, >, ", ', ;, --).
     */
    function validarNombre(input) {
        if (!input) return true;
        const valor = input.value;
        const valorTrim = valor.trim();

        if (valorTrim.length === 0) {
            mostrarError(input, 'El nombre del producto es obligatorio y no puede consistir únicamente en espacios en blanco.');
            return false;
        }

        if (valorTrim.length < 3) {
            mostrarError(input, `El nombre debe tener al menos 3 caracteres (actual: ${valorTrim.length}).`);
            return false;
        }

        if (valorTrim.length > 100) {
            mostrarError(input, `El nombre no puede exceder los 100 caracteres (actual: ${valorTrim.length}).`);
            return false;
        }

        if (REGEX_CARACTERES_PROHIBIDOS.test(valor)) {
            mostrarError(input, 'El nombre contiene caracteres especiales prohibidos (<, >, ", \', ;, --) no permitidos por seguridad.');
            return false;
        }

        limpiarError(input);
        return true;
    }

    /**
     * Valida la Descripción del Producto:
     * - Opcional, pero si se escribe texto no puede ser solo espacios.
     * - Longitud máxima de 255 caracteres.
     * - Sin caracteres prohibidos (<, >, ", ', ;, --).
     */
    function validarDescripcion(input) {
        if (!input) return true;
        const valor = input.value;

        if (valor.length > 0 && valor.trim().length === 0) {
            mostrarError(input, 'La descripción no puede contener únicamente espacios en blanco.');
            return false;
        }

        if (valor.trim().length > 255) {
            mostrarError(input, `La descripción no puede superar los 255 caracteres (actual: ${valor.trim().length}).`);
            return false;
        }

        if (REGEX_CARACTERES_PROHIBIDOS.test(valor)) {
            mostrarError(input, 'La descripción contiene caracteres especiales prohibidos (<, >, ", \', ;, --).');
            return false;
        }

        limpiarError(input);
        return true;
    }

    /**
     * Valida el Código SKU:
     * - Opcional, pero si se ingresa no puede ser solo espacios.
     * - Longitud máxima de 50 caracteres.
     * - Sin caracteres prohibidos (<, >, ", ', ;, --).
     */
    function validarCodigo(input) {
        if (!input) return true;
        const valor = input.value;

        if (valor.length > 0 && valor.trim().length === 0) {
            mostrarError(input, 'El código SKU no puede consistir únicamente en espacios.');
            return false;
        }

        if (valor.trim().length > 50) {
            mostrarError(input, 'El código SKU no puede superar los 50 caracteres.');
            return false;
        }

        if (REGEX_CARACTERES_PROHIBIDOS.test(valor)) {
            mostrarError(input, 'El código SKU contiene caracteres prohibidos (<, >, ", \', ;, --).');
            return false;
        }

        limpiarError(input);
        return true;
    }

    /**
     * Valida el Precio en CLP:
     * - Obligatorio.
     * - Únicamente dígitos enteros positivos (/^\d+$/).
     * - Rechaza explícitamente el signo negativo (-), puntos (.) y comas (,).
     * - Debe ser estrictamente mayor a 0 CLP.
     */
    function validarPrecio(input) {
        if (!input) return true;
        const valor = String(input.value).trim();

        if (valor.length === 0) {
            mostrarError(input, 'El precio en CLP es obligatorio.');
            return false;
        }

        // Detección explícita de patrones mal formateados o consecutivos (ej: .., ,,, .-)
        if (/[\.,\-]{2,}|[\.,]\-|\-[\.,]|\.,|,\./.test(valor)) {
            mostrarError(input, 'El precio contiene puntos, comas o guiones consecutivos o mal formateados (ej: .., ,,, .-).');
            return false;
        }

        // Detección explícita de signo negativo
        if (valor.includes('-')) {
            mostrarError(input, 'El precio no puede ser negativo ni contener el signo menos (-).');
            return false;
        }

        // Detección de puntos o comas (decimales no permitidos en CLP)
        if (valor.includes('.') || valor.includes(',')) {
            mostrarError(input, 'El sistema opera en CLP con precios enteros. No se permiten puntos (.) ni comas (,).');
            return false;
        }

        // Comprobación de formato numérico puro
        if (!REGEX_SOLO_DIGITOS.test(valor)) {
            mostrarError(input, 'El precio debe contener exclusivamente dígitos numéricos sin símbolos ni espacios.');
            return false;
        }

        const numero = parseInt(valor, 10);
        if (isNaN(numero) || numero <= 0) {
            mostrarError(input, 'El precio del producto debe ser un monto entero superior a $0 CLP.');
            return false;
        }

        limpiarError(input);
        return true;
    }

    /**
     * Valida el Stock:
     * - Obligatorio.
     * - Únicamente dígitos enteros (/^\d+$/).
     * - Rechaza explícitamente el signo negativo (-), puntos (.) y comas (,).
     * - Debe ser mayor o igual a 0 unidades.
     */
    function validarStock(input) {
        if (!input) return true;
        const valor = String(input.value).trim();

        if (valor.length === 0) {
            mostrarError(input, 'El stock es obligatorio.');
            return false;
        }

        // Detección explícita de patrones mal formateados o consecutivos (ej: .., ,,, .-)
        if (/[\.,\-]{2,}|[\.,]\-|\-[\.,]|\.,|,\./.test(valor)) {
            mostrarError(input, 'El stock contiene puntos, comas o guiones consecutivos o mal formateados (ej: .., ,,, .-).');
            return false;
        }

        if (valor.includes('-')) {
            mostrarError(input, 'El stock no puede ser un valor negativo ni contener el signo menos (-).');
            return false;
        }

        if (valor.includes('.') || valor.includes(',')) {
            mostrarError(input, 'El stock representa unidades enteras. No se admiten decimales, puntos (.) ni comas (,).');
            return false;
        }

        if (!REGEX_SOLO_DIGITOS.test(valor)) {
            mostrarError(input, 'El stock debe contener únicamente dígitos enteros.');
            return false;
        }

        const numero = parseInt(valor, 10);
        if (isNaN(numero) || numero < 0) {
            mostrarError(input, 'El stock debe ser un número entero mayor o igual a 0.');
            return false;
        }

        limpiarError(input);
        return true;
    }

    /**
     * Bloquea en tiempo real la pulsación de teclas no permitidas en campos numéricos enteros:
     * ., ,, -, +, e, E y espacios.
     */
    function configurarBloqueoTeclasNumericas(input) {
        if (!input) return;

        input.addEventListener('keydown', function (e) {
            const teclasProhibidas = ['.', ',', '-', '+', 'e', 'E', ' '];
            if (teclasProhibidas.includes(e.key)) {
                e.preventDefault();
                mostrarError(input, `La tecla '${e.key}' está bloqueada. Ingrese solo dígitos numéricos enteros positivos.`);
            }
        });

        // Evento input para interceptar pegado desde portapapeles o teclados móviles
        input.addEventListener('input', function () {
            const original = input.value;
            // Si el usuario pegó caracteres no numéricos como ., ,, -, letras
            if (/[^\d]/.test(original)) {
                input.value = original.replace(/\D/g, '');
                mostrarError(input, 'Se eliminaron automáticamente caracteres no numéricos (puntos, comas, signos o letras).');
            }
        });
    }

    /**
     * Inicializa los escuchadores de eventos en el formulario indicado.
     * Se defiende de la manipulación con DevTools validando estrictamente por código JavaScript.
     */
    function inicializarValidacionFormularioProducto(form) {
        if (!form || form.dataset.validadorActivo === 'true') return;
        form.dataset.validadorActivo = 'true';

        // Desactivar la validación HTML por defecto del navegador para garantizar
        // el control total por JavaScript ante manipulaciones con DevTools
        form.setAttribute('novalidate', 'true');

        const inputNombre = form.querySelector('[name="nombre"]');
        const inputDescripcion = form.querySelector('[name="descripcion"]');
        const inputCodigo = form.querySelector('[name="codigo"]');
        const inputPrecio = form.querySelector('[name="precio"]');
        const inputStock = form.querySelector('[name="stock"]');

        // Configurar bloqueos en tiempo real para Precio y Stock
        configurarBloqueoTeclasNumericas(inputPrecio);
        configurarBloqueoTeclasNumericas(inputStock);

        // Escuchadores en tiempo real (input y blur) para campos de texto
        if (inputNombre) {
            inputNombre.addEventListener('input', () => validarNombre(inputNombre));
            inputNombre.addEventListener('blur', () => validarNombre(inputNombre));
        }

        if (inputDescripcion) {
            inputDescripcion.addEventListener('input', () => validarDescripcion(inputDescripcion));
            inputDescripcion.addEventListener('blur', () => validarDescripcion(inputDescripcion));
        }

        if (inputCodigo) {
            inputCodigo.addEventListener('input', () => validarCodigo(inputCodigo));
            inputCodigo.addEventListener('blur', () => validarCodigo(inputCodigo));
        }

        if (inputPrecio) {
            inputPrecio.addEventListener('blur', () => validarPrecio(inputPrecio));
        }

        if (inputStock) {
            inputStock.addEventListener('blur', () => validarStock(inputStock));
        }

        // Intercepción estricta en el evento SUBMIT
        form.addEventListener('submit', function (evento) {
            // Protección activa contra manipulación en DevTools de method="POST" a "GET"
            const metodoActual = (form.getAttribute('method') || form.method || 'GET').toUpperCase();
            if (metodoActual !== 'POST') {
                evento.preventDefault();
                evento.stopPropagation();
                form.setAttribute('method', 'POST');
                form.method = 'POST';
                alert('Seguridad Safari: No se permite enviar formularios mediante GET para evitar exponer datos y campos en la barra de direcciones (URL). El formulario se restableció a POST.');
                return false;
            }

            let esFormularioValido = true;
            let primerElementoInvalido = null;

            // 1. Validar Nombre
            if (!validarNombre(inputNombre)) {
                esFormularioValido = false;
                if (!primerElementoInvalido) primerElementoInvalido = inputNombre;
            }

            // 2. Validar Descripción
            if (!validarDescripcion(inputDescripcion)) {
                esFormularioValido = false;
                if (!primerElementoInvalido) primerElementoInvalido = inputDescripcion;
            }

            // 3. Validar Código
            if (!validarCodigo(inputCodigo)) {
                esFormularioValido = false;
                if (!primerElementoInvalido) primerElementoInvalido = inputCodigo;
            }

            // 4. Validar Precio
            if (!validarPrecio(inputPrecio)) {
                esFormularioValido = false;
                if (!primerElementoInvalido) primerElementoInvalido = inputPrecio;
            }

            // 5. Validar Stock
            if (!validarStock(inputStock)) {
                esFormularioValido = false;
                if (!primerElementoInvalido) primerElementoInvalido = inputStock;
            }

            // Si alguna regla falló, bloquear el envío
            if (!esFormularioValido) {
                evento.preventDefault();
                evento.stopPropagation();

                if (primerElementoInvalido) {
                    primerElementoInvalido.focus();
                }
                return false;
            }

            return true;
        });
    }

    // Auto-registro en carga de página para todos los formularios de productos
    document.addEventListener('DOMContentLoaded', function () {
        const selectores = [
            '#formRegistrarProducto',
            '#formActualizarProducto',
            '#formProducto',
            'form[action*="/productos/guardar/"]',
            'form[action*="/stock/guardar/"]'
        ];

        selectores.forEach(selector => {
            document.querySelectorAll(selector).forEach(form => {
                inicializarValidacionFormularioProducto(form);
            });
        });
    });

    /**
     * Limpia todos los estilos de error y advertencias de un formulario.
     */
    function limpiarErroresFormulario(formulario) {
        if (!formulario) return;
        const formEl = typeof formulario === 'string' ? document.querySelector(formulario) : formulario;
        if (!formEl) return;

        formEl.querySelectorAll('.is-invalid, .is-valid').forEach(el => {
            el.classList.remove('is-invalid', 'is-valid');
        });
        formEl.querySelectorAll('.feedback-error-js').forEach(el => el.remove());
    }

    // Exponer la función de inicialización y limpieza en el ámbito global para modales o carga dinámica
    window.inicializarValidacionFormularioProducto = inicializarValidacionFormularioProducto;
    window.limpiarErroresFormulario = limpiarErroresFormulario;

})();
