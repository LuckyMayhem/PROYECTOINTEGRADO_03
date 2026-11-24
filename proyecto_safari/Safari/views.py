import re
import time
import json
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import JsonResponse, HttpResponseNotAllowed, Http404
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import DatabaseError
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib import messages
from django.db.models import Sum, Count, Avg, Q, DateField
from django.db.models.functions import Cast, Coalesce
from .models import (
    Usuario,
    Producto,
    Venta,
    DetalleVenta,
    Comanda,
    Mesa,
    ControlCaja,
    SecuenciaFolio,
    PuntoDeVenta,
    Menu,
    HistorialAccion,
    registrar_auditoria,
    obtener_siguiente_folio
)
from .auth_utils import (
    validar_texto_seguro,
    ResultadoValidacionTexto,
    REGEX_CARACTERES_PROHIBIDOS_ESTRICTO,
    REGEX_CARACTERES_PROHIBIDOS_IDENTIFICADOR,
    REGEX_SQL_INJECTION,
)


# ==============================================================================
# POLÍTICA DE SEGURIDAD DEFENSIVA Y BLINDAJE CONTRA INYECCIÓN SQL (OWASP A03:2021)
# ==============================================================================
# 1. Se utiliza exclusivamente el ORM de Django (.filter(), .get(), .create(), .update()),
#    garantizando consultas parametrizadas de manera nativa contra inyecciones SQL.
# 2. Queda estrictamente prohibida la concatenación de variables en consultas SQL en crudo
#    (ej: cursor.execute(f"SELECT ... WHERE id = {id}") o Model.objects.raw(f"... {id}")).
# 3. Blindaje de métodos HTTP: Toda operación de escritura/modificación exige POST.
#    Cualquier intento de alteración o envío por GET es rechazado con HTTP 405 / 400.
# 4. Inmunidad ante DevTools / Inspeccionar Elemento: Los precios, subtotales y totales
#    se calculan SIEMPRE en el servidor consultando el precio real de la BD (precio_bd * cantidad).
#    Nunca se confía en valores enviados desde el cliente ni inputs ocultos.
# ==============================================================================

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


def validar_cantidad_entera(valor_raw, nombre_campo="cantidad"):
    """
    Inmunidad DevTools: Valida que la cantidad sea estrictamente un entero positivo mayor a 0:
    - Rechaza valores nulos, vacíos, negativos, decimales (con punto o coma) y strings no numéricos.
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
        return cant, True, None
    except (ValueError, TypeError):
        return None, False, f"El campo '{nombre_campo}' contiene un valor numérico inválido."


def obtener_usuario(request):
    """Retorna los datos del usuario en sesión o None si no hay sesión."""
    u = request.session.get('usuario')
    if u and isinstance(u, dict) and 'id' in u:
        if 'usuario_id' not in request.session:
            request.session['usuario_id'] = u['id']
    return u


# ==============================================================================
# MANEJADORES PERSONALIZADOS DE ERRORES HTTP (OWASP / EXPERIENCIA DE USUARIO)
# ==============================================================================

def error_404_view(request, exception=None, mensaje=None):
    """Manejador global para error 404 (Página no encontrada / Problema de enrutamiento)."""
    return render(request, 'errors/404.html', {'mensaje': mensaje}, status=404)


def error_500_view(request, exception=None, mensaje=None):
    """Manejador global para error 500 (Error interno del servidor)."""
    return render(request, 'errors/500.html', {'mensaje': mensaje, 'exception': exception}, status=500)


def error_403_view(request, exception=None, mensaje=None):
    """Manejador global para error 403 (Acceso prohibido / Rol no autorizado)."""
    return render(request, 'errors/403.html', {'mensaje': mensaje}, status=403)


def error_400_view(request, exception=None, mensaje=None):
    """Manejador global para error 400 (Petición incorrecta / Datos no válidos)."""
    return render(request, 'errors/400.html', {'mensaje': mensaje}, status=400)


def error_401_view(request, mensaje=None):
    """Vista para error 401 (No autenticado / Requiere iniciar sesión)."""
    return render(request, 'errors/401.html', {'mensaje': mensaje}, status=401)


def error_502_view(request):
    """Vista de apoyo para error 502 (Bad Gateway)."""
    return render(request, 'errors/502.html', status=502)


def error_503_view(request):
    """Vista de apoyo para error 503 (Servicio no disponible / Mantenimiento)."""
    return render(request, 'errors/503.html', status=503)


def error_504_view(request):
    """Vista de apoyo para error 504 (Gateway Timeout)."""
    return render(request, 'errors/504.html', status=504)


# ==============================================================================
# VALIDACIÓN Y SANITIZACIÓN ROBUSTA DE PETICIONES GET Y POST
# ==============================================================================

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


def validar_entero_estricto(valor_raw, nombre_campo="campo", permitir_cero=False):
    """
    Comprueba de forma segura que un valor sea estrictamente entero:
    - Rechaza letras, signos negativos (-), puntos (.) y comas (,).
    - Utiliza try/except ValueError para conversión segura.
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
        return numero, True, None
    except (ValueError, TypeError):
        return None, False, f'El {nombre_campo} contiene un formato numérico no válido.'



# ==============================================================================
# 1. AUTENTICACIÓN
# ==============================================================================

def login_view(request):
    """
    Login individual con validación estricta y medidas de seguridad OWASP:
    - Validación y sanitización estricta de entradas (mitiga inyección y caracteres maliciosos).
    - Mitigación de ataques por fuerza bruta (bloqueo temporal tras 5 intentos fallidos y delay artificial).
    - Regeneración de ID de sesión para prevenir Session Fixation.
    """
    # 1. Verificación de bloqueo temporal por fuerza bruta
    bloqueado_hasta = request.session.get('login_bloqueado_hasta', 0)
    tiempo_actual = time.time()
    if tiempo_actual < bloqueado_hasta:
        segundos_restantes = max(1, int(bloqueado_hasta - tiempo_actual))
        return render(request, 'login.html', {
            'error': f'Acceso temporalmente bloqueado por demasiados intentos fallidos. Intente nuevamente en {segundos_restantes} segundos.'
        })

    # 2. Bloqueo estricto de envío de credenciales mediante GET para evitar exposición en URL
    # Si alguien cambia method="POST" a method="GET" desde Inspeccionar Elemento, se redirige limpio
    if 'username' in request.GET or 'password' in request.GET:
        return redirect('login')

    if request.method != 'POST':
        return render(request, 'login.html')

    raw_username = request.POST.get('username', '')
    raw_password = request.POST.get('password', '')

    # 3. Validación de campos obligatorios
    if not raw_username or not raw_password:
        return render(request, 'login.html', {'error': 'Debe ingresar tanto el usuario como la contraseña.'})

    # 4. Validación estricta de caracteres en el identificador y contraseña (previene XSS e inyecciones)
    res_u = validar_texto_seguro(raw_username, nombre_campo="usuario o correo", requerido=True, max_len=100, permitir_guion_bajo=True)
    if not res_u.es_valido:
        time.sleep(0.4)
        return render(request, 'login.html', {'error': res_u.mensaje})

    res_p = validar_texto_seguro(raw_password, nombre_campo="contraseña", requerido=True, max_len=128, permitir_guion_bajo=True)
    if not res_p.es_valido:
        time.sleep(0.4)
        return render(request, 'login.html', {'error': res_p.mensaje})

    # 5. Rechazo estricto de espacios en blanco en usuario o contraseña
    if ' ' in raw_username or any(c.isspace() for c in raw_username):
        time.sleep(0.3)
        return render(request, 'login.html', {'error': 'El usuario no puede contener espacios en blanco.'})

    if ' ' in raw_password or any(c.isspace() for c in raw_password):
        time.sleep(0.3)
        return render(request, 'login.html', {'error': 'La contraseña no puede contener espacios en blanco.'})

    # 6. Límites estrictos de longitud: Usuario (4 a 30 caracteres) y Contraseña (6 a 25 caracteres)
    if len(raw_username) < 4 or len(raw_username) > 30:
        time.sleep(0.3)
        return render(request, 'login.html', {'error': 'El usuario debe tener entre 4 y 30 caracteres.'})

    if len(raw_password) < 6 or len(raw_password) > 25:
        time.sleep(0.3)
        return render(request, 'login.html', {'error': 'La contraseña debe tener entre 6 y 25 caracteres.'})

    # 7. Sanitización básica con recorte de longitud máxima
    username = sanitizar_cadena(raw_username, max_len=30)
    password = sanitizar_cadena(raw_password, max_len=25)

    # 8. Consulta segura mediante ORM parametrizado (previene SQL Injection)
    usuario = Usuario.objects.filter(username=username, password=password).first()
    if not usuario:
        usuario = Usuario.objects.filter(correo=username, password=password).first()

    if usuario:
        # Verificar si la cuenta de usuario se encuentra activa
        if usuario.estado == 'inactivo':
            return render(request, 'login.html', {
                'error': 'Esta cuenta se encuentra inactiva. Por favor, comuníquese con el Administrador.'
            })

        # Login exitoso: limpiar contadores de fuerza bruta
        request.session['login_intentos'] = 0
        request.session.pop('login_bloqueado_hasta', None)

        # Regenerar ID de sesión para prevenir Session Fixation (OWASP)
        request.session.cycle_key()

        # Guardar en sesión
        request.session['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'username': usuario.username,
            'rol': usuario.rol,
        }
        request.session['usuario_id'] = usuario.id

        # Registro en la bitácora de auditoría
        registrar_auditoria(usuario, 'LOGIN', 'Autenticación', f"Inicio de sesión exitoso con rol '{usuario.rol}'")

        # Redirigir según el rol establecido en MySQL apuntando al name de la URL definida en urls.py
        if usuario.rol == 'administrador':
            return redirect('administrador')
        elif usuario.rol == 'cajero':
            return redirect('cajero')
        elif usuario.rol == 'mesero':
            return redirect('mesero')
        elif usuario.rol == 'cocinero':
            return redirect('cocinero')
        return redirect('login')
    else:
        # Mitigación contra fuerza bruta: conteo de intentos y retraso intencional
        intentos = request.session.get('login_intentos', 0) + 1
        request.session['login_intentos'] = intentos
        time.sleep(0.4) # Retardo intencional que ralentiza ataques automatizados

        if intentos >= MAX_INTENTOS_LOGIN:
            request.session['login_bloqueado_hasta'] = time.time() + BLOQUEO_SEGUNDOS
            return render(request, 'login.html', {
                'error': f'Límite de intentos excedido ({intentos}/{MAX_INTENTOS_LOGIN}). Acceso bloqueado por {BLOQUEO_SEGUNDOS} segundos.'
            })

        intentos_restantes = MAX_INTENTOS_LOGIN - intentos
        return render(request, 'login.html', {
            'error': f'Usuario o contraseña incorrectos. Le quedan {intentos_restantes} intento(s) antes del bloqueo temporal.'
        })


def logout_view(request):
    """Cierra la sesión y redirige al login."""
    request.session.flush()
    return redirect('login')


# ==============================================================================
# 2. MÓDULO DE CAJERO (POS TOUCH, VENTAS Y COMPROBANTE)
# ==============================================================================

def cajero_view(request):
    """Pantalla táctil POS para el cajero."""
    usuario = obtener_usuario(request)
    if not usuario:
        return error_401_view(request, mensaje='Se requiere iniciar sesión para acceder al módulo de Cajero.')
    if usuario.get('rol') not in ['cajero', 'administrador']:
        return error_403_view(request, mensaje=f'Acceso denegado: El usuario con rol "{usuario.get("rol")}" no tiene permisos para acceder al módulo de Cajero.')

    productos = Producto.objects.all().order_by('nombre')
    caja = ControlCaja.objects.filter(Q(abierta=True) | Q(estado='ABIERTA')).last()
    caja_abierta = bool(caja and caja.abierta and caja.estado == 'ABIERTA')

    # Métricas y arqueo del turno actual si la caja está abierta
    total_ventas_turno = Decimal('0.00')
    total_efectivo = Decimal('0.00')
    total_tarjeta = Decimal('0.00')
    total_transferencia = Decimal('0.00')
    efectivo_esperado = Decimal('0.00')

    if caja and caja.abierta and caja.estado == 'ABIERTA':
        ventas_turno = Venta.objects.filter(control_caja=caja)
        total_ventas_turno = ventas_turno.aggregate(s=Sum('total'))['s'] or Decimal('0.00')
        total_efectivo = ventas_turno.filter(metodo_pago='efectivo').aggregate(s=Sum('total'))['s'] or Decimal('0.00')
        total_tarjeta = ventas_turno.filter(metodo_pago='tarjeta').aggregate(s=Sum('total'))['s'] or Decimal('0.00')
        total_transferencia = ventas_turno.filter(metodo_pago='transferencia').aggregate(s=Sum('total'))['s'] or Decimal('0.00')
        efectivo_esperado = (caja.monto_inicial or Decimal('0.00')) + total_efectivo

    productos_data = [
        {
            'id': p.id,
            'nombre': p.nombre,
            'descripcion': p.descripcion,
            'precio': float(p.precio),
            'stock': p.stock,
            'categoria': p.categoria or 'General'
        }
        for p in productos
    ]

    cajeros = Usuario.objects.filter(rol__in=['cajero', 'administrador']).order_by('nombre')
    meseros = Usuario.objects.filter(rol='mesero').order_by('nombre')
    mesas = Mesa.objects.all().order_by('numero')

    # Identificar mesas con pedidos/cuentas pendientes (ocupadas o esperando cobro)
    mesas_con_cuenta = []
    mesas_query = Mesa.objects.filter(
        Q(estado__in=['ocupada', 'LISTO_PARA_COBRO', 'PENDIENTE_PAGO']) |
        Q(comandas__pagada=False)
    ).distinct().order_by('numero')

    for m in mesas_query:
        cmd = Comanda.objects.filter(Q(mesa_rel=m) | Q(mesa_rel_id=m.id), pagada=False).last()
        if not cmd:
            cmd = Comanda.objects.filter(mesa=m.nombre, pagada=False).last()
        if cmd:
            es_listo = (m.estado in ['LISTO_PARA_COBRO', 'PENDIENTE_PAGO'] or cmd.estado in ['LISTO_PARA_COBRO', 'PENDIENTE_PAGO'])
            mesas_con_cuenta.append({
                'mesa_id': m.id,
                'numero': m.numero,
                'nombre': m.nombre,
                'comanda_id': cmd.id,
                'folio': cmd.folio,
                'total': float(cmd.total),
                'notas': cmd.notas,
                'mesero': cmd.mesero.nombre if cmd.mesero else 'Garzón',
                'estado_comanda': cmd.estado,
                'estado_mesa': m.estado,
                'listo_para_cobro': es_listo
            })

    context = {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'productos': productos,
        'productos_json': json.dumps(productos_data),
        'caja': caja,
        'caja_abierta': caja_abierta,
        'cajeros': cajeros,
        'meseros': meseros,
        'mesas': mesas,
        'mesas_con_cuenta': mesas_con_cuenta,
        'total_ventas_turno': total_ventas_turno,
        'total_efectivo': total_efectivo,
        'total_tarjeta': total_tarjeta,
        'total_transferencia': total_transferencia,
        'efectivo_esperado': efectivo_esperado,
    }
    return render(request, 'cajero.html', context)


