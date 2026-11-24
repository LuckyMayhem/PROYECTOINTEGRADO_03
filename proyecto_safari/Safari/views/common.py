import re
from Safari.auth_utils import validar_texto_seguro

# Patrón para detectar intentos de inyección SQL o sintaxis maliciosa en parámetros
REGEX_INYECCION_SQL = re.compile(r"""['";]|--|/\*|\*/""")

# Patrón exhaustivo para secuencias de escape e inyección SQL defensiva (--, ;, /*, */, ' OR '1'='1', etc.)
REGEX_SQL_ESCAPE = re.compile(
    r"""(--|;|\/\*|\*\/|'\s*OR\s*['"]?1['"]?\s*=\s*['"]?1|"\s*OR\s*['"]?1['"]?\s*=\s*['"]?1|'\s*or\s+1\s*=\s*1|"\s*or\s+1\s*=\s*1)""",
    re.IGNORECASE
)

# Patrón para caracteres prohibidos en campos de texto (XSS / Inyecciones básicas)
REGEX_CARACTERES_PROHIBIDOS = re.compile(r"""[<>"'$;]|--|/\*|\*/""")

# Patrón numérico estricto: únicamente dígitos enteros positivos
REGEX_SOLO_DIGITOS = re.compile(r'^\d+$')

MAX_INTENTOS_LOGIN = 5
BLOQUEO_SEGUNDOS = 60


def sanitizar_cadena(valor, max_len=100):
    """Elimina caracteres nulos, caracteres de control y recorta la longitud para mitigar inyecciones y DoS."""
    if not isinstance(valor, str):
        return ""
    limpio = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', valor).strip()
    return limpio[:max_len]


def sanitizar_texto_defensivo(texto, max_len=150, nombre_campo='campo', requerido=False):
    """
    Sanitización estricta para inputs de texto contra inyección SQL y XSS:
    - Aplica .strip().
    - Valida contra longitud máxima permitida (max_len).
    - Rechaza de inmediato cualquier cadena que contenga símbolos peligrosos como:
      #, $, %, !, /, &, (, ), =, :, _, ;, ', ", -- o /* (así como <, >, \\, |, ^, ~, {, }, [, ]).
    - Si requerido=True, no permite cadenas vacías.
    Retorna (texto_limpio, es_valido, mensaje_error).
    """
    res = validar_texto_seguro(texto, nombre_campo=nombre_campo, requerido=requerido, max_len=max_len, permitir_guion_bajo=False)
    return res.texto_limpio, res.es_valido, res.mensaje


def validar_cantidad_entera(valor_raw, nombre_campo="cantidad", max_cant=50):
    """
    Inmunidad DevTools: Valida que la cantidad sea estrictamente un entero positivo mayor a 0:
    - Rechaza valores nulos, vacíos, negativos, decimales (con punto o coma) y strings no numéricos.
    - Rechaza cantidades mayores al límite permitido por línea de pedido (max_cant, por defecto 50 unidades).
    Retorna (cantidad, True, None) si es válido, o (None, False, mensaje_error).
    """
    if valor_raw is None:
        return None, False, f"El campo '{nombre_campo}' es obligatorio."
    val_str = str(valor_raw).strip()
    if not val_str:
        return None, False, f"El campo '{nombre_campo}' no puede estar vacío."
    if '-' in val_str:
        return None, False, f"El campo '{nombre_campo}' debe ser un número positivo mayor a 0 (no se permiten negativos)."
    if '.' in val_str or ',' in val_str:
        return None, False, f"El campo '{nombre_campo}' debe ser un número entero (no se permiten decimales)."
    if not REGEX_SOLO_DIGITOS.match(val_str):
        return None, False, f"El campo '{nombre_campo}' debe ser un número entero válido (sin letras ni caracteres especiales)."
    try:
        cant = int(val_str)
        if cant <= 0:
            return None, False, f"El campo '{nombre_campo}' debe ser mayor a 0."
        if max_cant is not None and cant > max_cant:
            return None, False, f"La cantidad máxima permitida por producto es de {max_cant} unidades."
        return cant, True, None
    except (ValueError, TypeError):
        return None, False, f"El campo '{nombre_campo}' contiene un valor numérico inválido."


