"""
auth_utils.py
Módulo de utilidades defensivas y sanitización contra inyecciones SQL y XSS.
Proporciona validación estricta de caracteres especiales para blindar todas las entradas del sistema.
"""

import re

# Patrón estricto de caracteres y secuencias peligrosas (Inyección SQL, XSS, scripts y comandos)
# Incluye: #, $, %, !, /, &, (, ), =, :, _, ;, ', ", --, /*, */, <, >, \, |, ^, ~, {, }, [, ]
REGEX_CARACTERES_PROHIBIDOS_ESTRICTO = re.compile(
    r"""[#$%\!/&()=:_;'"<>\\|^~{}[\]]|--|/\*|\*/"""
)

# Patrón idéntico pero que permite guión bajo (_) para identificadores de sistema (e.g. usernames)
REGEX_CARACTERES_PROHIBIDOS_IDENTIFICADOR = re.compile(
    r"""[#$%\!/&()=:;'"<>\\|^~{}[\]]|--|/\*|\*/"""
)

# Patrón exhaustivo para secuencias de escape SQL clásicas
REGEX_SQL_INJECTION = re.compile(
    r"""(--|;|\/\*|\*\/|'\s*OR\s*['"]?1['"]?\s*=\s*['"]?1|"\s*OR\s*['"]?1['"]?\s*=\s*['"]?1|'\s*or\s+1\s*=\s*1|"\s*or\s+1\s*=\s*1)""",
    re.IGNORECASE
)


class ResultadoValidacionTexto:
    """
    Objeto defensivo que encapsula el resultado de la validación.
    Es compatible tanto con evaluación booleana directa:
        if not validar_texto_seguro(valor): ...
    como con desempaquetado de tupla (compatibilidad estándar):
        es_valido, mensaje = validar_texto_seguro(valor)
    """
    def __init__(self, es_valido, mensaje=None, texto_limpio=""):
        self.es_valido = bool(es_valido)
        self.mensaje = mensaje
        self.texto_limpio = texto_limpio

    def __bool__(self):
        return self.es_valido

    def __iter__(self):
        yield self.es_valido
        yield self.mensaje

    def __getitem__(self, index):
        return (self.es_valido, self.mensaje)[index]

    def __len__(self):
        return 2

    def __repr__(self):
        return f"<ResultadoValidacionTexto valido={self.es_valido} mensaje={self.mensaje!r}>"

    def __str__(self):
        return self.mensaje or ("Válido" if self.es_valido else "Inválido")


def validar_texto_seguro(texto, nombre_campo="campo", requerido=False, max_len=250, permitir_guion_bajo=False):
    r"""
    Función utilitaria que valida rigurosamente cualquier entrada de texto contra inyección SQL y XSS:
    - Rechaza de inmediato cualquier cadena que contenga símbolos peligrosos:
      #, $, %, !, /, &, (, ), =, :, _, ;, ', ", -- o /* (así como <, >, \, |, ^, ~, {, }, [, ]).
    - Si permitir_guion_bajo=True (utilizado en identificadores como usernames preexistentes),
      permite el guión bajo pero mantiene bloqueados todos los demás caracteres peligrosos.
    - Rechaza nulos o cadenas vacías si requerido=True.
    - Valida que la longitud no supere max_len.
    - Retorna un ResultadoValidacionTexto que opera como booleano y como tupla (es_valido, mensaje_error).
    """
    if texto is None:
        if requerido:
            return ResultadoValidacionTexto(False, f"El campo '{nombre_campo}' es obligatorio.", "")
        return ResultadoValidacionTexto(True, None, "")

    cadena = str(texto).strip()

    if not cadena:
        if requerido:
            return ResultadoValidacionTexto(False, f"El campo '{nombre_campo}' no puede estar vacío.", "")
        return ResultadoValidacionTexto(True, None, "")

    if len(cadena) > max_len:
        return ResultadoValidacionTexto(
            False,
            f"El campo '{nombre_campo}' excede el límite máximo permitido de {max_len} caracteres.",
            cadena
        )

    # Selección del patrón regex según permiso de guión bajo
    regex_activo = REGEX_CARACTERES_PROHIBIDOS_IDENTIFICADOR if permitir_guion_bajo else REGEX_CARACTERES_PROHIBIDOS_ESTRICTO

    if regex_activo.search(cadena) or REGEX_SQL_INJECTION.search(cadena):
        return ResultadoValidacionTexto(
            False,
            f"El campo '{nombre_campo}' contiene caracteres especiales no permitidos (#, $, %, !, /, &, (, ), =, :, _, ;, ', \", --, /*).",
            cadena
        )

    return ResultadoValidacionTexto(True, None, cadena)