def cajero_registrar_venta(request):
    """
    Registra una venta desde la pantalla del cajero (Doble modalidad: Barra / Mesa):
    - Blindaje HTTP: Exige estrictamente POST (@require_POST defensivo). Rechaza GET con 405.
    - Inmunidad DevTools / Inspeccionar Elemento:
      * Busca siempre el producto en la BD por su ID primario y toma su precio real (precio_bd).
      * Multiplica precio_bd * cantidad en el servidor antes de guardar.
      * Valida que cantidad sea estrictamente entero positivo mayor a 0 (aborta si es negativo, decimal o string).
      * NUNCA confía en el total calculado enviado por el cliente ni inputs ocultos.
    - Mitigación SQL Injection: Sanitiza notas rechazando secuencias de escape (--, ;, /*, ' OR '1'='1').
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido. Se requiere POST.'}, status=405)

    usuario_sess = obtener_usuario(request)
    if not usuario_sess:
        return JsonResponse({'success': False, 'error': 'Sesión no válida'}, status=401)

    caja = ControlCaja.objects.filter(Q(abierta=True) & Q(estado='ABIERTA')).last()
    if not caja:
        return JsonResponse({
            'success': False,
            'error': 'Operación no permitida: La caja se encuentra CERRADA. Debe realizar la apertura obligatoria de jornada (con cajero responsable y fondo inicial) para emitir ventas.'
        }, status=400)

    try:
        data = json.loads(request.body)
        tipo_venta = data.get('tipo_venta', 'barra')

        # Si es liquidación de mesa previa, delegar a cajero_liquidar_mesa
        if tipo_venta == 'mesa' and (data.get('comanda_id') or (data.get('mesa_id') and Comanda.objects.filter(mesa_rel_id=data.get('mesa_id'), pagada=False).exists())):
            return cajero_liquidar_mesa(request)

        items = data.get('items', [])
        mesa = data.get('mesa', 'Barra')
        raw_notas = (data.get('notas') or data.get('comentarios') or '').strip()

        # Mitigación SQL Injection en notas de comanda
        notas, notas_validas, msg_notas = sanitizar_texto_defensivo(raw_notas, max_len=250, nombre_campo='notas de comanda')
        if not notas_validas:
            return JsonResponse({'success': False, 'error': f'Petición rechazada: {msg_notas}'}, status=400)

        metodo_pago = (data.get('metodo_pago') or 'efectivo').lower().strip()
        if metodo_pago not in ['efectivo', 'tarjeta', 'transferencia']:
            metodo_pago = 'efectivo'

        # Bloqueo Operativo: Comprobar que la caja del punto de venta esté ABIERTA
        punto_venta_id = data.get('punto_venta_id') or data.get('punto_de_venta_id')
        if punto_venta_id:
            caja_pv = ControlCaja.objects.filter(
                Q(punto_venta_id=punto_venta_id) | Q(punto_de_venta_id=punto_venta_id),
                Q(abierta=True) & Q(estado='ABIERTA')
            ).last()
            if not caja_pv:
                return JsonResponse({
                    'success': False,
                    'error': 'Operación no permitida: La caja del punto de venta no está ABIERTA.'
                }, status=400)
            caja = caja_pv

        mesero_id = data.get('mesero_id')
        mesero_obj = Usuario.objects.filter(id=mesero_id).first() if mesero_id else None

        mesa_id = data.get('mesa_id')
        mesa_obj = Mesa.objects.filter(id=mesa_id).first() if mesa_id else Mesa.objects.filter(nombre=mesa).first()

        if not items or not isinstance(items, list):
            return JsonResponse({'success': False, 'error': 'El carrito está vacío o el formato de ítems no es válido.'}, status=400)

        # Inmunidad ante DevTools / Inspeccionar Elemento:
        # 1. Validar rigurosamente que cada cantidad sea un entero positivo mayor a 0
        # 2. Consultar siempre el precio real directo del modelo Producto en la BD
        items_validados = []
        for item in items:
            if not isinstance(item, dict):
                return JsonResponse({'success': False, 'error': 'Formato de ítem no válido en el pedido.'}, status=400)

            prod_id_raw = item.get('id')
            prod_id, id_valido, _ = validar_entero_estricto(prod_id_raw, nombre_campo='ID de producto', permitir_cero=False)
            if not id_valido:
                return JsonResponse({'success': False, 'error': 'Identificador de producto inválido en el pedido.'}, status=400)

            raw_cant = item.get('cantidad')
            cant, cant_valida, msg_cant = validar_cantidad_entera(raw_cant, nombre_campo='cantidad')
            if not cant_valida:
                return JsonResponse({'success': False, 'error': f'Petición rechazada: {msg_cant}'}, status=400)

            prod = Producto.objects.filter(id=prod_id).first()
            if not prod:
                return JsonResponse({'success': False, 'error': f'Producto #{prod_id} no encontrado en la base de datos.'}, status=400)

            if prod.stock <= 0 or prod.stock < cant:
                return JsonResponse({
                    'success': False,
                    'error': f'Stock insuficiente para "{prod.nombre}". Solicitado: {cant}, disponible: {prod.stock}.'
                }, status=400)

            items_validados.append((prod, cant))

        # Re-validación estricta de inventario antes de descontar (protección contra condiciones de carrera concurrentes)
        for prod, cant in items_validados:
            prod.refresh_from_db()
            if prod.stock <= 0 or prod.stock < cant:
                return JsonResponse({
                    'success': False,
                    'error': f'Stock insuficiente para "{prod.nombre}". Solicitado: {cant}, disponible en inventario: {prod.stock}.'
                }, status=400)

        # Inmunidad DevTools: Multiplica precio_bd * cantidad en el servidor y recalcula total
        total_calculado = Decimal('0.00')
        detalle_texto = []
        productos_detalle = []
        items_limpios_json = []

        for prod, cant in items_validados:
            precio_bd = prod.precio  # Precio real directo del modelo Producto
            subtotal = Decimal(str(cant)) * precio_bd
            total_calculado += subtotal

            # Descontar stock verificado
            prod.stock = max(0, prod.stock - cant)
            prod.save()

            productos_detalle.append((prod, cant, subtotal))
            detalle_texto.append(f"{cant}x {prod.nombre} (${subtotal:,.0f})")
            items_limpios_json.append({'id': prod.id, 'nombre': prod.nombre, 'cantidad': cant, 'precio': float(precio_bd)})

        # Total recalculado 100% en el servidor (inmune a manipulación del cliente)
        total_final = total_calculado

        # 3. Crear Venta inmediata vinculada a la caja abierta (tipo_venta = 'barra')
        usuario_obj = Usuario.objects.filter(id=usuario_sess.get('id')).first()
        venta = Venta.objects.create(
            usuario=usuario_obj,
            mesero=mesero_obj,
            control_caja=caja,
            metodo_pago=metodo_pago,
            tipo_venta='barra',
            mesa=mesa_obj,
            notas=notas,
            total=total_final
        )

        for prod, cant, subtotal in productos_detalle:
            DetalleVenta.objects.create(
                venta=venta,
                producto=prod,
                cantidad=cant,
                subtotal=subtotal
            )

        # 4. Crear Comanda inmediata para Cocina con notas sanitizadas
        comanda = Comanda.objects.create(
            folio=venta.folio,
            mesa=mesa_obj.nombre if mesa_obj else mesa,
            mesa_rel=mesa_obj,
            mesero=usuario_obj,
            venta=venta,
            items=", ".join(detalle_texto),
            items_json=json.dumps(items_limpios_json),
            notas=notas,
            tipo_pedido='barra',
            pagada=True,
            total=total_final,
            estado='preparacion'
        )

        # 5. Registrar auditoría
        registrar_auditoria(
            usuario_obj,
            'CREAR',
            'Ventas',
            f"Venta en barra #{venta.id} ({venta.folio}) - Total: ${total_final:,.0f} CLP ({metodo_pago}) por {usuario_obj.nombre}"
        )

        return JsonResponse({
            'success': True,
            'folio': venta.folio,
            'total': float(total_final),
            'metodo_pago': metodo_pago,
            'tipo_venta': 'barra',
            'notas': notas,
            'message': f'Venta en barra registrada y boleta {venta.folio} emitida al instante.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def cajero_mesa_cuenta(request, mesa_id):
    """
    Retorna el detalle de la comanda activa y no pagada de una mesa física
    para que el cajero pueda visualizarla y liquidarla en su terminal.
    """
    usuario = obtener_usuario(request)
    if not usuario or usuario.get('rol') not in ['cajero', 'administrador']:
        return JsonResponse({'success': False, 'error': 'No autorizado'}, status=403)

    mesa = Mesa.objects.filter(id=mesa_id).first()
    if not mesa:
        return JsonResponse({'success': False, 'error': 'Mesa no encontrada'}, status=404)

    comanda = Comanda.objects.filter(mesa_rel=mesa, pagada=False).last()
    if not comanda:
        comanda = Comanda.objects.filter(mesa=mesa.nombre, pagada=False).last()

    if not comanda:
        return JsonResponse({'success': False, 'error': f'{mesa.nombre} no tiene pedidos pendientes de pago.'}, status=404)

    items_data = []
    try:
        raw_items = json.loads(comanda.items_json)
    except Exception:
        raw_items = []

    for it in raw_items:
        p = Producto.objects.filter(id=it.get('id')).first()
        if p:
            cant = int(it.get('cantidad', 1))
            items_data.append({
                'id': p.id,
                'nombre': p.nombre,
                'precio': float(p.precio),
                'cantidad': cant,
                'subtotal': float(p.precio * cant),
                'stock': p.stock
            })

    es_listo = (mesa.estado in ['LISTO_PARA_COBRO', 'PENDIENTE_PAGO'] or comanda.estado in ['LISTO_PARA_COBRO', 'PENDIENTE_PAGO'])

    return JsonResponse({
        'success': True,
        'comanda_id': comanda.id,
        'folio': comanda.folio,
        'mesa_id': mesa.id,
        'mesa_nombre': mesa.nombre,
        'mesero': comanda.mesero.nombre if comanda.mesero else 'Garzón',
        'mesero_id': comanda.mesero.id if comanda.mesero else None,
        'notas': comanda.notas,
        'items': items_data,
        'items_texto': comanda.items,
        'total': float(comanda.total),
        'estado_comanda': comanda.estado,
        'estado_mesa': mesa.estado,
        'listo_para_cobro': es_listo
    })


def cajero_liquidar_mesa(request):
    """
    Liquidación de Mesa en Terminal de Caja:
    - Blindaje de método HTTP: Exige estrictamente POST. Rechaza GET u otros con 405.
    - Inmunidad DevTools / Inspeccionar Elemento:
      * Recalcula el total directamente en el backend multiplicando precio_bd * cantidad por cada producto.
      * Valida cantidad como entero positivo mayor a 0 con validar_cantidad_entera.
      * NUNCA confía en montos o totales calculados en cliente ni inputs ocultos.
    - Valida que la caja esté ABIERTA.
    - Descuenta stock de inventario de forma segura.
    - Emite la boleta correlativa (BOL-XXXX) y asocia la venta a la caja activa.
    - Marca la comanda como pagada y desocupa la mesa física ('desocupada').
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido. Se requiere POST.'}, status=405)

    usuario = obtener_usuario(request)
    if not usuario or usuario.get('rol') not in ['cajero', 'administrador']:
        return JsonResponse({'success': False, 'error': 'No autorizado para liquidar mesas.'}, status=403)

    caja = ControlCaja.objects.filter(Q(abierta=True) & Q(estado='ABIERTA')).last()
    if not caja:
        return JsonResponse({
            'success': False,
            'error': 'Operación no permitida: La caja se encuentra CERRADA. Debe realizar la apertura de jornada para liquidar mesas.'
        }, status=400)

    try:
        data = json.loads(request.body)
        mesa_id = data.get('mesa_id')
        comanda_id = data.get('comanda_id')
        metodo_pago = (data.get('metodo_pago') or 'efectivo').lower().strip()
        if metodo_pago not in ['efectivo', 'tarjeta', 'transferencia']:
            metodo_pago = 'efectivo'

        comanda = None
        if comanda_id:
            comanda = Comanda.objects.filter(id=comanda_id, pagada=False).first()
        if not comanda and mesa_id:
            comanda = Comanda.objects.filter(mesa_rel_id=mesa_id, pagada=False).last()
            if not comanda:
                mesa_obj = Mesa.objects.filter(id=mesa_id).first()
                if mesa_obj:
                    comanda = Comanda.objects.filter(mesa=mesa_obj.nombre, pagada=False).last()

        if not comanda:
            return JsonResponse({'success': False, 'error': 'No se encontró un pedido activo pendiente de liquidar para esta mesa.'}, status=400)

        mesa = comanda.mesa_rel

        # Parsear ítems de la comanda
        try:
            items = json.loads(comanda.items_json)
        except Exception:
            items = []

        if not items:
            return JsonResponse({'success': False, 'error': 'La comanda no tiene ítems válidos para liquidar.'}, status=400)

        # 1. Validar cantidades e inmunidad ante DevTools: Recalcular precio_bd * cantidad en servidor
        productos_detalle = []
        total_calculado = Decimal('0.00')

        for item in items:
            prod_id = item.get('id')
            cant_raw = item.get('cantidad', 1)
            cant, cant_valida, msg_cant = validar_cantidad_entera(cant_raw, nombre_campo="cantidad")
            if not cant_valida:
                return JsonResponse({'success': False, 'error': f'Petición rechazada: {msg_cant}'}, status=400)

            prod = Producto.objects.filter(id=prod_id).first()
            if not prod:
                return JsonResponse({'success': False, 'error': f'Producto #{prod_id} de la orden no encontrado en la base de datos.'}, status=400)

            prod.refresh_from_db()
            if prod.stock <= 0 or prod.stock < cant:
                return JsonResponse({
                    'success': False,
                    'error': f'Stock insuficiente para liquidar "{prod.nombre}". Solicitado: {cant}, disponible en inventario: {prod.stock}.'
                }, status=400)

            subtotal = Decimal(str(cant)) * prod.precio
            total_calculado += subtotal

            # Descontar stock
            prod.stock = max(0, prod.stock - cant)
            prod.save()

            productos_detalle.append((prod, cant, subtotal))

        # Total 100% verificado y recalculado en servidor
        total_final = total_calculado

        # 2. Crear Venta oficial vinculada a la caja abierta
        usuario_obj = Usuario.objects.filter(id=usuario.get('id')).first()
        venta = Venta.objects.create(
            usuario=usuario_obj,
            mesero=comanda.mesero,
            control_caja=caja,
            metodo_pago=metodo_pago,
            tipo_venta='mesa',
            mesa=mesa,
            notas=comanda.notas,
            total=total_final
        )

        for prod, cant, subtotal in productos_detalle:
            DetalleVenta.objects.create(
                venta=venta,
                producto=prod,
                cantidad=cant,
                subtotal=subtotal
            )

        # 3. Vincular y marcar comanda como pagada y actualizar total final recalculado
        comanda.total = total_final
        comanda.pagada = True
        comanda.venta = venta
        comanda.save()

        # Marcar todas las comandas pendientes de esta mesa como pagadas vinculadas a la venta
        if mesa:
            Comanda.objects.filter(Q(mesa_rel=mesa) | Q(mesa_rel_id=mesa.id), pagada=False).update(pagada=True, venta=venta)

        # 4. Desocupar la mesa física
        if mesa:
            mesa.estado = 'desocupada'
            mesa.comida_entregada = False
            mesa.save()

        # 5. Registro en auditoría
        registrar_auditoria(
            usuario_obj,
            'CREAR',
            'Ventas',
            f"Liquidación de {comanda.mesa} - Boleta {venta.folio} emitida por ${venta.total:,.0f} CLP ({metodo_pago}) - Cajero: {usuario_obj.nombre}"
        )

        return JsonResponse({
            'success': True,
            'folio': venta.folio,
            'tipo_venta': 'mesa',
            'mesa': comanda.mesa,
            'mesa_id': mesa.id if mesa else None,
            'total': float(venta.total),
            'metodo_pago': metodo_pago,
            'notas': comanda.notas,
            'message': f'Mesa {comanda.mesa} liquidada exitosamente. Boleta {venta.folio} emitida.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def api_mesas_con_cuenta(request):
    """Retorna la lista de mesas ocupadas o listas para cobro con pedidos activos para la terminal de caja."""
    usuario = obtener_usuario(request)
    if not usuario or usuario.get('rol') not in ['cajero', 'administrador']:
        return JsonResponse({'success': False, 'error': 'No autorizado'}, status=403)

    mesas_data = []
    mesas_query = Mesa.objects.filter(
        Q(estado__in=['ocupada', 'LISTO_PARA_COBRO', 'PENDIENTE_PAGO']) |
        Q(comandas__pagada=False)
    ).distinct().order_by('numero')

    for m in mesas_query:
        cmd = Comanda.objects.filter(Q(mesa_rel=m) | Q(mesa_rel_id=m.id), pagada=False).last()
        if not cmd:
            cmd = Comanda.objects.filter(mesa=m.nombre, pagada=False).last()
        if cmd:
            es_listo = (m.estado in ['LISTO_PARA_COBRO', 'PENDIENTE_PAGO'] or cmd.estado in ['LISTO_PARA_COBRO', 'PENDIENTE_PAGO'])
            mesas_data.append({
                'mesa_id': m.id,
                'numero': m.numero,
                'nombre': m.nombre,
                'comanda_id': cmd.id,
                'folio': cmd.folio,
                'total': float(cmd.total),
                'notas': cmd.notas,
                'mesero': cmd.mesero.nombre if cmd.mesero else 'Garzón',
                'estado_comanda': cmd.estado,
                'estado_mesa': m.estado,
                'listo_para_cobro': es_listo
            })

    return JsonResponse({'success': True, 'mesas': mesas_data})


# ==============================================================================
# 3. MÓDULO DE MESERO (TOMA DE PEDIDOS, MESAS Y ENTREGA DE COMIDA)
# ==============================================================================

def mesero_view(request):
    """Módulo de salón para el mesero."""
    usuario = obtener_usuario(request)
    if not usuario:
        return error_401_view(request, mensaje='Se requiere iniciar sesión para acceder al módulo de Mesero.')
    if usuario.get('rol') not in ['mesero', 'administrador']:
        return error_403_view(request, mensaje=f'Acceso denegado: El usuario con rol "{usuario.get("rol")}" no tiene permisos para acceder al módulo de Mesero.')

    mesas = Mesa.objects.all().order_by('numero')
    productos = Producto.objects.filter(stock__gt=0).order_by('nombre')
    productos_data = [
        {
            'id': p.id,
            'nombre': p.nombre,
            'descripcion': p.descripcion,
            'precio': float(p.precio),
            'stock': p.stock,
            'categoria': p.categoria or 'General'
        }
        for p in productos
    ]

    # Comandas activas por mesa
    comandas_por_mesa = {}
    for m in mesas:
        cmd = Comanda.objects.filter(Q(mesa_rel=m) | Q(mesa_rel_id=m.id), pagada=False).last()
        if not cmd:
            cmd = Comanda.objects.filter(mesa=m.nombre, pagada=False).last()
        if cmd:
            es_listo = (m.estado in ['LISTO_PARA_COBRO', 'PENDIENTE_PAGO'] or cmd.estado in ['LISTO_PARA_COBRO', 'PENDIENTE_PAGO'])
            comandas_por_mesa[m.id] = {
                'id': cmd.id,
                'folio': cmd.folio,
                'total': float(cmd.total),
                'estado': cmd.estado,
                'notas': cmd.notas,
                'items': cmd.items,
                'listo_para_cobro': es_listo
            }

    context = {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'mesas': mesas,
        'productos': productos,
        'productos_json': json.dumps(productos_data),
        'comandas_activas': comandas_por_mesa
    }
    return render(request, 'mesero.html', context)


def mesero_tomar_pedido(request):
    """
    Toma de Pedido de Garzón / Mesero:
    - Blindaje de método HTTP: Exige estrictamente POST. Rechaza GET u otros con 405.
    - Inmunidad DevTools / Inspeccionar Elemento:
      * Busca los productos en BD por su ID primario y toma su precio real (precio_bd).
      * Valida cantidad como entero positivo mayor a 0 con validar_cantidad_entera (rechaza negativos, decimales y strings).
      * Recalcula subtotal (precio_bd * cant) y total en el servidor.
    - Mitigación SQL Injection: Sanitiza notas y comentarios rechazando secuencias de escape (--, ;, /*, ' OR '1'='1').
    - El mesero selecciona la mesa física (pasa a estado 'OCUPADA').
    - Carga los productos y notas para cocina.
    - Genera la comanda hacia la cocina con estado 'EN ESPERA'.
    - La boleta NO se emite en este momento (se emitirá cuando el cliente pida la cuenta y el cajero liquide la mesa).
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido. Se requiere POST.'}, status=405)

    usuario = obtener_usuario(request)
    if not usuario:
        return JsonResponse({'success': False, 'error': 'Sesión no válida'}, status=401)
    if usuario.get('rol') not in ['mesero', 'administrador']:
        return JsonResponse({'success': False, 'error': 'No autorizado para tomar pedidos de mesero.'}, status=403)

    try:
        data = json.loads(request.body)
        mesa_id = data.get('mesa_id')
        items = data.get('items', [])
        raw_notas = (data.get('notas') or data.get('comentarios') or '').strip()

        # Mitigación SQL Injection en notas de comanda
        notas, notas_validas, msg_notas = sanitizar_texto_defensivo(raw_notas, max_len=250, nombre_campo='notas de comanda')
        if not notas_validas:
            return JsonResponse({'success': False, 'error': f'Petición rechazada: {msg_notas}'}, status=400)

        mesa = Mesa.objects.filter(id=mesa_id).first()
        if not mesa:
            mesa = Mesa.objects.filter(numero=mesa_id).first()
        if not mesa:
            return JsonResponse({'success': False, 'error': 'Mesa física no encontrada.'}, status=404)

        # Bloqueo estricto: Si la mesa está esperando liquidación en caja, rechazar nuevos pedidos
        if mesa.estado in ['LISTO_PARA_COBRO', 'PENDIENTE_PAGO']:
            return JsonResponse({
                'success': False,
                'error': 'Operación no permitida: La mesa se encuentra en estado LISTO_PARA_COBRO esperando liquidación en caja. No es posible agregar más productos.'
            }, status=400)

        if not items or not isinstance(items, list):
            return JsonResponse({'success': False, 'error': 'Debe seleccionar al menos un producto para el pedido.'}, status=400)

        # Inmunidad ante DevTools / Inspeccionar Elemento:
        # 1. Validar rigurosamente que cada cantidad sea un entero positivo mayor a 0
        # 2. Consultar siempre el precio real directo del modelo Producto en la BD
        detalle_texto = []
        total_calculado = Decimal('0.00')
        items_limpios = []

        for item in items:
            if not isinstance(item, dict):
                return JsonResponse({'success': False, 'error': 'Formato de ítem no válido en el pedido.'}, status=400)

            prod_id_raw = item.get('id')
            prod_id, id_valido, _ = validar_entero_estricto(prod_id_raw, nombre_campo='ID de producto', permitir_cero=False)
            if not id_valido:
                return JsonResponse({'success': False, 'error': 'Identificador de producto inválido en el pedido.'}, status=400)

            raw_cant = item.get('cantidad')
            cant, cant_valida, msg_cant = validar_cantidad_entera(raw_cant, nombre_campo='cantidad')
            if not cant_valida:
                return JsonResponse({'success': False, 'error': f'Petición rechazada: {msg_cant}'}, status=400)

            prod = Producto.objects.filter(id=prod_id).first()
            if not prod:
                return JsonResponse({'success': False, 'error': f'Producto #{prod_id} no encontrado en la base de datos.'}, status=400)

            prod.refresh_from_db()
            if prod.stock <= 0 or prod.stock < cant:
                return JsonResponse({
                    'success': False,
                    'error': f'Stock insuficiente para "{prod.nombre}". Solicitado: {cant}, disponible: {prod.stock}.'
                }, status=400)

            precio_bd = prod.precio
            subtotal = Decimal(str(cant)) * precio_bd
            total_calculado += subtotal

            detalle_texto.append(f"{cant}x {prod.nombre} (${subtotal:,.0f})")
            items_limpios.append({'id': prod.id, 'nombre': prod.nombre, 'cantidad': cant, 'precio': float(precio_bd)})

        # 1. Mesa pasa a estado 'ocupada'
        mesa.estado = 'ocupada'
        mesa.comida_entregada = False
        mesa.save()

        usuario_obj = Usuario.objects.filter(id=usuario.get('id')).first()

        # 2. Aislamiento estricto por Mesa:
        # Si la mesa ya tiene una comanda activa no pagada, consolidar productos de esa misma sesión de mesa
        comanda_activa = Comanda.objects.filter(Q(mesa_rel=mesa) | Q(mesa_rel_id=mesa.id), pagada=False).last()
        if not comanda_activa:
            comanda_activa = Comanda.objects.filter(mesa=mesa.nombre, pagada=False).last()

        if comanda_activa:
            try:
                items_existentes = json.loads(comanda_activa.items_json)
            except Exception:
                items_existentes = []

            dict_items = {it['id']: it for it in items_existentes if isinstance(it, dict) and 'id' in it}
            for il in items_limpios:
                pid = il['id']
                if pid in dict_items:
                    dict_items[pid]['cantidad'] += il['cantidad']
                else:
                    dict_items[pid] = il

            items_unificados = list(dict_items.values())
            comanda_activa.items_json = json.dumps(items_unificados)
            comanda_activa.items = f"{comanda_activa.items}, {', '.join(detalle_texto)}"
            comanda_activa.total = sum(Decimal(str(it['cantidad'])) * Decimal(str(it['precio'])) for it in items_unificados)
            if notas:
                comanda_activa.notas = f"{comanda_activa.notas} | {notas}" if comanda_activa.notas else notas
            comanda_activa.mesa_rel = mesa
            comanda_activa.mesa = mesa.nombre
            comanda_activa.tipo_pedido = 'mesa'
            comanda_activa.estado = 'en_espera'
            comanda_activa.save()
            comanda = comanda_activa
            total_calculado = comanda.total
            folio = comanda.folio
        else:
            # Generar folio correlativo para nueva comanda
            folio = obtener_siguiente_folio('comanda')
            comanda = Comanda.objects.create(
                folio=folio,
                mesa=mesa.nombre,
                mesa_rel=mesa,
                mesero=usuario_obj,
                items=", ".join(detalle_texto),
                items_json=json.dumps(items_limpios),
                notas=notas,
                tipo_pedido='mesa',
                pagada=False,
                total=total_calculado,
                estado='en_espera'  # Estado EN ESPERA hacia cocina
            )

        # 4. Registrar auditoría
        registrar_auditoria(
            usuario_obj,
            'CREAR',
            'Comandas',
            f"Pedido de salón para {mesa.nombre} - Comanda {folio} (EN ESPERA) - Total: ${total_calculado:,.0f} CLP - Mesero: {usuario_obj.nombre}"
        )

        return JsonResponse({
            'success': True,
            'comanda_id': comanda.id,
            'folio': comanda.folio,
            'mesa_id': mesa.id,
            'mesa_nombre': mesa.nombre,
            'mesa_estado': mesa.estado,
            'estado': comanda.estado,
            'total': float(total_calculado),
            'notas': comanda.notas,
            'message': f'Comanda {folio} enviada a cocina en estado EN ESPERA. Mesa {mesa.nombre} pasa a estado OCUPADA.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def mesero_solicitar_cuenta(request):
    """
    Finaliza la atención de una mesa y solicita la cuenta al cajero (Botón 'Finalizar Venta / Solicitar Cuenta'):
    - Blindaje de método: Exige estrictamente POST. Rechaza GET u otros con 405.
    - Valida que el usuario tenga rol 'mesero' o 'administrador'.
    - Transiciona la mesa y sus comandas activas a estado 'LISTO_PARA_COBRO'.
    - Bloquea que se sigan agregando platos por error a esta mesa.
    - Libera la vista operativa del mesero para esa mesa.
    - Deja la mesa lista en el terminal del Cajero para emitir la boleta y cobrar.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido. Se requiere POST.'}, status=405)

    usuario = obtener_usuario(request)
    if not usuario:
        return JsonResponse({'success': False, 'error': 'Sesión no válida'}, status=401)
    if usuario.get('rol') not in ['mesero', 'administrador']:
        return JsonResponse({'success': False, 'error': 'No autorizado para solicitar cuenta de mesa.'}, status=403)

    try:
        data = json.loads(request.body)
        mesa_id = data.get('mesa_id')
        if not mesa_id:
            return JsonResponse({'success': False, 'error': 'Identificador de mesa no proporcionado.'}, status=400)

        mesa = Mesa.objects.filter(id=mesa_id).first()
        if not mesa:
            mesa = Mesa.objects.filter(numero=mesa_id).first()
        if not mesa:
            return JsonResponse({'success': False, 'error': 'Mesa no encontrada.'}, status=404)

        comandas = Comanda.objects.filter(Q(mesa_rel=mesa) | Q(mesa_rel_id=mesa.id), pagada=False)
        if not comandas.exists():
            comandas = Comanda.objects.filter(mesa=mesa.nombre, pagada=False)

        if not comandas.exists() and mesa.estado not in ['ocupada', 'LISTO_PARA_COBRO']:
            return JsonResponse({
                'success': False,
                'error': f'La {mesa.nombre} no tiene pedidos activos para solicitar cuenta.'
            }, status=400)

        # Transición a estado LISTO_PARA_COBRO
        mesa.estado = 'LISTO_PARA_COBRO'
        mesa.save()

        for cmd in comandas:
            cmd.estado = 'LISTO_PARA_COBRO'
            cmd.save()

        usuario_obj = Usuario.objects.filter(id=usuario.get('id')).first()
        registrar_auditoria(
            usuario_obj,
            'ACTUALIZAR',
            'Mesas',
            f"Mesa {mesa.nombre} pasó a estado LISTO_PARA_COBRO. Cuenta solicitada por {usuario_obj.nombre if usuario_obj else 'Mesero'} para liquidación en caja."
        )

        return JsonResponse({
            'success': True,
            'mesa_id': mesa.id,
            'mesa_nombre': mesa.nombre,
            'mesa_estado': 'LISTO_PARA_COBRO',
            'estado': 'LISTO_PARA_COBRO',
            'message': f'Cuenta solicitada para {mesa.nombre}. Pedido en estado LISTO_PARA_COBRO listo para cobro en caja.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def mesero_cambiar_mesa(request):
    """
    Alterna estado de la mesa (ocupada/desocupada) o la entrega de comida.
    Blindaje de método: Requiere estrictamente POST.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido. Se requiere POST.'}, status=405)

    usuario = obtener_usuario(request)
    if not usuario or usuario.get('rol') not in ['mesero', 'administrador']:
        return JsonResponse({'success': False, 'error': 'No autorizado'}, status=403)

    try:
        data = json.loads(request.body)
        mesa_id = data.get('mesa_id')
        accion = data.get('accion')  # 'toggle_ocupada' o 'toggle_comida'

        mesa = Mesa.objects.filter(id=mesa_id).first()
        if mesa:
            if accion == 'toggle_ocupada':
                mesa.estado = 'desocupada' if mesa.estado == 'ocupada' else 'ocupada'
                if mesa.estado == 'desocupada':
                    mesa.comida_entregada = False
            elif accion == 'toggle_comida':
                mesa.comida_entregada = not mesa.comida_entregada
            mesa.save()
            return JsonResponse({'success': True, 'estado': mesa.estado, 'comida_entregada': mesa.comida_entregada})

        return JsonResponse({'success': False, 'error': 'Mesa no encontrada'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==============================================================================
# 4. MÓDULO DE COCINERO (COMANDAS, FLUJO OPERATIVO Y RE-ORDEN / RE-EMISIÓN)
# ==============================================================================

def cocinero_view(request):
    """
    Monitor de cocina para el cocinero y administrador:
    - Comandas regulares en cola: 'en_espera', 'preparacion', 'listo'.
    - Sección Prioritaria de RE_ORDEN: Órdenes re-emitidas para cambios o recalentados.
    - Historial de pedidos entregados con botón 'Re-hacer / Re-orden'.
    """
    usuario = obtener_usuario(request)
    if not usuario:
        return error_401_view(request, mensaje='Se requiere iniciar sesión para acceder al monitor de Cocina.')
    if usuario.get('rol') not in ['cocinero', 'administrador']:
        return error_403_view(request, mensaje=f'Acceso denegado: El usuario con rol "{usuario.get("rol")}" no tiene permisos para acceder a la Cocina.')

    # Preservar y restaurar la pestaña activa (desde GET o sesión)
    tab_activa = (request.GET.get('tab') or request.session.get('tab_cocina_activa') or 'en_espera').strip().lower()
    if tab_activa not in ['en_espera', 'preparacion', 'listo', 'entregado', 'recocinando']:
        tab_activa = 'en_espera'
    request.session['tab_cocina_activa'] = tab_activa

    # 1. Re-órdenes prioritarias activas (cambios / recalentados)
    comandas_reorden = Comanda.objects.filter(
        Q(estado__in=['RE_ORDEN', 're_orden']) | Q(es_reemision=True, estado__in=['RE_ORDEN', 're_orden', 'preparacion', 'PREPARANDO', 'en_espera'])
    ).order_by('fecha')

    # 2. Cola regular activa de preparación (separada visualmente de las re-órdenes)
    comandas_regulares = Comanda.objects.filter(
        estado__in=['en_espera', 'EN ESPERA', 'preparacion', 'PREPARANDO', 'listo', 'LISTO']
    ).exclude(
        id__in=comandas_reorden.values_list('id', flat=True)
    ).order_by('fecha')

    # Desglose por estados operativos para la navegación de pestañas Chrome
    comandas_en_espera = comandas_regulares.filter(estado__in=['en_espera', 'EN ESPERA'])
    comandas_preparacion = comandas_regulares.filter(estado__in=['preparacion', 'PREPARANDO'])
    comandas_listo = comandas_regulares.filter(estado__in=['listo', 'LISTO'])

    # 3. Pedidos entregados recientemente con opción de re-emisión
    entregados_recientes = Comanda.objects.filter(
        estado__in=['entregado', 'ENTREGADO']
    ).exclude(
        id__in=comandas_reorden.values_list('id', flat=True)
    ).order_by('-fecha')[:30]

    context = {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'tab_activa': tab_activa,
        'comandas': comandas_regulares,
        'comandas_reorden': comandas_reorden,
        'entregados_recientes': entregados_recientes,
        'comandas_en_espera': comandas_en_espera,
        'comandas_preparacion': comandas_preparacion,
        'comandas_listo': comandas_listo,
        'comandas_entregado': entregados_recientes,
        'count_en_espera': comandas_en_espera.count(),
        'count_preparacion': comandas_preparacion.count(),
        'count_listo': comandas_listo.count(),
        'count_entregado': entregados_recientes.count(),
        'count_recocinando': comandas_reorden.count(),
    }
    return render(request, 'cocinero.html', context)


def cocina_reorden(request):
    """
    Flujo de re-emisión de platillos para cambios o recalentados:
    - Blindaje de método HTTP: Exige estrictamente POST. Rechaza GET u otros con 405.
    - Mitigación SQL Injection: Sanitiza motivo rechazando secuencias de escape (--, ;, /*, ' OR '1'='1').
    - Visible para cocina o garzón (roles: cocinero, mesero, administrador).
    - Al pulsar 'Re-hacer', la orden pasa al estado 'RE_ORDEN', se activa es_reemision = True
      y regresa a la cola activa de preparación en cocina con alerta visual prioritaria.
    - Registra la acción en HistorialAccion indicando qué usuario solicitó re-hacer la comanda.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido. Se requiere POST.'}, status=405)

    usuario = obtener_usuario(request)
    if not usuario or usuario.get('rol') not in ['cocinero', 'mesero', 'administrador']:
        return JsonResponse({'success': False, 'error': 'No autorizado para solicitar re-emisión de comandas.'}, status=403)

    try:
        data = json.loads(request.body)
        comanda_id = data.get('comanda_id')
        raw_motivo = (data.get('motivo') or data.get('motivo_reemision') or '').strip()

        # Mitigación SQL Injection en motivo
        motivo, motivo_valido, msg_motivo = sanitizar_texto_defensivo(raw_motivo, max_len=150, nombre_campo='motivo de re-orden')
        if not motivo_valido:
            return JsonResponse({'success': False, 'error': f'Petición rechazada: {msg_motivo}'}, status=400)

        if not comanda_id:
            return JsonResponse({'success': False, 'error': 'Debe especificar el ID de la comanda a re-hacer.'}, status=400)

        comanda = Comanda.objects.filter(id=comanda_id).first()
        if not comanda:
            return JsonResponse({'success': False, 'error': 'Comanda no encontrada.'}, status=404)

        # Actualizar estado a RE_ORDEN y activar bandera de re-emisión
        comanda.estado = 'RE_ORDEN'
        comanda.es_reemision = True
        comanda.motivo_reemision = motivo if motivo else 'Solicitud de re-orden / cambio de platillo'
        comanda.save()

        # Si la mesa física asociada estaba marcada como entregada, reactivar espera
        if comanda.mesa_rel:
            comanda.mesa_rel.comida_entregada = False
            comanda.mesa_rel.save()

        # Registrar en HistorialAccion
        usuario_obj = Usuario.objects.filter(id=usuario.get('id')).first()
        registrar_auditoria(
            usuario_obj,
            'RE_ORDEN',
            'Cocina',
            f"Re-emisión de comanda {comanda.folio} ({comanda.mesa}) solicitada por {usuario_obj.nombre} ({usuario_obj.rol}): {comanda.motivo_reemision}"
        )

        return JsonResponse({
            'success': True,
            'comanda_id': comanda.id,
            'folio': comanda.folio,
            'estado': comanda.estado,
            'es_reemision': comanda.es_reemision,
            'motivo_reemision': comanda.motivo_reemision,
            'message': f'Comanda {comanda.folio} re-emitida como RE_ORDEN. Regresa a la cola activa de preparación.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def cocina_cambiar_estado(request):
    """
    Actualiza el estado de una orden a en_espera, preparación, listo, entregado o RE_ORDEN.
    Blindaje de método: Exige estrictamente POST. Rechaza GET u otros con 405.
    Asegura que siempre redirija de vuelta a la vista de cocina (return redirect('cocinero'))
    preservando el estado de la pestaña actual en la sesión o devolviendo JSON para llamadas asíncronas.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido. Se requiere POST.'}, status=405)

    usuario = obtener_usuario(request)
    if not usuario or usuario.get('rol') not in ['cocinero', 'mesero', 'administrador']:
        if request.content_type != 'application/json' and request.headers.get('x-requested-with') != 'XMLHttpRequest':
            return redirect('cocinero')
        return JsonResponse({'success': False, 'error': 'No autorizado'}, status=403)

    es_json_body = False
    try:
        # Detectar origen de datos (JSON body o request.POST de formulario estándar)
        data = {}
        if request.content_type == 'application/json' or (request.body and request.body.strip().startswith(b'{')):
            try:
                data = json.loads(request.body.decode('utf-8'))
                es_json_body = True
            except Exception:
                data = request.POST.dict()
        else:
            data = request.POST.dict()

        comanda_id = data.get('comanda_id') or request.POST.get('comanda_id')
        raw_estado = (data.get('nuevo_estado') or request.POST.get('nuevo_estado') or '').strip()
        nuevo_estado = raw_estado.lower()
        tab_activa = (data.get('tab_activa') or request.POST.get('tab_activa') or request.GET.get('tab') or '').strip().lower()

        # Mapeo a los estados reconocidos por el sistema
        if nuevo_estado in ['re_orden', 'reorden']:
            estado_db = 'RE_ORDEN'
        elif nuevo_estado in ['preparando', 'preparacion']:
            estado_db = 'preparacion'
        elif nuevo_estado in ['listo']:
            estado_db = 'listo'
        elif nuevo_estado in ['entregado']:
            estado_db = 'entregado'
        elif nuevo_estado in ['en_espera']:
            estado_db = 'en_espera'
        else:
            estado_db = None

        if not estado_db:
            if not es_json_body and request.headers.get('x-requested-with') != 'XMLHttpRequest':
                messages.error(request, f'Estado "{raw_estado}" no es válido.')
                return redirect('cocinero')
            return JsonResponse({'success': False, 'error': f'Estado "{raw_estado}" no es válido.'}, status=400)

        comanda = Comanda.objects.filter(id=comanda_id).first()
        if not comanda:
            if not es_json_body and request.headers.get('x-requested-with') != 'XMLHttpRequest':
                messages.error(request, 'Comanda no encontrada.')
                return redirect('cocinero')
            return JsonResponse({'success': False, 'error': 'Comanda no encontrada.'}, status=404)

        comanda.estado = estado_db
        if estado_db == 'RE_ORDEN':
            comanda.es_reemision = True
            raw_motivo = (data.get('motivo') or data.get('motivo_reemision') or request.POST.get('motivo') or '').strip()
            motivo, motivo_valido, msg_motivo = sanitizar_texto_defensivo(raw_motivo, max_len=150, nombre_campo='motivo de re-orden')
            if not motivo_valido:
                if not es_json_body and request.headers.get('x-requested-with') != 'XMLHttpRequest':
                    messages.error(request, f'Petición rechazada: {msg_motivo}')
                    return redirect('cocinero')
                return JsonResponse({'success': False, 'error': f'Petición rechazada: {msg_motivo}'}, status=400)
            comanda.motivo_reemision = motivo if motivo else 'Solicitud de re-orden / cambio'
            usuario_obj = Usuario.objects.filter(id=usuario.get('id')).first()
            registrar_auditoria(
                usuario_obj,
                'RE_ORDEN',
                'Cocina',
                f"Re-emisión de comanda {comanda.folio} ({comanda.mesa}) solicitada por {usuario_obj.nombre} ({usuario_obj.rol}): {comanda.motivo_reemision}"
            )
        comanda.save()

        # Almacenar la pestaña activa en la sesión del usuario para persistencia
        if not tab_activa or tab_activa not in ['en_espera', 'preparacion', 'listo', 'entregado', 'recocinando']:
            tab_activa = request.session.get('tab_cocina_activa') or 'en_espera'
        request.session['tab_cocina_activa'] = tab_activa

        # Si la petición es tradicional (formulario POST) o solicita redirección explícita:
        # Asegura que siempre redirija de vuelta a la vista de cocina (return redirect('cocinero'))
        quiere_redirect = (
            not es_json_body or
            str(request.POST.get('redirect', '')).lower() in ['1', 'true'] or
            str(data.get('redirect', '')).lower() in ['1', 'true'] or
            request.headers.get('accept', '').startswith('text/html')
        ) and (request.headers.get('x-requested-with') != 'XMLHttpRequest')

        if quiere_redirect:
            return redirect('cocinero')

        return JsonResponse({
            'success': True,
            'nuevo_estado': comanda.estado,
            'es_reemision': comanda.es_reemision,
            'tab_activa': tab_activa,
            'redirect_url': reverse('cocinero')
        })
    except Exception as e:
        if not es_json_body and request.headers.get('x-requested-with') != 'XMLHttpRequest':
            messages.error(request, f'Error al actualizar comanda: {str(e)}')
            return redirect('cocinero')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==============================================================================
# 5. MÓDULO DE ADMINISTRADOR (CONTROL DE CAJA, USUARIOS Y AUDITORÍA)
# ==============================================================================

def administrador_view(request):
    """
    Panel general de administración:
    - Control de Caja con apertura obligatoria y arqueo de cierre.
    - Reportes estadísticos avanzados con agregaciones ORM (Sum, Count, Avg):
      * Total vendido por día, semana y mes.
      * Top 5 productos más vendidos.
      * Cantidad de ventas y ticket promedio por turno y por mesero.
    - Gestión de cuentas de empleados y auditoría de ventas.
    - Envoltorio de consultas críticas en bloques try/except controlados para que,
      en caso de un fallo de acceso, ruta inválida o permiso denegado, el sistema
      renderice limpiamente las plantillas de error (401.html, 403.html, 404.html o 500.html).
    """
    # 1. Validación de sesión y rol con try/except defensivo
    try:
        usuario = obtener_usuario(request)
        if not usuario:
            return error_401_view(request, mensaje='Se requiere iniciar sesión como Administrador para acceder al panel de control.')
        if usuario.get('rol') != 'administrador':
            return error_403_view(request, mensaje=f'Acceso denegado: El usuario con rol "{usuario.get("rol")}" no tiene privilegios de Administrador.')
    except Exception as e:
        return error_403_view(request, mensaje=f'Fallo de validación de acceso o permisos: {str(e)}')

    # 2. Consultas y preparación de datos envueltas en bloque try/except controlado
    try:
        usuarios = Usuario.objects.all().order_by('nombre')
        cajeros = Usuario.objects.filter(rol__in=['cajero', 'administrador']).order_by('nombre')
        meseros = Usuario.objects.filter(rol='mesero').order_by('nombre')
        ventas_recientes = Venta.objects.all().order_by('-fecha')[:15]
        productos = Producto.objects.all()
        caja = ControlCaja.objects.last()

        # Nombre seguro del cajero responsable de la caja activa
        caja_cajero_nombre = "Sin asignar"
        if caja:
            try:
                if caja.cajero_responsable and hasattr(caja.cajero_responsable, 'nombre'):
                    caja_cajero_nombre = caja.cajero_responsable.nombre
                elif caja.usuario and hasattr(caja.usuario, 'nombre'):
                    caja_cajero_nombre = caja.usuario.nombre
            except (ObjectDoesNotExist, AttributeError):
                caja_cajero_nombre = "Sin asignar"

        # Cálculo de duración/timer si la caja está abierta o cerrada (con validación de fecha_apertura)
        duracion_str = ""
        if caja and caja.fecha_apertura:
            fin = caja.fecha_cierre if not caja.abierta and caja.fecha_cierre else timezone.now()
            if fin:
                delta = fin - caja.fecha_apertura
                horas = int(delta.total_seconds() // 3600)
                minutos = int((delta.total_seconds() % 3600) // 60)
                duracion_str = f"{horas}h {minutos}m"

        # =========================================================================
        # REPORTES ESTADÍSTICOS CON AGREGACIONES DEL ORM (Sum, Count, Avg)
        # =========================================================================
        ahora = timezone.now()
        inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        inicio_semana = ahora - timezone.timedelta(days=7)
        inicio_mes = ahora - timezone.timedelta(days=30)

        # 1. Total recaudado en la jornada actual (jornada/hoy)
        ventas_jornada = Venta.objects.filter(fecha__gte=inicio_dia)
        agg_jornada = ventas_jornada.aggregate(
            total_recaudado=Sum('total'),
            cantidad=Count('id'),
            ticket_promedio=Avg('total'),
            efectivo=Sum('total', filter=Q(metodo_pago='efectivo')),
            tarjeta=Sum('total', filter=Q(metodo_pago='tarjeta')),
            transferencia=Sum('total', filter=Q(metodo_pago='transferencia'))
        )
        total_jornada = agg_jornada['total_recaudado'] or Decimal('0.00')
        cant_jornada = agg_jornada['cantidad'] or 0
        prom_jornada = agg_jornada['ticket_promedio'] or Decimal('0.00')
        jornada_efectivo = agg_jornada['efectivo'] or Decimal('0.00')
        jornada_tarjeta = agg_jornada['tarjeta'] or Decimal('0.00')
        jornada_transferencia = agg_jornada['transferencia'] or Decimal('0.00')

        # Métricas de períodos anteriores (compatibilidad y análisis temporal)
        total_dia = total_jornada
        cant_dia = cant_jornada
        prom_dia = prom_jornada

        agg_semana = Venta.objects.filter(fecha__gte=inicio_semana).aggregate(
            total_recaudado=Sum('total'),
            cantidad=Count('id'),
            ticket_promedio=Avg('total')
        )
        total_semana = agg_semana['total_recaudado'] or Decimal('0.00')
        cant_semana = agg_semana['cantidad'] or 0
        prom_semana = agg_semana['ticket_promedio'] or Decimal('0.00')

        agg_mes = Venta.objects.filter(fecha__gte=inicio_mes).aggregate(
            total_recaudado=Sum('total'),
            cantidad=Count('id'),
            ticket_promedio=Avg('total')
        )
        total_mes = agg_mes['total_recaudado'] or Decimal('0.00')
        cant_mes = agg_mes['cantidad'] or 0
        prom_mes = agg_mes['ticket_promedio'] or Decimal('0.00')

        # Total histórico acumulado
        agg_historico = Venta.objects.aggregate(
            total_recaudado=Sum('total'),
            cantidad=Count('id'),
            ticket_promedio=Avg('total')
        )
        total_historico = agg_historico['total_recaudado'] or Decimal('0.00')
        cant_historico = agg_historico['cantidad'] or 0
        prom_historico = agg_historico['ticket_promedio'] or Decimal('0.00')

        # 1.1 Desglose histórico por fecha (agrupado por día mediante Cast a DateField)
        desglose_por_fecha = (
            Venta.objects.annotate(fecha_dia=Cast('fecha', DateField()))
            .values('fecha_dia')
            .annotate(
                total_recaudado=Sum('total'),
                cantidad_ventas=Count('id'),
                ticket_promedio=Avg('total'),
                total_efectivo=Sum('total', filter=Q(metodo_pago='efectivo')),
                total_tarjeta=Sum('total', filter=Q(metodo_pago='tarjeta')),
                total_transferencia=Sum('total', filter=Q(metodo_pago='transferencia'))
            )
            .order_by('-fecha_dia')[:15]
        )

        # 2. Desglose de ingresos por método de pago (Efectivo vs. Tarjeta vs. Transferencia)
        desglose_metodos_raw = (
            Venta.objects.values('metodo_pago')
            .annotate(
                total_recaudado=Sum('total'),
                cantidad_ventas=Count('id'),
                ticket_promedio=Avg('total')
            )
            .order_by('-total_recaudado')
        )
        desglose_metodos = []
        total_efectivo_gral = Decimal('0.00')
        total_tarjeta_gral = Decimal('0.00')
        total_transferencia_gral = Decimal('0.00')
        cant_efectivo_gral = 0
        cant_tarjeta_gral = 0
        cant_transferencia_gral = 0

        for m in desglose_metodos_raw:
            met = (m.get('metodo_pago') or 'efectivo').lower()
            tot = m.get('total_recaudado') or Decimal('0.00')
            cant = m.get('cantidad_ventas') or 0
            prom = m.get('ticket_promedio') or Decimal('0.00')
            pct = float((tot / total_historico) * 100) if total_historico > 0 else 0.0

            if met == 'efectivo':
                total_efectivo_gral = tot
                cant_efectivo_gral = cant
            elif met == 'tarjeta':
                total_tarjeta_gral = tot
                cant_tarjeta_gral = cant
            elif met == 'transferencia':
                total_transferencia_gral = tot
                cant_transferencia_gral = cant

            desglose_metodos.append({
                'metodo': met.capitalize(),
                'metodo_key': met,
                'total_recaudado': tot,
                'cantidad_ventas': cant,
                'ticket_promedio': prom,
                'porcentaje': round(pct, 1)
            })

        pct_efectivo = round(float((total_efectivo_gral / total_historico) * 100), 1) if total_historico > 0 else 0.0
        pct_tarjeta = round(float((total_tarjeta_gral / total_historico) * 100), 1) if total_historico > 0 else 0.0
        pct_transferencia = round(float((total_transferencia_gral / total_historico) * 100), 1) if total_historico > 0 else 0.0

        # 3. Ranking de los 5 productos con mayor volumen de venta (annotate(total_vendido=Sum('cantidad')))
        top_5_productos = (
            DetalleVenta.objects.values('producto__id', 'producto__nombre', 'producto__precio')
            .annotate(
                total_vendido=Sum('cantidad'),
                total_unidades=Sum('cantidad'),  # Compatibilidad
                total_recaudado=Sum('subtotal'),
                ticket_promedio=Avg('subtotal')
            )
            .order_by('-total_vendido')[:5]
        )

        # 4. Total de diferencias de caja registradas (sobrantes o faltantes acumulados en las cuadraturas)
        cajas_cerradas_qs = ControlCaja.objects.filter(Q(abierta=False) | Q(estado='CERRADA'))
        agg_diferencias = cajas_cerradas_qs.aggregate(
            total_diferencias=Sum(Coalesce('diferencia_cuadratura', 'diferencia', Decimal('0.00'))),
            total_sobrantes=Sum(Coalesce('diferencia_cuadratura', 'diferencia', Decimal('0.00')), filter=Q(diferencia_cuadratura__gt=0) | Q(diferencia__gt=0)),
            total_faltantes=Sum(Coalesce('diferencia_cuadratura', 'diferencia', Decimal('0.00')), filter=Q(diferencia_cuadratura__lt=0) | Q(diferencia__lt=0)),
            conteo_sobrantes=Count('id', filter=Q(diferencia_cuadratura__gt=0) | Q(diferencia__gt=0)),
            conteo_faltantes=Count('id', filter=Q(diferencia_cuadratura__lt=0) | Q(diferencia__lt=0)),
            conteo_cuadradas=Count('id', filter=Q(diferencia_cuadratura=0) | Q(diferencia=0)),
            total_cuadraturas=Count('id')
        )
        total_diferencias_caja = agg_diferencias['total_diferencias'] or Decimal('0.00')
        total_sobrantes_caja = agg_diferencias['total_sobrantes'] or Decimal('0.00')
        total_faltantes_caja = agg_diferencias['total_faltantes'] or Decimal('0.00')
        conteo_sobrantes_caja = agg_diferencias['conteo_sobrantes'] or 0
        conteo_faltantes_caja = agg_diferencias['conteo_faltantes'] or 0
        conteo_cuadradas_caja = agg_diferencias['conteo_cuadradas'] or 0
        total_cuadraturas_caja = agg_diferencias['total_cuadraturas'] or 0

        # 5. Cantidad de ventas y ticket promedio por turno (ControlCaja) con detalle de cuadratura
        turnos_historial = []
        cajas_recientes = ControlCaja.objects.all().order_by('-id')[:10]
        for c in cajas_recientes:
            v_caja = Venta.objects.filter(control_caja=c)
            if not v_caja.exists() and c:
                if c.fecha_cierre and c.fecha_apertura:
                    v_caja = Venta.objects.filter(fecha__gte=c.fecha_apertura, fecha__lte=c.fecha_cierre)
                elif c.fecha_apertura:
                    v_caja = Venta.objects.filter(fecha__gte=c.fecha_apertura)

            agg_t = v_caja.aggregate(
                cantidad=Count('id'),
                total_recaudado=Sum('total'),
                ticket_promedio=Avg('total')
            )
            dif_val = c.diferencia_cuadratura if c.diferencia_cuadratura is not None else c.diferencia
            if dif_val is None:
                estado_cuadratura = 'pendiente'
            elif dif_val == Decimal('0.00'):
                estado_cuadratura = 'cuadrada'
            elif dif_val > Decimal('0.00'):
                estado_cuadratura = 'sobrante'
            else:
                estado_cuadratura = 'faltante'

            cajero_nombre = "Sin asignar"
            try:
                if c.cajero_responsable and hasattr(c.cajero_responsable, 'nombre'):
                    cajero_nombre = c.cajero_responsable.nombre
                elif c.usuario and hasattr(c.usuario, 'nombre'):
                    cajero_nombre = c.usuario.nombre
            except (ObjectDoesNotExist, AttributeError):
                cajero_nombre = "Sin asignar"

            cerrada_por_username = "-"
            try:
                if c.cerrada_por and hasattr(c.cerrada_por, 'username'):
                    cerrada_por_username = c.cerrada_por.username
            except (ObjectDoesNotExist, AttributeError):
                cerrada_por_username = "-"

            turnos_historial.append({
                'caja': c,
                'cajero_nombre': cajero_nombre,
                'cerrada_por_username': cerrada_por_username,
                'cantidad_ventas': agg_t['cantidad'] or 0,
                'total_ventas': agg_t['total_recaudado'] or Decimal('0.00'),
                'ticket_promedio': agg_t['ticket_promedio'] or Decimal('0.00'),
                'diferencia': dif_val,
                'estado_cuadratura': estado_cuadratura
            })

        # 6. Cantidad de ventas y ticket promedio por mesero
        ventas_por_mesero = (
            Venta.objects.filter(mesero__isnull=False)
            .values('mesero__id', 'mesero__nombre', 'mesero__username')
            .annotate(
                cantidad_ventas=Count('id'),
                total_ventas=Sum('total'),
                ticket_promedio=Avg('total')
            )
            .order_by('-total_ventas')
        )

        # Arqueo de la caja activa si está abierta
        arqueo_caja_actual = None
        if caja and caja.abierta:
            v_actual = Venta.objects.filter(control_caja=caja)
            tot_v = v_actual.aggregate(s=Sum('total'))['s'] or Decimal('0.00')
            tot_ef = v_actual.filter(metodo_pago='efectivo').aggregate(s=Sum('total'))['s'] or Decimal('0.00')
            tot_tarj = v_actual.filter(metodo_pago='tarjeta').aggregate(s=Sum('total'))['s'] or Decimal('0.00')
            tot_trans = v_actual.filter(metodo_pago='transferencia').aggregate(s=Sum('total'))['s'] or Decimal('0.00')
            ef_esp = (caja.monto_inicial or Decimal('0.00')) + tot_ef
            arqueo_caja_actual = {
                'total_ventas': tot_v,
                'total_efectivo': tot_ef,
                'total_tarjeta': tot_tarj,
                'total_transferencia': tot_trans,
                'efectivo_esperado': ef_esp
            }

        alerta_admin = request.session.pop('alerta_admin', None)

        context = {
            'usuario': usuario.get('nombre'),
            'rol': usuario.get('rol'),
            'usuarios': usuarios,
            'cajeros': cajeros,
            'meseros': meseros,
            'ventas': ventas_recientes,
            'productos': productos,
            'caja': caja,
            'caja_cajero_nombre': caja_cajero_nombre,
            'duracion_caja': duracion_str,
            'alerta_admin': alerta_admin,
            # 1. Total recaudado en la jornada actual y períodos
            'total_jornada': total_jornada,
            'cant_jornada': cant_jornada,
            'prom_jornada': prom_jornada,
            'jornada_efectivo': jornada_efectivo,
            'jornada_tarjeta': jornada_tarjeta,
            'jornada_transferencia': jornada_transferencia,
            'total_dia': total_dia,
            'cant_dia': cant_dia,
            'prom_dia': prom_dia,
            'total_semana': total_semana,
            'cant_semana': cant_semana,
            'prom_semana': prom_semana,
            'total_mes': total_mes,
            'cant_mes': cant_mes,
            'prom_mes': prom_mes,
            'total_historico': total_historico,
            'cant_historico': cant_historico,
            'prom_historico': prom_historico,
            # 1.1 Desglose histórico por fecha
            'desglose_por_fecha': desglose_por_fecha,
            # 2. Desglose de ingresos por método de pago (Efectivo vs. Tarjeta)
            'desglose_metodos': desglose_metodos,
            'total_efectivo_gral': total_efectivo_gral,
            'total_tarjeta_gral': total_tarjeta_gral,
            'total_transferencia_gral': total_transferencia_gral,
            'cant_efectivo_gral': cant_efectivo_gral,
            'cant_tarjeta_gral': cant_tarjeta_gral,
            'cant_transferencia_gral': cant_transferencia_gral,
            'pct_efectivo': pct_efectivo,
            'pct_tarjeta': pct_tarjeta,
            'pct_transferencia': pct_transferencia,
            # 3. Ranking de los 5 productos con mayor volumen de venta
            'top_5_productos': top_5_productos,
            # 4. Total de diferencias de caja registradas (cuadraturas)
            'total_diferencias_caja': total_diferencias_caja,
            'total_sobrantes_caja': total_sobrantes_caja,
            'total_faltantes_caja': total_faltantes_caja,
            'conteo_sobrantes_caja': conteo_sobrantes_caja,
            'conteo_faltantes_caja': conteo_faltantes_caja,
            'conteo_cuadradas_caja': conteo_cuadradas_caja,
            'total_cuadraturas_caja': total_cuadraturas_caja,
            # 5. Auditoría de turnos y meseros
            'turnos_historial': turnos_historial,
            'ventas_por_mesero': ventas_por_mesero,
            'arqueo_caja_actual': arqueo_caja_actual,
        }
        return render(request, 'administrador.html', context)
    except PermissionDenied as e:
        return error_403_view(request, mensaje=f'Acceso denegado: {str(e)}')
    except Http404 as e:
        return error_404_view(request, mensaje=f'Recurso no encontrado: {str(e)}')
    except (ObjectDoesNotExist, AttributeError, TypeError, DatabaseError, Exception) as e:
        return error_500_view(request, mensaje=f'Error interno al procesar el panel de Administración: {str(e)}')


def api_resumen_caja_actual(request):
    """Retorna en JSON el estado y cálculo en tiempo real de la caja abierta para el arqueo."""
    usuario = obtener_usuario(request)
    if not usuario or usuario.get('rol') not in ['administrador', 'cajero']:
        return JsonResponse({'success': False, 'error': 'No autorizado'}, status=403)

    caja = ControlCaja.objects.filter(Q(abierta=True) & Q(estado='ABIERTA')).last()
    if not caja:
        return JsonResponse({'success': False, 'caja_abierta': False, 'error': 'No hay caja abierta actualmente.'})

    ventas = Venta.objects.filter(control_caja=caja)
    tot_ventas = ventas.aggregate(s=Sum('total'))['s'] or Decimal('0.00')
    tot_efectivo = ventas.filter(metodo_pago='efectivo').aggregate(s=Sum('total'))['s'] or Decimal('0.00')
    tot_tarjeta = ventas.filter(metodo_pago='tarjeta').aggregate(s=Sum('total'))['s'] or Decimal('0.00')
    tot_transferencia = ventas.filter(metodo_pago='transferencia').aggregate(s=Sum('total'))['s'] or Decimal('0.00')
    efectivo_esperado = (caja.monto_inicial or Decimal('0.00')) + tot_efectivo

    cajero_nombre = caja.usuario.nombre if caja.usuario else (caja.cajero_responsable.nombre if caja.cajero_responsable else 'Sin asignar')
    punto_nombre = caja.punto_venta.nombre if caja.punto_venta else (caja.punto_de_venta.nombre if caja.punto_de_venta else 'Caja Principal')

    return JsonResponse({
        'success': True,
        'caja_abierta': True,
        'caja_id': caja.id,
        'estado': caja.estado,
        'cajero_apertura': cajero_nombre,
        'punto_venta': punto_nombre,
        'fecha_apertura': caja.fecha_apertura.strftime('%d/%m/%Y %H:%M:%S'),
        'monto_inicial': float(caja.monto_inicial or 0),
        'total_ventas': float(tot_ventas),
        'total_ventas_sistema': float(tot_ventas),
        'total_efectivo': float(tot_efectivo),
        'total_tarjeta': float(tot_tarjeta),
        'total_transferencia': float(tot_transferencia),
        'efectivo_esperado': float(efectivo_esperado)
    })


def admin_abrir_caja(request):
    """
    Abre una nueva jornada/turno de caja.
    Blindaje de método: Exige estrictamente POST. Rechaza GET u otros con 405.
    Validaciones de Sesión de Caja:
    - Solo se puede abrir si el cajero no tiene ya una caja en estado 'ABIERTA'.
    - Exigir ingresar obligatoriamente un monto_inicial numérico positivo mayor o igual a 0.
    - Asigna punto de venta y usuario responsable, marcando estado='ABIERTA' y abierta=True.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido. Se requiere POST.'}, status=405)

    usuario = obtener_usuario(request)
    if not usuario or usuario.get('rol') not in ['administrador', 'cajero']:
        return JsonResponse({'success': False, 'error': 'No autorizado para abrir caja.'}, status=403)

    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST

        cajero_id = data.get('cajero_id') or usuario.get('id')
        cajero_obj = Usuario.objects.filter(id=cajero_id).first()
        if not cajero_obj:
            return JsonResponse({'success': False, 'error': 'Debe seleccionar un cajero responsable válido.'}, status=400)

        # Validación: Solo se puede abrir si el cajero no tiene ya una caja en estado 'ABIERTA'
        caja_cajero_abierta = ControlCaja.objects.filter(
            Q(cajero_responsable=cajero_obj) | Q(usuario=cajero_obj),
            Q(abierta=True) | Q(estado='ABIERTA')
        ).first()
        if caja_cajero_abierta:
            return JsonResponse({
                'success': False,
                'error': f'El cajero {cajero_obj.nombre} ya tiene una caja en estado ABIERTA iniciada el {caja_cajero_abierta.fecha_apertura.strftime("%d/%m/%Y %H:%M")}. Debe cerrarla antes de iniciar una nueva.'
            }, status=400)

        # Validación: Comprobar si existe una caja abierta general en el sistema
        caja_abierta_existente = ControlCaja.objects.filter(Q(abierta=True) | Q(estado='ABIERTA')).last()
        if caja_abierta_existente:
            return JsonResponse({
                'success': False,
                'error': f'Ya existe un turno de caja abierto iniciado el {caja_abierta_existente.fecha_apertura.strftime("%d/%m/%Y %H:%M")}. Debe cerrarlo antes de iniciar uno nuevo.'
            }, status=400)

        # Validación: Exigir obligatoriamente un monto_inicial numérico positivo mayor o igual a 0
        raw_monto = data.get('monto_inicial')
        if raw_monto is None or str(raw_monto).strip() == '':
            return JsonResponse({'success': False, 'error': 'Debe ingresar obligatoriamente el monto inicial (fondo de caja) mayor o igual a 0.'}, status=400)

        try:
            monto_inicial = Decimal(str(raw_monto).strip())
            if monto_inicial < 0:
                raise ValueError()
        except (ValueError, TypeError, InvalidOperation):
            return JsonResponse({'success': False, 'error': 'El monto inicial (fondo de caja) debe ser un número mayor o igual a 0.'}, status=400)

        # Punto de venta asociado
        punto_venta_id = data.get('punto_venta_id') or data.get('punto_de_venta_id')
        punto_venta_obj = None
        if punto_venta_id:
            punto_venta_obj = PuntoDeVenta.objects.filter(id=punto_venta_id).first()
        if not punto_venta_obj:
            punto_venta_obj = PuntoDeVenta.objects.first()

        nueva_caja = ControlCaja.objects.create(
            abierta=True,
            estado='ABIERTA',
            fecha_apertura=timezone.now(),
            usuario=cajero_obj,
            cajero_responsable=cajero_obj,
            punto_venta=punto_venta_obj,
            punto_de_venta=punto_venta_obj,
            monto_inicial=monto_inicial
        )

        # Registrar en auditoría
        usuario_operador = Usuario.objects.filter(id=usuario.get('id')).first()
        registrar_auditoria(
            usuario_operador,
            'APERTURA_CAJA',
            'Control de Caja',
            f"Apertura de turno #{nueva_caja.id} para cajero {cajero_obj.nombre} - Fondo Inicial: ${monto_inicial:,.0f} CLP"
        )

        return JsonResponse({
            'success': True,
            'message': f'Apertura de jornada exitosa. Cajero: {cajero_obj.nombre} | Fondo Inicial: ${monto_inicial:,.0f} CLP.',
            'caja_id': nueva_caja.id
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def admin_cerrar_caja(request):
    """
    Cierra la caja del turno activo cumpliendo con el proceso operativo formal de caja y auditoría:
    - Blindaje de método HTTP: Exige estrictamente POST. Rechaza GET u otros con 405.
    - Recepción de cantidades de cada billete y moneda ingresadas por el cajero.
    - Recálculo obligatorio del total en el backend sin fiarse del cálculo enviado por el cliente:
      Total = (b20*20000) + (b10*10000) + (b5*5000) + (b1*1000) + (m500*500) + (m100*100) + (m50*50) + (m5*5) + (m1*1)
    - Cálculo de la diferencia con respecto a (monto_inicial + ventas_efectivo_del_turno).
    - Persistencia en BD de estado 'CERRADA', total_ventas_sistema, total_efectivo_declarado, diferencia_cuadratura y arqueo detallado.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido. Se requiere POST.'}, status=405)

    usuario = obtener_usuario(request)
    if not usuario or usuario.get('rol') not in ['administrador', 'cajero']:
        return JsonResponse({'success': False, 'error': 'No autorizado para cerrar caja.'}, status=403)

    caja = ControlCaja.objects.filter(Q(abierta=True) | Q(estado='ABIERTA')).last()
    if not caja:
        return JsonResponse({'success': False, 'error': 'No hay ninguna caja abierta para cerrar.'}, status=400)

    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST

        denominaciones_keys = [
            'billetes_20000', 'billetes_10000', 'billetes_5000', 'billetes_1000',
            'monedas_500', 'monedas_100', 'monedas_50', 'monedas_5', 'monedas_1'
        ]
        hay_denominaciones = any(k in data for k in denominaciones_keys)

        if hay_denominaciones:
            def safe_int(val, nombre_campo):
                if val is None or str(val).strip() == '':
                    return 0
                try:
                    v = int(val)
                    if v < 0:
                        raise ValueError()
                    return v
                except (ValueError, TypeError):
                    raise ValueError(f"La cantidad ingresada para {nombre_campo} debe ser un número entero mayor o igual a 0.")

            try:
                b20 = safe_int(data.get('billetes_20000'), 'billetes de 20.000')
                b10 = safe_int(data.get('billetes_10000'), 'billetes de 10.000')
                b5 = safe_int(data.get('billetes_5000'), 'billetes de 5.000')
                b1 = safe_int(data.get('billetes_1000'), 'billetes de 1.000')
                m500 = safe_int(data.get('monedas_500'), 'monedas de 500')
                m100 = safe_int(data.get('monedas_100'), 'monedas de 100')
                m50 = safe_int(data.get('monedas_50'), 'monedas de 50')
                m5 = safe_int(data.get('monedas_5'), 'monedas de 5')
                m1 = safe_int(data.get('monedas_1'), 'monedas de 1')
            except ValueError as ve:
                return JsonResponse({'success': False, 'error': str(ve)}, status=400)

            # Recálculo obligatorio del total en el servidor (sin fiarse del cliente)
            # Total = (b20*20000) + (b10*10000) + (b5*5000) + (b1*1000) + (m500*500) + (m100*100) + (m50*50) + (m5*5) + (m1*1)
            total_recalculado = (
                (b20 * 20000) +
                (b10 * 10000) +
                (b5 * 5000) +
                (b1 * 1000) +
                (m500 * 500) +
                (m100 * 100) +
                (m50 * 50) +
                (m5 * 5) +
                (m1 * 1)
            )
            monto_real = Decimal(str(total_recalculado))

            # Guardar el desglose de arqueo detallado
            caja.billetes_20000 = b20
            caja.billetes_10000 = b10
            caja.billetes_5000 = b5
            caja.billetes_1000 = b1
            caja.monedas_500 = m500
            caja.monedas_100 = m100
            caja.monedas_50 = m50
            caja.monedas_5 = m5
            caja.monedas_1 = m1
        else:
            # Soporte de compatibilidad cuando solo se envía monto_real directo
            raw_monto_real = data.get('monto_real')
            if raw_monto_real is None or str(raw_monto_real).strip() == '':
                return JsonResponse({'success': False, 'error': 'Debe ingresar el detalle de billetes y monedas o el monto real en efectivo contado en la gaveta.'}, status=400)

            try:
                monto_real = Decimal(str(raw_monto_real).strip())
                if monto_real < 0:
                    raise ValueError()
            except (ValueError, TypeError, InvalidOperation):
                return JsonResponse({'success': False, 'error': 'El monto contado debe ser un valor numérico válido mayor o igual a 0.'}, status=400)

        # Cálculos de ventas y métodos de pago del turno
        ventas_turno = Venta.objects.filter(control_caja=caja)
        total_ventas = ventas_turno.aggregate(s=Sum('total'))['s'] or Decimal('0.00')
        total_efectivo = ventas_turno.filter(metodo_pago='efectivo').aggregate(s=Sum('total'))['s'] or Decimal('0.00')
        total_tarjeta = ventas_turno.filter(metodo_pago='tarjeta').aggregate(s=Sum('total'))['s'] or Decimal('0.00')
        total_transferencia = ventas_turno.filter(metodo_pago='transferencia').aggregate(s=Sum('total'))['s'] or Decimal('0.00')

        fondo_inicial = caja.monto_inicial or Decimal('0.00')
        efectivo_esperado = fondo_inicial + total_efectivo
        diferencia = monto_real - efectivo_esperado

        # Actualizar registro de caja y arqueo en la BD
        usuario_obj = Usuario.objects.filter(id=usuario.get('id')).first()
        caja.abierta = False
        caja.estado = 'CERRADA'
        caja.fecha_cierre = timezone.now()
        caja.cerrada_por = usuario_obj
        caja.total_ventas = total_ventas
        caja.total_ventas_sistema = total_ventas
        caja.total_efectivo = total_efectivo
        caja.total_tarjeta = total_tarjeta
        caja.total_transferencia = total_transferencia
        caja.monto_real = monto_real
        caja.total_efectivo_declarado = monto_real
        caja.diferencia = diferencia
        caja.diferencia_cuadratura = diferencia
        caja.save()

        if diferencia == Decimal('0.00'):
            estado_dif = 'cuadrada'
            mensaje_dif = 'Caja Cuadrada exactamente sin diferencias.'
        elif diferencia > Decimal('0.00'):
            estado_dif = 'sobrante'
            mensaje_dif = f'Sobrante de caja de +${diferencia:,.0f} CLP.'
        else:
            estado_dif = 'faltante'
            mensaje_dif = f'Faltante de caja de -${abs(diferencia):,.0f} CLP.'

        # Registro en auditoría
        cajero_ap_nombre = caja.usuario.nombre if caja.usuario else (caja.cajero_responsable.nombre if caja.cajero_responsable else 'Sin asignar')
        registrar_auditoria(
            usuario_obj,
            'CIERRE_CAJA',
            'Control de Caja',
            f"Cierre de caja #{caja.id} ({cajero_ap_nombre}) - Total Ventas: ${total_ventas:,.0f} CLP - Arqueo: {diferencia:,.0f} CLP ({estado_dif})"
        )

        return JsonResponse({
            'success': True,
            'message': f'Cierre y arqueo de caja completado exitosamente. {mensaje_dif}',
            'arqueo': {
                'cajero_apertura': cajero_ap_nombre,
                'cerrada_por': usuario_obj.nombre if usuario_obj else 'Admin',
                'punto_venta': caja.punto_venta.nombre if caja.punto_venta else (caja.punto_de_venta.nombre if caja.punto_de_venta else 'Caja General'),
                'fecha_apertura': caja.fecha_apertura.strftime('%d/%m/%Y %H:%M:%S'),
                'fecha_cierre': caja.fecha_cierre.strftime('%d/%m/%Y %H:%M:%S'),
                'monto_inicial': float(fondo_inicial),
                'total_ventas': float(total_ventas),
                'total_ventas_sistema': float(total_ventas),
                'total_efectivo': float(total_efectivo),
                'total_tarjeta': float(total_tarjeta),
                'total_transferencia': float(total_transferencia),
                'efectivo_esperado': float(efectivo_esperado),
                'monto_real': float(monto_real),
                'total_efectivo_declarado': float(monto_real),
                'diferencia': float(diferencia),
                'diferencia_cuadratura': float(diferencia),
                'estado': caja.estado,
                'estado_diferencia': estado_dif,
                'mensaje_diferencia': mensaje_dif,
                'desglose_arqueo': {
                    'billetes_20000': caja.billetes_20000,
                    'billetes_10000': caja.billetes_10000,
                    'billetes_5000': caja.billetes_5000,
                    'billetes_1000': caja.billetes_1000,
                    'monedas_500': caja.monedas_500,
                    'monedas_100': caja.monedas_100,
                    'monedas_50': caja.monedas_50,
                    'monedas_5': caja.monedas_5,
                    'monedas_1': caja.monedas_1,
                    'subtotal_billetes': float((caja.billetes_20000 * 20000) + (caja.billetes_10000 * 10000) + (caja.billetes_5000 * 5000) + (caja.billetes_1000 * 1000)),
                    'subtotal_monedas': float((caja.monedas_500 * 500) + (caja.monedas_100 * 100) + (caja.monedas_50 * 50) + (caja.monedas_5 * 5) + (caja.monedas_1 * 1))
                }
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)



def admin_guardar_usuario(request):
    """Crea o edita un usuario en MySQL con reautenticación para crear otro administrador."""
    usuario = obtener_usuario(request)
    if not usuario:
        return error_401_view(request, mensaje='Se requiere iniciar sesión como Administrador.')
    if usuario.get('rol') != 'administrador':
        return error_403_view(request, mensaje='Acceso denegado: Solo el Administrador puede registrar o modificar usuarios.')

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        rut = request.POST.get('rut', '').strip()
        nombre = request.POST.get('nombre', '').strip()
        correo = request.POST.get('correo', '').strip()
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        rol = request.POST.get('rol', 'cajero').strip()
        estado = request.POST.get('estado', 'activo').strip()

        # Validación estricta de datos (Error 400 ante mal dato)
        if not nombre or not correo or not username:
            return error_400_view(request, mensaje='Petición incorrecta: Nombre, correo y nombre de usuario son campos obligatorios.')

        # Validación de caracteres prohibidos y secuencias de inyección SQL / XSS con validar_texto_seguro
        res_nom = validar_texto_seguro(nombre, nombre_campo="nombre", requerido=True, max_len=100, permitir_guion_bajo=False)
        if not res_nom.es_valido:
            return error_400_view(request, mensaje=f'Petición incorrecta: {res_nom.mensaje}')

        res_usr = validar_texto_seguro(username, nombre_campo="nombre de usuario", requerido=True, max_len=50, permitir_guion_bajo=True)
        if not res_usr.es_valido:
            return error_400_view(request, mensaje=f'Petición incorrecta: {res_usr.mensaje}')

        res_cor = validar_texto_seguro(correo, nombre_campo="correo", requerido=True, max_len=100, permitir_guion_bajo=True)
        if not res_cor.es_valido:
            return error_400_view(request, mensaje=f'Petición incorrecta: {res_cor.mensaje}')

        if rut:
            res_rut = validar_texto_seguro(rut, nombre_campo="RUT", requerido=False, max_len=20, permitir_guion_bajo=False)
            if not res_rut.es_valido:
                return error_400_view(request, mensaje=f'Petición incorrecta: {res_rut.mensaje}')

        if password:
            res_pwd = validar_texto_seguro(password, nombre_campo="contraseña", requerido=False, max_len=128, permitir_guion_bajo=True)
            if not res_pwd.es_valido:
                return error_400_view(request, mensaje=f'Petición incorrecta: {res_pwd.mensaje}')

        if rol not in ['administrador', 'cajero', 'mesero', 'cocinero']:
            return error_400_view(request, mensaje=f'Petición incorrecta: El rol "{rol}" no es válido en el sistema.')

        if estado not in ['activo', 'inactivo']:
            estado = 'activo'

        # Prohibir terminantemente que el Administrador se auto-modifique o se desactive
        current_admin_id = request.session.get('usuario_id') or usuario.get('id')
        if user_id and str(user_id).strip():
            try:
                target_user_id = int(str(user_id).strip())
            except (ValueError, TypeError):
                return error_400_view(request, mensaje='Petición incorrecta: El identificador de usuario debe ser numérico.')

            if current_admin_id and target_user_id == int(current_admin_id):
                messages.error(request, 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión')
                request.session['alerta_admin'] = {
                    'tipo': 'danger',
                    'texto': 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión'
                }
                return error_400_view(request, mensaje='No puedes desactivar ni modificar tu propia cuenta de administrador en sesión')

        # Verificación de credenciales al crear o asignar rol de Administrador a otro usuario
        es_crear_otro_admin = (rol == 'administrador' and (not user_id or str(user_id).strip() != str(current_admin_id)))

        if es_crear_otro_admin:
            confirm_user = request.POST.get('admin_confirm_username', '').strip()
            confirm_pass = request.POST.get('admin_confirm_password', '').strip()

            admin_actual = Usuario.objects.filter(id=current_admin_id).first()
            if not admin_actual or admin_actual.password != confirm_pass or (admin_actual.username != confirm_user and admin_actual.correo != confirm_user):
                request.session['alerta_admin'] = {
                    'tipo': 'danger',
                    'texto': 'Confirmación denegada: Sus credenciales actuales son incorrectas. No se autorizó la creación/asignación de otro Administrador.'
                }
                return redirect('/administrador/')

        if user_id and str(user_id).strip():
            u = Usuario.objects.filter(id=user_id.strip()).first()
            if not u:
                return error_404_view(request, mensaje=f'El usuario con ID {user_id} que intentas editar no existe.')

            u.rut = rut
            u.nombre = nombre
            u.correo = correo
            u.username = username
            u.rol = rol
            u.estado = estado
            if password:
                u.password = password
            u.save()

            # Auditoría
            registrar_auditoria(usuario, 'ACTUALIZAR', 'Usuarios', f"Actualizado usuario '{u.username}' (RUT: {u.rut}, Rol: {u.rol}, Estado: {u.estado})")

            # Si el administrador editó su propia cuenta, actualizar la sesión activa
            if usuario.get('id') == u.id:
                request.session['usuario']['nombre'] = u.nombre
                request.session['usuario']['username'] = u.username
                request.session['usuario']['rol'] = u.rol
                request.session.modified = True

            request.session['alerta_admin'] = {
                'tipo': 'success',
                'texto': f'Usuario "{u.username}" actualizado exitosamente.'
            }
        else:
            nuevo_u = Usuario.objects.create(
                rut=rut,
                nombre=nombre,
                correo=correo,
                username=username,
                password=password,
                rol=rol,
                estado=estado
            )
            registrar_auditoria(usuario, 'CREAR', 'Usuarios', f"Creado nuevo usuario '{nuevo_u.username}' (RUT: {nuevo_u.rut}, Rol: {nuevo_u.rol}, Estado: {nuevo_u.estado})")

            request.session['alerta_admin'] = {
                'tipo': 'success',
                'texto': f'Nuevo usuario "{username}" ({rol}) creado exitosamente.'
            }

        return redirect('/administrador/')

    if request.GET:
        messages.error(request, 'Manipulación detectada: No se permite enviar formularios mediante GET para evitar la exposición de campos en la URL.')
        return redirect('/administrador/')
    return error_400_view(request, mensaje='Método no permitido. Se esperaba una petición POST.')


def admin_eliminar_usuario(request, id):
    """Elimina un usuario de MySQL."""
    usuario = obtener_usuario(request)
    if not usuario:
        return error_401_view(request, mensaje='Se requiere iniciar sesión como Administrador.')
    if usuario.get('rol') != 'administrador':
        return error_403_view(request, mensaje='Acceso denegado: Solo el Administrador puede eliminar usuarios.')

    current_admin_id = request.session.get('usuario_id') or usuario.get('id')
    if current_admin_id and (id == current_admin_id or str(id) == str(current_admin_id)):
        messages.error(request, 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión')
        request.session['alerta_admin'] = {
            'tipo': 'danger',
            'texto': 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión'
        }
        return error_400_view(request, mensaje='No puedes desactivar ni modificar tu propia cuenta de administrador en sesión')

    u = Usuario.objects.filter(id=id).first()
    if not u:
        return error_404_view(request, mensaje=f'El usuario con ID {id} que intentas eliminar no existe.')

    nombre_u = u.username
    u.delete()
    registrar_auditoria(usuario, 'ELIMINAR', 'Usuarios', f"Eliminado usuario '{nombre_u}' (ID: {id})")
    request.session['alerta_admin'] = {'tipo': 'success', 'texto': f'Usuario "{nombre_u}" eliminado exitosamente.'}
    return redirect('/administrador/')


# ==============================================================================
# 6. MÓDULO DE STOCK (ACCESIBLE PARA TODOS EN MODO LECTURA; ADMIN ADMINISTRA)
# ==============================================================================

def stock_view(request):
    """
    Consulta de stock:
    - Exclusivo para Cajero (modo solo lectura) y Administrador (control y modificación total).
    - Mesero y Cocinero tienen el acceso restringido.
    - Validación y rechazo temprano de parámetros GET maliciosos o con caracteres de inyección.
    """
    usuario = obtener_usuario(request)
    if not usuario:
        return error_401_view(request, mensaje='Se requiere autenticación para consultar el catálogo de stock.')

    rol = usuario.get('rol')
    if rol not in ['cajero', 'administrador']:
        return error_403_view(request, mensaje=f'Acceso denegado: El rol "{rol}" no tiene permisos para ver el catálogo de stock.')

    # Validación de seguridad en parámetros GET (rechazo temprano sin consultar la BD)
    es_seguro, err_resp = verificar_peticion_get_segura(request, max_len=100)
    if not es_seguro:
        return err_resp

    q = request.GET.get('q', '').strip()

    # Consulta parametrizada exclusiva con el ORM de Django
    productos = Producto.objects.all().order_by('nombre')
    if q:
        productos = productos.filter(Q(nombre__icontains=q) | Q(descripcion__icontains=q))

    es_admin = (rol == 'administrador')

    context = {
        'usuario': usuario.get('nombre'),
        'rol': rol,
        'es_admin': es_admin,
        'productos': productos,
        'busqueda': q,
    }
    return render(request, 'stock.html', context)


def admin_guardar_producto(request):
    """Exclusivo Administrador: Registra o actualiza un producto con validación estricta backend."""
    usuario = obtener_usuario(request)
    if not usuario:
        return error_401_view(request, mensaje='Se requiere iniciar sesión como Administrador.')
    if usuario.get('rol') != 'administrador':
        return error_403_view(request, mensaje='Acceso denegado: Solo el Administrador puede gestionar productos.')

    if request.method != 'POST':
        if request.GET:
            messages.error(request, 'Manipulación detectada: No se permite enviar formularios mediante GET para evitar la exposición de campos en la URL.')
            return redirect('/stock/')
        return error_400_view(request, mensaje='Método no permitido. Se esperaba una petición POST.')

    prod_id = request.POST.get('prod_id', '').strip()
    nombre = request.POST.get('nombre', '').strip()
    descripcion = request.POST.get('descripcion', '').strip()
    raw_precio = request.POST.get('precio', '')
    raw_stock = request.POST.get('stock', '')

    # Validar ID de producto si existe
    if prod_id and not prod_id.isdigit():
        return error_400_view(request, mensaje='Petición incorrecta: El identificador de producto debe ser un número entero.')

    # Validar nombre del producto con validar_texto_seguro (bloquea #, $, %, !, /, &, (, ), =, :, _, ;, ', ", --, /*)
    res_nom = validar_texto_seguro(nombre, nombre_campo="nombre del producto", requerido=True, max_len=100, permitir_guion_bajo=False)
    if not res_nom.es_valido:
        return error_400_view(request, mensaje=f'Petición incorrecta: {res_nom.mensaje}')

    if len(nombre) < 3:
        return error_400_view(request, mensaje='Petición incorrecta: El nombre del producto debe contener al menos 3 caracteres.')

    # Validar descripción si se proporciona
    if descripcion:
        res_desc = validar_texto_seguro(descripcion, nombre_campo="descripción", requerido=False, max_len=255, permitir_guion_bajo=False)
        if not res_desc.es_valido:
            return error_400_view(request, mensaje=f'Petición incorrecta: {res_desc.mensaje}')

    # Validación numérica estricta mediante try/except ValueError seguro
    precio, precio_valido, msg_precio = validar_entero_estricto(raw_precio, nombre_campo="precio", permitir_cero=False)
    if not precio_valido:
        return error_400_view(request, mensaje=f'Petición incorrecta: {msg_precio}')

    stock, stock_valido, msg_stock = validar_entero_estricto(raw_stock, nombre_campo="stock", permitir_cero=True)
    if not stock_valido:
        return error_400_view(request, mensaje=f'Petición incorrecta: {msg_stock}')

    # Consultas parametrizadas con ORM de Django
    if prod_id:
        p = Producto.objects.filter(id=prod_id).first()
        if not p:
            return error_404_view(request, mensaje=f'El producto con ID {prod_id} que intentas editar no existe.')
        p.nombre = nombre
        p.descripcion = descripcion
        p.precio = precio
        p.stock = stock
        p.save()
        registrar_auditoria(usuario, 'ACTUALIZAR', 'Productos', f"Actualizado producto '{p.nombre}' (Precio: ${p.precio}, Stock: {p.stock})")
    else:
        p = Producto.objects.create(nombre=nombre, descripcion=descripcion, precio=precio, stock=stock)
        registrar_auditoria(usuario, 'CREAR', 'Productos', f"Creado producto '{p.nombre}' (Precio: ${p.precio}, Stock: {p.stock})")

    return redirect('/stock/')


def admin_agregar_stock(request):
    """
    Exclusivo Administrador: Añade unidades de reposición al stock con validación segura.
    Blindaje de método: Exige estrictamente POST. Rechaza GET u otros con 405.
    Inmunidad DevTools: Valida cantidad como entero positivo mayor a 0 (rechaza negativos, decimales y cadenas no numéricas).
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido. Se requiere POST.'}, status=405)

    usuario = obtener_usuario(request)
    if not usuario:
        return JsonResponse({'success': False, 'error': 'No autenticado'}, status=401)
    if usuario.get('rol') != 'administrador':
        return JsonResponse({'success': False, 'error': 'No autorizado'}, status=403)

    try:
        data = json.loads(request.body)
        raw_id = data.get('producto_id')
        raw_cant = data.get('cantidad_agregar')

        prod_id, id_valido, _ = validar_entero_estricto(raw_id, nombre_campo="ID de producto", permitir_cero=False)
        cantidad, cant_valida, msg_cant = validar_cantidad_entera(raw_cant, nombre_campo="cantidad a agregar")

        if not id_valido or not cant_valida:
            return JsonResponse({'success': False, 'error': msg_cant or 'Parámetros numéricos no válidos o negativos.'}, status=400)

        prod = Producto.objects.filter(id=prod_id).first()
        if prod:
            prod.stock += cantidad
            prod.save()
            registrar_auditoria(usuario, 'ACTUALIZAR', 'Productos', f"Repuesto stock de '{prod.nombre}': +{cantidad} unidades (Stock total: {prod.stock})")
            return JsonResponse({'success': True, 'nuevo_stock': prod.stock, 'message': f'Stock incrementado a {prod.stock} unidades.'})
        return JsonResponse({'success': False, 'error': 'Producto no encontrado.'}, status=404)
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Cuerpo de solicitud inválido o parámetros incorrectos.'}, status=400)


def admin_eliminar_producto(request, id):
    """Exclusivo Administrador: Elimina un producto del catálogo."""
    usuario = obtener_usuario(request)
    if not usuario:
        return error_401_view(request, mensaje='Se requiere iniciar sesión como Administrador.')
    if usuario.get('rol') != 'administrador':
        return error_403_view(request, mensaje='Acceso denegado: Solo el Administrador puede eliminar productos.')

    p = Producto.objects.filter(id=id).first()
    if not p:
        return error_404_view(request, mensaje=f'El producto con ID {id} que intentas eliminar no existe.')

    nombre_p = p.nombre
    p.delete()
    registrar_auditoria(usuario, 'ELIMINAR', 'Productos', f"Eliminado producto '{nombre_p}' (ID: {id})")
    return redirect('/stock/')


# ==============================================================================
# 7. AUDITORÍA DE VENTAS (EXCLUSIVO ADMINISTRADOR, CON TIEMPO EXACTO)
# ==============================================================================

def ventas_view(request):
    """
    Auditoría de ventas con tiempo exacto visible para el Administrador.
    - Validación y rechazo temprano de parámetros GET maliciosos o con inyección SQL.
    - Filtrado seguro por fecha mediante ORM parametrizado de Django.
    """
    usuario = obtener_usuario(request)
    if not usuario:
        return error_401_view(request, mensaje='Se requiere autenticación para auditar las ventas.')
    if usuario.get('rol') != 'administrador':
        return error_403_view(request, mensaje=f'Acceso denegado: El rol "{usuario.get("rol")}" no tiene permisos para auditar el historial de ventas.')

    # Validación de seguridad en parámetros GET (rechazo inmediato ante caracteres de inyección)
    es_seguro, err_resp = verificar_peticion_get_segura(request, max_len=100)
    if not es_seguro:
        return err_resp

    fecha_filtro = request.GET.get('fecha', '').strip()
    if fecha_filtro and not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha_filtro):
        return error_400_view(request, mensaje='Petición incorrecta: El formato de fecha para auditar ventas debe ser AAAA-MM-DD.')

    # Consultas parametrizadas exclusivas con el ORM de Django
    ventas = Venta.objects.all().order_by('-fecha')
    if fecha_filtro:
        ventas = ventas.filter(fecha__date=fecha_filtro)

    total_recaudado = sum(v.total for v in ventas)

    context = {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'ventas': ventas,
        'total_recaudado': total_recaudado,
        'fecha_filtro': fecha_filtro,
    }
    return render(request, 'ventas.html', context)


# ==============================================================================
# 8. MÓDULOS MANTENEDORES (CRUDS COMPLETOS) Y BITÁCORA DE AUDITORÍA
# ==============================================================================

def _verificar_admin(request):
    """Auxiliar para validar sesión activa de Administrador en los mantenedores."""
    usuario = obtener_usuario(request)
    if not usuario:
        return None, error_401_view(request, mensaje='Se requiere iniciar sesión como Administrador para acceder a los módulos mantenedores.')
    if usuario.get('rol') != 'administrador':
        return None, error_403_view(request, mensaje=f'Acceso denegado: El rol "{usuario.get("rol")}" no tiene permisos para acceder a los mantenedores del sistema.')
    return usuario, None


def mantenedores_hub_view(request):
    """Panel principal y centro de control de todos los módulos mantenedores."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    total_usuarios = Usuario.objects.count()
    usuarios_activos = Usuario.objects.filter(estado='activo').count()
    total_mesas = Mesa.objects.count()
    total_capacidad = Mesa.objects.aggregate(total=Sum('capacidad'))['total'] or 0
    total_pdv = PuntoDeVenta.objects.count()
    total_menus = Menu.objects.count()
    total_productos = Producto.objects.count()
    total_auditorias = HistorialAccion.objects.count()
    ultimas_acciones = HistorialAccion.objects.select_related('usuario').all().order_by('-fecha')[:10]

    context = {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'total_usuarios': total_usuarios,
        'usuarios_activos': usuarios_activos,
        'total_mesas': total_mesas,
        'total_capacidad': total_capacidad,
        'total_pdv': total_pdv,
        'total_menus': total_menus,
        'total_productos': total_productos,
        'total_auditorias': total_auditorias,
        'ultimas_acciones': ultimas_acciones,
        'seccion_activa': 'hub',
    }
    return render(request, 'mantenedores/index.html', context)


# ------------------------------------------------------------------------------
# Mantenedor: Usuarios
# ------------------------------------------------------------------------------

def mantenedor_usuarios_view(request):
    """Listado y gestión completa de usuarios con validación GET segura."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    es_seguro, err_resp = verificar_peticion_get_segura(request, max_len=100)
    if not es_seguro:
        return err_resp

    usuarios = Usuario.objects.all().order_by('id')
    alerta_mantenedor = request.session.pop('alerta_mantenedor', None)

    context = {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'usuarios': usuarios,
        'alerta_mantenedor': alerta_mantenedor,
        'seccion_activa': 'usuarios',
    }
    return render(request, 'mantenedores/usuarios/listado.html', context)


def mantenedor_usuario_registrar_view(request):
    """Formulario dedicado para registrar un nuevo usuario (registrar.html)."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    return render(request, 'mantenedores/usuarios/registrar.html', {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'seccion_activa': 'usuarios',
    })


def mantenedor_usuario_actualizar_view(request, id):
    """Formulario dedicado para actualizar un usuario existente (actualizar.html)."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    current_admin_id = request.session.get('usuario_id') or usuario.get('id')
    if current_admin_id and (id == current_admin_id or str(id) == str(current_admin_id)):
        messages.error(request, 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión')
        request.session['alerta_mantenedor'] = {
            'tipo': 'danger',
            'texto': 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión'
        }
        return redirect('/mantenedores/usuarios/')

    usuario_editar = Usuario.objects.filter(id=id).first()
    if not usuario_editar:
        messages.error(request, f'El usuario con ID {id} que intentas editar no existe.')
        return redirect('/mantenedores/usuarios/')

    return render(request, 'mantenedores/usuarios/actualizar.html', {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'usuario_editar': usuario_editar,
        'seccion_activa': 'usuarios',
    })


def mantenedor_usuario_guardar(request):
    """Creación o actualización de usuarios con inserción en HistorialAccion y messages."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    if request.method != 'POST':
        if request.GET:
            messages.error(request, 'Manipulación detectada: No se permite enviar formularios mediante GET para evitar la exposición de campos en la URL.')
            return redirect('/mantenedores/usuarios/')
        messages.error(request, 'Método no permitido. Se esperaba una petición POST.')
        return error_400_view(request, mensaje='Método no permitido. Se esperaba una petición POST.')

    user_id = request.POST.get('user_id')
    current_admin_id = request.session.get('usuario_id') or usuario.get('id')
    if user_id and str(user_id).strip():
        try:
            target_user_id = int(str(user_id).strip())
        except (ValueError, TypeError):
            messages.error(request, 'Petición incorrecta: El identificador de usuario debe ser numérico.')
            return error_400_view(request, mensaje='Petición incorrecta: El identificador de usuario debe ser numérico.')

        if current_admin_id and target_user_id == int(current_admin_id):
            messages.error(request, 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión')
            request.session['alerta_mantenedor'] = {
                'tipo': 'danger',
                'texto': 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión'
            }
            return error_400_view(request, mensaje='No puedes desactivar ni modificar tu propia cuenta de administrador en sesión')
    rut = request.POST.get('rut', '').strip()
    nombre = request.POST.get('nombre', '').strip()
    correo = request.POST.get('correo', '').strip()
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '').strip()
    rol = request.POST.get('rol', 'cajero').strip()
    estado = request.POST.get('estado', 'activo').strip()

    if not nombre or not correo or not username:
        messages.error(request, 'Petición incorrecta: Nombre, correo y nombre de usuario son campos obligatorios.')
        return error_400_view(request, mensaje='Petición incorrecta: Nombre, correo y nombre de usuario son campos obligatorios.')

    if user_id and str(user_id).strip() and not str(user_id).strip().isdigit():
        messages.error(request, 'Petición incorrecta: El identificador de usuario debe ser numérico.')
        return error_400_view(request, mensaje='Petición incorrecta: El identificador de usuario debe ser numérico.')

    res_nom = validar_texto_seguro(nombre, nombre_campo="nombre", requerido=True, max_len=100, permitir_guion_bajo=False)
    if not res_nom.es_valido:
        messages.error(request, f'Petición incorrecta: {res_nom.mensaje}')
        return error_400_view(request, mensaje=f'Petición incorrecta: {res_nom.mensaje}')

    res_usr = validar_texto_seguro(username, nombre_campo="nombre de usuario", requerido=True, max_len=50, permitir_guion_bajo=True)
    if not res_usr.es_valido:
        messages.error(request, f'Petición incorrecta: {res_usr.mensaje}')
        return error_400_view(request, mensaje=f'Petición incorrecta: {res_usr.mensaje}')

    res_cor = validar_texto_seguro(correo, nombre_campo="correo", requerido=True, max_len=100, permitir_guion_bajo=True)
    if not res_cor.es_valido:
        messages.error(request, f'Petición incorrecta: {res_cor.mensaje}')
        return error_400_view(request, mensaje=f'Petición incorrecta: {res_cor.mensaje}')

    if rut:
        res_rut = validar_texto_seguro(rut, nombre_campo="RUT", requerido=False, max_len=20, permitir_guion_bajo=False)
        if not res_rut.es_valido:
            messages.error(request, f'Petición incorrecta: {res_rut.mensaje}')
            return error_400_view(request, mensaje=f'Petición incorrecta: {res_rut.mensaje}')

    if password:
        res_pwd = validar_texto_seguro(password, nombre_campo="contraseña", requerido=False, max_len=128, permitir_guion_bajo=True)
        if not res_pwd.es_valido:
            messages.error(request, f'Petición incorrecta: {res_pwd.mensaje}')
            return error_400_view(request, mensaje=f'Petición incorrecta: {res_pwd.mensaje}')

    if rol not in ['administrador', 'cajero', 'mesero', 'cocinero']:
        messages.error(request, f'Petición incorrecta: El rol "{rol}" no es válido en el sistema.')
        return error_400_view(request, mensaje=f'Petición incorrecta: El rol "{rol}" no es válido en el sistema.')

    if estado not in ['activo', 'inactivo']:
        estado = 'activo'

    # Validar unicidad de username
    qs_duplicado = Usuario.objects.filter(username=username)
    if user_id:
        qs_duplicado = qs_duplicado.exclude(id=user_id)
    if qs_duplicado.exists():
        mensaje_error = f'El nombre de usuario "@{username}" ya está registrado por otro colaborador.'
        messages.error(request, mensaje_error)
        request.session['alerta_mantenedor'] = {'tipo': 'danger', 'texto': mensaje_error}
        return redirect('/mantenedores/usuarios/')

    # Reautenticación de seguridad para otorgar rol Administrador
    current_admin_id = usuario.get('id')
    es_crear_otro_admin = (rol == 'administrador' and (not user_id or str(user_id).strip() != str(current_admin_id)))
    if es_crear_otro_admin:
        confirm_user = request.POST.get('admin_confirm_username', '').strip()
        confirm_pass = request.POST.get('admin_confirm_password', '').strip()
        admin_actual = Usuario.objects.filter(id=current_admin_id).first()
        if not admin_actual or admin_actual.password != confirm_pass or (admin_actual.username != confirm_user and admin_actual.correo != confirm_user):
            mensaje_sec = 'Confirmación de seguridad denegada: Credenciales de Administrador incorrectas.'
            messages.error(request, mensaje_sec)
            request.session['alerta_mantenedor'] = {'tipo': 'danger', 'texto': mensaje_sec}
            return redirect('/mantenedores/usuarios/')

    if user_id and str(user_id).strip():
        u = Usuario.objects.filter(id=user_id.strip()).first()
        if not u:
            messages.error(request, f'El usuario con ID {user_id} que intentas editar no existe.')
            return error_404_view(request, mensaje=f'El usuario con ID {user_id} que intentas editar no existe.')

        u.rut = rut
        u.nombre = nombre
        u.correo = correo
        u.username = username
        u.rol = rol
        u.estado = estado
        if password:
            u.password = password
        u.save()

        registrar_auditoria(usuario, 'ACTUALIZAR', 'Usuarios', f"Actualizado usuario '{u.username}' (RUT: {u.rut}, Rol: {u.rol}, Estado: {u.estado})")

        if usuario.get('id') == u.id:
            request.session['usuario']['nombre'] = u.nombre
            request.session['usuario']['username'] = u.username
            request.session['usuario']['rol'] = u.rol
            request.session.modified = True

        msg_exito = f'Usuario "@{u.username}" ({u.rol}) actualizado exitosamente.'
        messages.success(request, msg_exito)
        request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_exito}
    else:
        if not password:
            messages.error(request, 'Petición incorrecta: La contraseña es obligatoria para un usuario nuevo.')
            return error_400_view(request, mensaje='Petición incorrecta: La contraseña es obligatoria para un usuario nuevo.')

        nuevo_u = Usuario.objects.create(
            rut=rut,
            nombre=nombre,
            correo=correo,
            username=username,
            password=password,
            rol=rol,
            estado=estado
        )
        registrar_auditoria(usuario, 'CREAR', 'Usuarios', f"Creado nuevo usuario '{nuevo_u.username}' (RUT: {nuevo_u.rut}, Rol: {nuevo_u.rol}, Estado: {nuevo_u.estado})")

        msg_exito = f'Nuevo usuario "@{username}" ({rol}) registrado exitosamente.'
        messages.success(request, msg_exito)
        request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_exito}

    return redirect('/mantenedores/usuarios/')


def mantenedor_usuario_eliminar(request, id):
    """Elimina un usuario y registra la acción en HistorialAccion y messages."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    current_admin_id = request.session.get('usuario_id') or usuario.get('id')
    if current_admin_id and (id == current_admin_id or str(id) == str(current_admin_id)):
        messages.error(request, 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión')
        request.session['alerta_mantenedor'] = {
            'tipo': 'danger',
            'texto': 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión'
        }
        return error_400_view(request, mensaje='No puedes desactivar ni modificar tu propia cuenta de administrador en sesión')

    u = Usuario.objects.filter(id=id).first()
    if not u:
        messages.error(request, f'El usuario con ID {id} que intentas eliminar no existe.')
        return error_404_view(request, mensaje=f'El usuario con ID {id} que intentas eliminar no existe.')

    nombre_u = u.username
    u.delete()
    registrar_auditoria(usuario, 'ELIMINAR', 'Usuarios', f"Eliminado usuario '{nombre_u}' (ID: {id})")

    msg_del = f'Usuario "@{nombre_u}" eliminado del sistema exitosamente.'
    messages.success(request, msg_del)
    request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_del}
    return redirect('/mantenedores/usuarios/')


# ------------------------------------------------------------------------------
# Mantenedor: Mesas
# ------------------------------------------------------------------------------

def mantenedor_mesas_view(request):
    """Listado y gestión completa de mesas del salón con validación GET segura."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    es_seguro, err_resp = verificar_peticion_get_segura(request, max_len=100)
    if not es_seguro:
        return err_resp

    mesas = Mesa.objects.all().order_by('numero')
    alerta_mantenedor = request.session.pop('alerta_mantenedor', None)

    context = {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'mesas': mesas,
        'alerta_mantenedor': alerta_mantenedor,
        'seccion_activa': 'mesas',
    }
    return render(request, 'mantenedores/mesas/listado.html', context)


def mantenedor_mesa_registrar_view(request):
    """Formulario dedicado para registrar una nueva mesa (registrar.html)."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    return render(request, 'mantenedores/mesas/registrar.html', {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'seccion_activa': 'mesas',
    })


def mantenedor_mesa_actualizar_view(request, id):
    """Formulario dedicado para actualizar una mesa existente (actualizar.html)."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    mesa_editar = Mesa.objects.filter(id=id).first()
    if not mesa_editar:
        messages.error(request, f'La mesa con ID {id} no existe.')
        return redirect('/mantenedores/mesas/')

    return render(request, 'mantenedores/mesas/actualizar.html', {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'mesa_editar': mesa_editar,
        'seccion_activa': 'mesas',
    })


def mantenedor_mesa_guardar(request):
    """Creación o edición de mesas con registro en HistorialAccion y messages."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    if request.method != 'POST':
        if request.GET:
            messages.error(request, 'Manipulación detectada: No se permite enviar formularios mediante GET para evitar la exposición de campos en la URL.')
            return redirect('/mantenedores/mesas/')
        messages.error(request, 'Método no permitido. Se esperaba una petición POST.')
        return error_400_view(request, mensaje='Método no permitido. Se esperaba una petición POST.')

    mesa_id = request.POST.get('mesa_id', '').strip()
    nombre = request.POST.get('nombre', '').strip()
    raw_numero = request.POST.get('numero', '')
    raw_capacidad = request.POST.get('capacidad', '4')
    estado = request.POST.get('estado', 'disponible').strip()

    if mesa_id and not mesa_id.isdigit():
        messages.error(request, 'Petición incorrecta: El identificador de mesa debe ser numérico.')
        return error_400_view(request, mensaje='Petición incorrecta: El identificador de mesa debe ser numérico.')

    res_nom = validar_texto_seguro(nombre, nombre_campo="nombre descriptivo de la mesa", requerido=True, max_len=100, permitir_guion_bajo=False)
    if not res_nom.es_valido:
        messages.error(request, f'Petición incorrecta: {res_nom.mensaje}')
        return error_400_view(request, mensaje=f'Petición incorrecta: {res_nom.mensaje}')

    if not str(raw_numero).strip():
        messages.error(request, 'Petición incorrecta: El número de mesa es obligatorio.')
        return error_400_view(request, mensaje='Petición incorrecta: El número de mesa es obligatorio.')

    numero, num_valido, msg_num = validar_entero_estricto(raw_numero, nombre_campo="número de mesa", permitir_cero=False)
    if not num_valido:
        messages.error(request, f'Petición incorrecta: {msg_num}')
        return error_400_view(request, mensaje=f'Petición incorrecta: {msg_num}')

    capacidad, cap_valida, msg_cap = validar_entero_estricto(raw_capacidad, nombre_campo="capacidad de comensales", permitir_cero=False)
    if not cap_valida:
        messages.error(request, f'Petición incorrecta: {msg_cap}')
        return error_400_view(request, mensaje=f'Petición incorrecta: {msg_cap}')

    if estado not in ['disponible', 'ocupada', 'reservada']:
        estado = 'disponible'

    # Verificar unicidad del número de mesa
    qs_duplicado = Mesa.objects.filter(numero=numero)
    if mesa_id:
        qs_duplicado = qs_duplicado.exclude(id=mesa_id)
    if qs_duplicado.exists():
        msg_dup = f'Ya existe una mesa con el número #{numero} en el restaurante.'
        messages.error(request, msg_dup)
        request.session['alerta_mantenedor'] = {'tipo': 'danger', 'texto': msg_dup}
        return redirect('/mantenedores/mesas/')

    if mesa_id and str(mesa_id).strip():
        m = Mesa.objects.filter(id=mesa_id.strip()).first()
        if not m:
            messages.error(request, f'La mesa con ID {mesa_id} que intentas editar no existe.')
            return error_404_view(request, mensaje=f'La mesa con ID {mesa_id} que intentas editar no existe.')

        m.numero = numero
        m.nombre = nombre
        m.capacidad = capacidad
        m.estado = estado
        m.save()

        registrar_auditoria(usuario, 'ACTUALIZAR', 'Mesas', f"Actualizada Mesa #{m.numero} '{m.nombre}' (Capacidad: {m.capacidad}, Estado: {m.estado})")

        msg_exito = f'Mesa #{m.numero} "{m.nombre}" actualizada exitosamente.'
        messages.success(request, msg_exito)
        request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_exito}
    else:
        m = Mesa.objects.create(
            numero=numero,
            nombre=nombre,
            capacidad=capacidad,
            estado=estado
        )
        registrar_auditoria(usuario, 'CREAR', 'Mesas', f"Creada nueva Mesa #{m.numero} '{m.nombre}' (Capacidad: {m.capacidad}, Estado: {m.estado})")

        msg_exito = f'Mesa #{m.numero} "{m.nombre}" creada exitosamente.'
        messages.success(request, msg_exito)
        request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_exito}

    return redirect('/mantenedores/mesas/')


def mantenedor_mesa_eliminar(request, id):
    """Elimina una mesa y registra la acción en HistorialAccion y messages."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    m = Mesa.objects.filter(id=id).first()
    if not m:
        messages.error(request, f'La mesa con ID {id} que intentas eliminar no existe.')
        return error_404_view(request, mensaje=f'La mesa con ID {id} que intentas eliminar no existe.')

    num = m.numero
    nom = m.nombre
    m.delete()
    registrar_auditoria(usuario, 'ELIMINAR', 'Mesas', f"Eliminada Mesa #{num} '{nom}' (ID: {id})")

    msg_del = f'Mesa #{num} "{nom}" eliminada del salón exitosamente.'
    messages.success(request, msg_del)
    request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_del}
    return redirect('/mantenedores/mesas/')


# ------------------------------------------------------------------------------
# Mantenedor: Puntos de Venta (POS)
# ------------------------------------------------------------------------------

def mantenedor_puntos_venta_view(request):
    """Listado y gestión completa de puntos de venta (cajas registradoras) con validación GET segura."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    es_seguro, err_resp = verificar_peticion_get_segura(request, max_len=100)
    if not es_seguro:
        return err_resp

    puntos_venta = PuntoDeVenta.objects.all().order_by('id')
    alerta_mantenedor = request.session.pop('alerta_mantenedor', None)

    context = {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'puntos_venta': puntos_venta,
        'alerta_mantenedor': alerta_mantenedor,
        'seccion_activa': 'puntos_venta',
    }
    return render(request, 'mantenedores/puntos_venta/listado.html', context)


def mantenedor_punto_venta_registrar_view(request):
    """Formulario dedicado para registrar un nuevo punto de venta (registrar.html)."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    return render(request, 'mantenedores/puntos_venta/registrar.html', {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'seccion_activa': 'puntos_venta',
    })


def mantenedor_punto_venta_actualizar_view(request, id):
    """Formulario dedicado para actualizar un punto de venta existente (actualizar.html)."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    pdv_editar = PuntoDeVenta.objects.filter(id=id).first()
    if not pdv_editar:
        messages.error(request, f'El punto de venta con ID {id} no existe.')
        return redirect('/mantenedores/puntos-de-venta/')

    return render(request, 'mantenedores/puntos_venta/actualizar.html', {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'pdv_editar': pdv_editar,
        'seccion_activa': 'puntos_venta',
    })


def mantenedor_punto_venta_guardar(request):
    """Creación o actualización de puntos de venta con registro en HistorialAccion y messages."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    if request.method != 'POST':
        if request.GET:
            messages.error(request, 'Manipulación detectada: No se permite enviar formularios mediante GET para evitar la exposición de campos en la URL.')
            return redirect('/mantenedores/puntos-de-venta/')
        messages.error(request, 'Método no permitido. Se esperaba una petición POST.')
        return error_400_view(request, mensaje='Método no permitido. Se esperaba una petición POST.')

    pdv_id = request.POST.get('pdv_id', '').strip()
    nombre = request.POST.get('nombre', '').strip()
    ubicacion = request.POST.get('ubicacion', '').strip()
    estado = request.POST.get('estado', 'activo').strip()

    if pdv_id and not pdv_id.isdigit():
        messages.error(request, 'Petición incorrecta: El identificador de punto de venta debe ser numérico.')
        return error_400_view(request, mensaje='Petición incorrecta: El identificador de punto de venta debe ser numérico.')

    res_nom = validar_texto_seguro(nombre, nombre_campo="nombre o identificador del punto de venta", requerido=True, max_len=100, permitir_guion_bajo=False)
    if not res_nom.es_valido:
        messages.error(request, f'Petición incorrecta: {res_nom.mensaje}')
        return error_400_view(request, mensaje=f'Petición incorrecta: {res_nom.mensaje}')

    if ubicacion:
        res_ubi = validar_texto_seguro(ubicacion, nombre_campo="ubicación", requerido=False, max_len=150, permitir_guion_bajo=False)
        if not res_ubi.es_valido:
            messages.error(request, f'Petición incorrecta: {res_ubi.mensaje}')
            return error_400_view(request, mensaje=f'Petición incorrecta: {res_ubi.mensaje}')

    if estado not in ['activo', 'inactivo']:
        estado = 'activo'

    if pdv_id and str(pdv_id).strip():
        pv = PuntoDeVenta.objects.filter(id=pdv_id.strip()).first()
        if not pv:
            messages.error(request, f'El punto de venta con ID {pdv_id} no existe.')
            return error_404_view(request, mensaje=f'El punto de venta con ID {pdv_id} no existe.')

        pv.nombre = nombre
        pv.ubicacion = ubicacion
        pv.estado = estado
        pv.save()

        registrar_auditoria(usuario, 'ACTUALIZAR', 'Puntos de Venta', f"Actualizado Punto de Venta #{pv.id} '{pv.nombre}' ({pv.ubicacion or 'Sin ubicación'}, Estado: {pv.estado})")

        msg_exito = f'Punto de venta "{pv.nombre}" actualizado exitosamente.'
        messages.success(request, msg_exito)
        request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_exito}
    else:
        pv = PuntoDeVenta.objects.create(
            nombre=nombre,
            ubicacion=ubicacion,
            estado=estado
        )
        registrar_auditoria(usuario, 'CREAR', 'Puntos de Venta', f"Creado nuevo Punto de Venta '{pv.nombre}' ({pv.ubicacion or 'Sin ubicación'}, Estado: {pv.estado})")

        msg_exito = f'Punto de venta "{pv.nombre}" registrado exitosamente.'
        messages.success(request, msg_exito)
        request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_exito}

    return redirect('/mantenedores/puntos-de-venta/')


def mantenedor_punto_venta_eliminar(request, id):
    """Elimina un punto de venta y registra en HistorialAccion y messages."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    pv = PuntoDeVenta.objects.filter(id=id).first()
    if not pv:
        messages.error(request, f'El punto de venta con ID {id} que intentas eliminar no existe.')
        return error_404_view(request, mensaje=f'El punto de venta con ID {id} que intentas eliminar no existe.')

    nom = pv.nombre
    pv.delete()
    registrar_auditoria(usuario, 'ELIMINAR', 'Puntos de Venta', f"Eliminado Punto de Venta '{nom}' (ID: {id})")

    msg_del = f'Punto de venta "{nom}" eliminado exitosamente.'
    messages.success(request, msg_del)
    request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_del}
    return redirect('/mantenedores/puntos-de-venta/')


# ------------------------------------------------------------------------------
# Mantenedor: Menús (Categorías de la Carta)
# ------------------------------------------------------------------------------

def mantenedor_menus_view(request):
    """Listado y gestión completa de categorías del menú gastronómico con validación GET segura."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    es_seguro, err_resp = verificar_peticion_get_segura(request, max_len=100)
    if not es_seguro:
        return err_resp

    menus = Menu.objects.annotate(total_productos=Count('productos')).order_by('id')
    alerta_mantenedor = request.session.pop('alerta_mantenedor', None)

    context = {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'menus': menus,
        'alerta_mantenedor': alerta_mantenedor,
        'seccion_activa': 'menus',
    }
    return render(request, 'mantenedores/menus/listado.html', context)


def mantenedor_menu_registrar_view(request):
    """Formulario dedicado para registrar una nueva categoría de menú (registrar.html)."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    return render(request, 'mantenedores/menus/registrar.html', {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'seccion_activa': 'menus',
    })


def mantenedor_menu_actualizar_view(request, id):
    """Formulario dedicado para actualizar una categoría de menú existente (actualizar.html)."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    menu_editar = Menu.objects.filter(id=id).first()
    if not menu_editar:
        messages.error(request, f'La categoría de menú con ID {id} no existe.')
        return redirect('/mantenedores/menus/')

    return render(request, 'mantenedores/menus/actualizar.html', {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'menu_editar': menu_editar,
        'seccion_activa': 'menus',
    })


def mantenedor_menu_guardar(request):
    """Creación o actualización de menús con registro en HistorialAccion y messages."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    if request.method != 'POST':
        if request.GET:
            messages.error(request, 'Manipulación detectada: No se permite enviar formularios mediante GET para evitar la exposición de campos en la URL.')
            return redirect('/mantenedores/menus/')
        messages.error(request, 'Método no permitido. Se esperaba una petición POST.')
        return error_400_view(request, mensaje='Método no permitido. Se esperaba una petición POST.')

    menu_id = request.POST.get('menu_id', '').strip()
    nombre = request.POST.get('nombre', '').strip()
    descripcion = request.POST.get('descripcion', '').strip()
    estado = request.POST.get('estado', 'activo').strip()

    if menu_id and not menu_id.isdigit():
        messages.error(request, 'Petición incorrecta: El identificador de menú debe ser numérico.')
        return error_400_view(request, mensaje='Petición incorrecta: El identificador de menú debe ser numérico.')

    res_nom = validar_texto_seguro(nombre, nombre_campo="nombre de la sección de menú", requerido=True, max_len=100, permitir_guion_bajo=False)
    if not res_nom.es_valido:
        messages.error(request, f'Petición incorrecta: {res_nom.mensaje}')
        return error_400_view(request, mensaje=f'Petición incorrecta: {res_nom.mensaje}')

    if descripcion:
        res_desc = validar_texto_seguro(descripcion, nombre_campo="descripción del menú", requerido=False, max_len=250, permitir_guion_bajo=False)
        if not res_desc.es_valido:
            messages.error(request, f'Petición incorrecta: {res_desc.mensaje}')
            return error_400_view(request, mensaje=f'Petición incorrecta: {res_desc.mensaje}')

    if estado not in ['activo', 'inactivo']:
        estado = 'activo'

    if menu_id and str(menu_id).strip():
        mn = Menu.objects.filter(id=menu_id.strip()).first()
        if not mn:
            messages.error(request, f'La categoría de menú con ID {menu_id} no existe.')
            return error_404_view(request, mensaje=f'La categoría de menú con ID {menu_id} no existe.')

        mn.nombre = nombre
        mn.descripcion = descripcion
        mn.estado = estado
        mn.save()

        registrar_auditoria(usuario, 'ACTUALIZAR', 'Menús', f"Actualizada categoría de Menú #{mn.id} '{mn.nombre}' (Estado: {mn.estado})")

        msg_exito = f'Categoría de menú "{mn.nombre}" actualizada exitosamente.'
        messages.success(request, msg_exito)
        request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_exito}
    else:
        mn = Menu.objects.create(
            nombre=nombre,
            descripcion=descripcion,
            estado=estado
        )
        registrar_auditoria(usuario, 'CREAR', 'Menús', f"Creada nueva categoría de Menú '{mn.nombre}' (Estado: {mn.estado})")

        msg_exito = f'Categoría de menú "{mn.nombre}" creada exitosamente.'
        messages.success(request, msg_exito)
        request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_exito}

    return redirect('/mantenedores/menus/')


def mantenedor_menu_eliminar(request, id):
    """Elimina una categoría de menú y registra en HistorialAccion y messages."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    mn = Menu.objects.filter(id=id).first()
    if not mn:
        messages.error(request, f'La categoría de menú con ID {id} que intentas eliminar no existe.')
        return error_404_view(request, mensaje=f'La categoría de menú con ID {id} que intentas eliminar no existe.')

    nom = mn.nombre
    mn.delete()
    registrar_auditoria(usuario, 'ELIMINAR', 'Menús', f"Eliminada categoría de Menú '{nom}' (ID: {id})")

    msg_del = f'Categoría de menú "{nom}" eliminada exitosamente.'
    messages.success(request, msg_del)
    request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_del}
    return redirect('/mantenedores/menus/')


# ------------------------------------------------------------------------------
# Mantenedor: Productos
# ------------------------------------------------------------------------------

def mantenedor_productos_view(request):
    """Listado y gestión completa del catálogo de productos con validación GET segura."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    # Validación y rechazo temprano de parámetros GET maliciosos
    es_seguro, err_resp = verificar_peticion_get_segura(request, max_len=100)
    if not es_seguro:
        return err_resp

    q = request.GET.get('q', '').strip()
    menu_filtro = request.GET.get('menu_id', '').strip()
    if menu_filtro and not menu_filtro.isdigit():
        return error_400_view(request, mensaje='Petición incorrecta: El identificador de categoría/menú debe ser numérico.')

    productos = Producto.objects.select_related('menu').all().order_by('nombre')
    if q:
        productos = productos.filter(Q(nombre__icontains=q) | Q(descripcion__icontains=q) | Q(codigo__icontains=q))
    if menu_filtro:
        productos = productos.filter(menu_id=int(menu_filtro))

    menus = Menu.objects.all().order_by('nombre')
    alerta_mantenedor = request.session.pop('alerta_mantenedor', None)

    context = {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'productos': productos,
        'menus': menus,
        'alerta_mantenedor': alerta_mantenedor,
        'busqueda': q,
        'menu_filtro': menu_filtro,
        'seccion_activa': 'productos',
    }
    return render(request, 'mantenedores/productos/listado.html', context)


def mantenedor_producto_registrar_view(request):
    """Formulario dedicado para registrar un nuevo producto (registrar.html)."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    menus = Menu.objects.filter(estado='activo').order_by('nombre')
    return render(request, 'mantenedores/productos/registrar.html', {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'menus': menus,
        'seccion_activa': 'productos',
    })


def mantenedor_producto_actualizar_view(request, id):
    """Formulario dedicado para actualizar un producto existente (actualizar.html)."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    producto_editar = Producto.objects.filter(id=id).first()
    if not producto_editar:
        messages.error(request, f'El producto con ID {id} no existe.')
        return redirect('/mantenedores/productos/')

    menus = Menu.objects.all().order_by('nombre')
    return render(request, 'mantenedores/productos/actualizar.html', {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'producto_editar': producto_editar,
        'menus': menus,
        'seccion_activa': 'productos',
    })


def mantenedor_producto_guardar(request):
    """Creación o actualización de productos con validación estricta backend y consultas parametrizadas."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    if request.method != 'POST':
        if request.GET:
            messages.error(request, 'Manipulación detectada: No se permite enviar formularios mediante GET para evitar la exposición de campos en la URL.')
            return redirect('/mantenedores/productos/')
        messages.error(request, 'Método no permitido. Se esperaba una petición POST.')
        return error_400_view(request, mensaje='Método no permitido. Se esperaba una petición POST.')

    prod_id = request.POST.get('prod_id', '').strip()
    codigo = request.POST.get('codigo', '').strip()
    nombre = request.POST.get('nombre', '').strip()
    descripcion = request.POST.get('descripcion', '').strip()
    menu_id = request.POST.get('menu_id', '').strip()
    raw_precio = request.POST.get('precio', '')
    raw_stock = request.POST.get('stock', '')

    # Validar IDs numéricos si se proporcionan
    if prod_id and not prod_id.isdigit():
        messages.error(request, 'Petición incorrecta: El identificador de producto debe ser un número entero.')
        return error_400_view(request, mensaje='Petición incorrecta: El identificador de producto debe ser un número entero.')

    if menu_id and not menu_id.isdigit():
        messages.error(request, 'Petición incorrecta: El identificador de menú/categoría debe ser un número entero.')
        return error_400_view(request, mensaje='Petición incorrecta: El identificador de menú/categoría debe ser un número entero.')

    # Validar nombre del producto con validar_texto_seguro (bloquea #, $, %, !, /, &, (, ), =, :, _, ;, ', ", --, /*)
    res_nom = validar_texto_seguro(nombre, nombre_campo="nombre del producto", requerido=True, max_len=100, permitir_guion_bajo=False)
    if not res_nom.es_valido:
        messages.error(request, f'Petición incorrecta: {res_nom.mensaje}')
        return error_400_view(request, mensaje=f'Petición incorrecta: {res_nom.mensaje}')

    if len(nombre) < 3:
        messages.error(request, 'Petición incorrecta: El nombre del producto debe contener entre 3 y 100 caracteres.')
        return error_400_view(request, mensaje='Petición incorrecta: El nombre del producto debe contener entre 3 y 100 caracteres.')

    if descripcion:
        res_desc = validar_texto_seguro(descripcion, nombre_campo="descripción", requerido=False, max_len=255, permitir_guion_bajo=False)
        if not res_desc.es_valido:
            messages.error(request, f'Petición incorrecta: {res_desc.mensaje}')
            return error_400_view(request, mensaje=f'Petición incorrecta: {res_desc.mensaje}')

    if codigo:
        res_cod = validar_texto_seguro(codigo, nombre_campo="código SKU", requerido=False, max_len=50, permitir_guion_bajo=True)
        if not res_cod.es_valido:
            messages.error(request, f'Petición incorrecta: {res_cod.mensaje}')
            return error_400_view(request, mensaje=f'Petición incorrecta: {res_cod.mensaje}')

    # Validación numérica estricta para precio y stock mediante try/except ValueError seguro
    precio, precio_valido, msg_precio = validar_entero_estricto(raw_precio, nombre_campo="precio", permitir_cero=False)
    if not precio_valido:
        messages.error(request, f'Petición incorrecta: {msg_precio}')
        return error_400_view(request, mensaje=f'Petición incorrecta: {msg_precio}')

    stock, stock_valido, msg_stock = validar_entero_estricto(raw_stock, nombre_campo="stock", permitir_cero=True)
    if not stock_valido:
        messages.error(request, f'Petición incorrecta: {msg_stock}')
        return error_400_view(request, mensaje=f'Petición incorrecta: {msg_stock}')

    # Consultas parametrizadas seguras mediante ORM de Django
    menu_obj = None
    if menu_id:
        menu_obj = Menu.objects.filter(id=int(menu_id)).first()

    if prod_id:
        p = Producto.objects.filter(id=int(prod_id)).first()
        if not p:
            messages.error(request, f'El producto con ID {prod_id} no existe.')
            return error_404_view(request, mensaje=f'El producto con ID {prod_id} no existe.')

        p.codigo = codigo
        p.nombre = nombre
        p.descripcion = descripcion
        p.precio = precio
        p.stock = stock
        p.menu = menu_obj
        p.save()

        menu_nombre = p.menu.nombre if p.menu else 'Sin categoría'
        registrar_auditoria(usuario, 'ACTUALIZAR', 'Productos', f"Actualizado producto '{p.nombre}' (Código: {p.codigo or 'N/A'}, Precio: ${p.precio}, Stock: {p.stock}, Menú: {menu_nombre})")

        msg_exito = f'Producto "{p.nombre}" actualizado exitosamente.'
        messages.success(request, msg_exito)
        request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_exito}
    else:
        p = Producto.objects.create(
            codigo=codigo,
            nombre=nombre,
            descripcion=descripcion,
            precio=precio,
            stock=stock,
            menu=menu_obj
        )
        menu_nombre = p.menu.nombre if p.menu else 'Sin categoría'
        registrar_auditoria(usuario, 'CREAR', 'Productos', f"Creado nuevo producto '{p.nombre}' (Código: {p.codigo or 'N/A'}, Precio: ${p.precio}, Stock: {p.stock}, Menú: {menu_nombre})")

        msg_exito = f'Producto "{p.nombre}" registrado exitosamente en el catálogo.'
        messages.success(request, msg_exito)
        request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_exito}

    return redirect('/mantenedores/productos/')


def mantenedor_producto_eliminar(request, id):
    """Elimina un producto y registra en HistorialAccion y messages."""
    usuario, err = _verificar_admin(request)
    if err:
        return err

    p = Producto.objects.filter(id=id).first()
    if not p:
        messages.error(request, f'El producto con ID {id} que intentas eliminar no existe.')
        return error_404_view(request, mensaje=f'El producto con ID {id} que intentas eliminar no existe.')

    nom = p.nombre
    p.delete()
    registrar_auditoria(usuario, 'ELIMINAR', 'Productos', f"Eliminado producto '{nom}' (ID: {id})")

    msg_del = f'Producto "{nom}" eliminado del catálogo exitosamente.'
    messages.success(request, msg_del)
    request.session['alerta_mantenedor'] = {'tipo': 'success', 'texto': msg_del}
    return redirect('/mantenedores/productos/')


# ------------------------------------------------------------------------------
# Bitácora de Auditoría (HistorialAccion): Listado y Filtros
# ------------------------------------------------------------------------------

def mantenedor_auditoria_view(request):
    """
    Vista para listar y filtrar el historial de acciones y auditoría:
    - Validación estricta y rechazo temprano de parámetros GET maliciosos o con inyección SQL.
    - Limpieza con .strip() antes de procesar y verificación de formatos esperados.
    - Filtro por acción (CREAR, ACTUALIZAR, ELIMINAR, LOGIN, CIERRE_CAJA).
    - Filtro por módulo (Usuarios, Mesas, Puntos de Venta, Menús, Productos, etc.).
    - Filtro por usuario responsable.
    - Filtro por rango de fechas (fecha desde / hasta).
    - Búsqueda textual en detalle y nombres.
    - Consultas exclusivamente parametrizadas mediante el ORM de Django.
    """
    usuario, err = _verificar_admin(request)
    if err:
        return err

    # 1. Validación de seguridad en todos los parámetros GET recibidos (rechazo inmediato ante inyección)
    es_seguro, err_resp = verificar_peticion_get_segura(request, max_len=100)
    if not es_seguro:
        return err_resp

    # 2. Sanitización con .strip()
    filtro_accion = request.GET.get('accion', '').strip()
    filtro_modulo = request.GET.get('modulo', '').strip()
    filtro_usuario = request.GET.get('usuario_id', '').strip()
    filtro_fecha_desde = request.GET.get('fecha_desde', '').strip()
    filtro_fecha_hasta = request.GET.get('fecha_hasta', '').strip()
    busqueda = request.GET.get('q', '').strip()

    # 3. Validación de formatos específicos antes de consultar la Base de Datos
    if filtro_usuario and not filtro_usuario.isdigit():
        return error_400_view(request, mensaje='Petición incorrecta: El identificador de usuario debe ser numérico.')

    formato_fecha = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    if filtro_fecha_desde and not formato_fecha.match(filtro_fecha_desde):
        return error_400_view(request, mensaje='Petición incorrecta: El formato de "fecha_desde" debe ser AAAA-MM-DD.')

    if filtro_fecha_hasta and not formato_fecha.match(filtro_fecha_hasta):
        return error_400_view(request, mensaje='Petición incorrecta: El formato de "fecha_hasta" debe ser AAAA-MM-DD.')

    # 4. Consultas parametrizadas exclusivas con el ORM de Django (blindaje SQL)
    qs = HistorialAccion.objects.select_related('usuario').all()

    if filtro_accion:
        qs = qs.filter(accion=filtro_accion)

    if filtro_modulo:
        qs = qs.filter(modulo=filtro_modulo)

    if filtro_usuario:
        qs = qs.filter(usuario_id=int(filtro_usuario))

    if filtro_fecha_desde:
        qs = qs.filter(fecha__date__gte=filtro_fecha_desde)

    if filtro_fecha_hasta:
        qs = qs.filter(fecha__date__lte=filtro_fecha_hasta)

    if busqueda:
        qs = qs.filter(
            Q(detalle__icontains=busqueda) |
            Q(usuario__nombre__icontains=busqueda) |
            Q(usuario__username__icontains=busqueda)
        )

    historial = qs.order_by('-fecha')[:250]
    lista_usuarios = Usuario.objects.all().order_by('nombre')

    context = {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'historial': historial,
        'lista_usuarios': lista_usuarios,
        'filtro_accion': filtro_accion,
        'filtro_modulo': filtro_modulo,
        'filtro_usuario': filtro_usuario,
        'filtro_fecha_desde': filtro_fecha_desde,
        'filtro_fecha_hasta': filtro_fecha_hasta,
        'busqueda': busqueda,
        'seccion_activa': 'auditoria',
    }
    return render(request, 'mantenedores/auditoria.html', context)



