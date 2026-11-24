import re
import time
import json
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import JsonResponse, HttpResponseNotAllowed, Http404
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import DatabaseError, transaction
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib import messages
from django.db.models import Sum, Count, Avg, Q, DateField
from django.db.models.functions import Cast, Coalesce
from Safari.models import (
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
    obtener_siguiente_folio,
)
from Safari.auth_utils import (
    validar_texto_seguro,
    ResultadoValidacionTexto,
    REGEX_CARACTERES_PROHIBIDOS_ESTRICTO,
    REGEX_CARACTERES_PROHIBIDOS_IDENTIFICADOR,
    REGEX_SQL_INJECTION,
)

from .common import (
    sanitizar_cadena,
    MAX_INTENTOS_LOGIN,
    BLOQUEO_SEGUNDOS,
)


def obtener_usuario(request):
    """Retorna los datos del usuario en sesión o None si no hay sesión."""
    u = request.session.get('usuario')
    if u and isinstance(u, dict) and 'id' in u:
        if 'usuario_id' not in request.session:
            request.session['usuario_id'] = u['id']
    return u


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


