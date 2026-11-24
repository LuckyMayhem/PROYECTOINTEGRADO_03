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
    sanitizar_texto_defensivo,
    validar_cantidad_entera,
    validar_parametro_get_seguro,
    verificar_peticion_get_segura,
    validar_entero_estricto,
)
from .auth import obtener_usuario
from .admin_panel import (
    _verificar_admin,
    error_400_view,
    error_401_view,
    error_403_view,
    error_404_view,
)


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

    # Validación numérica estricta para precio (100 a 9.999.999 CLP) y stock (0 a 99.999 unidades)
    precio, precio_valido, msg_precio = validar_entero_estricto(raw_precio, nombre_campo="precio", permitir_cero=False, min_val=100, max_val=9999999)
    if not precio_valido:
        messages.error(request, f'Petición incorrecta: {msg_precio}')
        return error_400_view(request, mensaje=f'Petición incorrecta: {msg_precio}')

    stock, stock_valido, msg_stock = validar_entero_estricto(raw_stock, nombre_campo="stock", permitir_cero=True, min_val=0, max_val=99999)
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

    # Validación numérica estricta para precio (100 a 9.999.999 CLP) y stock (0 a 99.999 unidades)
    precio, precio_valido, msg_precio = validar_entero_estricto(raw_precio, nombre_campo="precio", permitir_cero=False, min_val=100, max_val=9999999)
    if not precio_valido:
        return error_400_view(request, mensaje=f'Petición incorrecta: {msg_precio}')

    stock, stock_valido, msg_stock = validar_entero_estricto(raw_stock, nombre_campo="stock", permitir_cero=True, min_val=0, max_val=99999)
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
    Control transaccional atómico y límite de stock de 99.999 unidades.
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
        cantidad, cant_valida, msg_cant = validar_cantidad_entera(raw_cant, nombre_campo="cantidad a agregar", max_cant=99999)

        if not id_valido or not cant_valida:
            return JsonResponse({'success': False, 'error': msg_cant or 'Parámetros numéricos no válidos o negativos.'}, status=400)

        with transaction.atomic():
            prod = Producto.objects.select_for_update().filter(id=prod_id).first()
            if prod:
                if prod.stock + cantidad > 99999:
                    return JsonResponse({'success': False, 'error': f'El stock total no puede superar las 99.999 unidades (actual: {prod.stock}, a agregar: {cantidad}).'}, status=400)
                prod.stock += cantidad
                prod.save(update_fields=['stock'])
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