def validar_parametro_get_seguro(valor, max_len=100, nombre_parametro='parámetro', permitir_guion_bajo=False):
    """
    Valida un parámetro individual recibido vía GET:
    - Aplica .strip().
    - Verifica que no exceda la longitud máxima permitida.
    - Rechaza caracteres y secuencias peligrosas contra inyección SQL y XSS (#, $, %, !, /, &, (, ), =, :, _, ;, ', ", --, /*).
    Retorna (valor_limpio, es_valido, mensaje_error).
    """
    res = validar_texto_seguro(valor, nombre_campo=nombre_parametro, requerido=False, max_len=max_len, permitir_guion_bajo=permitir_guion_bajo)
    return res.texto_limpio, res.es_valido, res.mensaje or ''


def verificar_peticion_get_segura(request, max_len=100):
    """
    Inspecciona todos los parámetros de la querystring (request.GET) antes de procesarlos.
    Si se detecta cualquier intento de inyección o parámetro malicioso con caracteres prohibidos
    (#, $, %, !, /, &, (, ), =, :, _, ;, ', ", --, /*), rechaza la solicitud de inmediato sin consultar la BD.
    Retorna (True, None) si todos los parámetros son seguros, o (False, error_response) si es maliciosa.
    """
    from .admin_panel import error_400_view
    for clave, valor in request.GET.items():
        clave_limpia = str(clave).strip()
        # Verificar la clave (se permite _ para nombres estándar como fecha_desde, fecha_hasta, usuario_id, etc.)
        res_clave = validar_texto_seguro(clave_limpia, nombre_campo="clave de parámetro", requerido=False, max_len=50, permitir_guion_bajo=True)
        if not res_clave.es_valido:
            return False, error_400_view(request, mensaje=f'Petición rechazada: {res_clave.mensaje}')

        permitir_guion_bajo_val = (clave_limpia in ['usuario_id', 'modulo', 'accion'])
        val_limpio, es_valido, msg_error = validar_parametro_get_seguro(
            valor,
            max_len=max_len,
            nombre_parametro=f'parámetro "{clave_limpia}"',
            permitir_guion_bajo=permitir_guion_bajo_val
        )
        if not es_valido:
            return False, error_400_view(request, mensaje=f'Petición rechazada: {msg_error}')
    return True, None


def validar_entero_estricto(valor_raw, nombre_campo="campo", permitir_cero=False, min_val=None, max_val=None):
    """
    Comprueba de forma segura que un valor sea estrictamente entero:
    - Rechaza letras, signos negativos (-), puntos (.) y comas (,).
    - Utiliza try/except ValueError para conversión segura.
    - Valida rango numérico min_val y max_val si se especifican.
    Retorna (entero, True, None) si es válido, o (None, False, mensaje_error).
    """
    if valor_raw is None:
        return None, False, f'El {nombre_campo} es obligatorio.'
    cadena = str(valor_raw).strip()
    if not cadena:
        return None, False, f'El {nombre_campo} no puede estar vacío.'
    
    if '-' in cadena:
        return None, False, f'El {nombre_campo} no puede ser un valor negativo.'
    if '.' in cadena or ',' in cadena:
        return None, False, f'El {nombre_campo} debe ser un número entero (no se permiten puntos ni comas).'
    if not REGEX_SOLO_DIGITOS.match(cadena):
        return None, False, f'El {nombre_campo} debe contener exclusivamente dígitos numéricos enteros (sin letras ni símbolos).'

    try:
        numero = int(cadena)
        if numero < 0 or (not permitir_cero and numero == 0):
            return None, False, f'El {nombre_campo} debe ser un número mayor a cero.'
        if min_val is not None and numero < min_val:
            return None, False, f'El {nombre_campo} debe ser un valor de al menos {min_val:,}.'
        if max_val is not None and numero > max_val:
            return None, False, f'El {nombre_campo} no puede exceder {max_val:,}.'
        return numero, True, None
    except (ValueError, TypeError):
        return None, False, f'El {nombre_campo} contiene un formato numérico no válido.'


