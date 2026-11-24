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

from .common import sanitizar_texto_defensivo
from .auth import obtener_usuario
from .admin_panel import (
    error_400_view,
    error_401_view,
    error_403_view,
    error_404_view,
)


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


def devolver_stock_comanda(comanda):
    """
    Restaura atómicamente el inventario de los productos de una comanda anulada/cancelada,
    siempre que el stock haya sido descontado previamente.
    """
    with transaction.atomic():
        try:
            items = json.loads(comanda.items_json) if comanda.items_json else []
        except Exception:
            items = []
        pids = [it.get('id') for it in items if isinstance(it, dict) and it.get('id')]
        if not pids:
            return
        prods = {p.id: p for p in Producto.objects.select_for_update().filter(id__in=pids)}
        for it in items:
            if isinstance(it, dict):
                pid = it.get('id')
                cant = it.get('cantidad', 0)
                if pid in prods and cant > 0:
                    p = prods[pid]
                    p.stock = min(99999, p.stock + cant)
                    p.save(update_fields=['stock'])


def cocina_anular_comanda(request):
    """
    Anula una comanda y restituye el stock al inventario en caso de haber sido descontado.
    Blindaje de método: Exige POST. Requiere rol de cocinero, mesero o administrador.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido. Se requiere POST.'}, status=405)

    usuario = obtener_usuario(request)
    if not usuario or usuario.get('rol') not in ['cocinero', 'mesero', 'administrador']:
        return JsonResponse({'success': False, 'error': 'No autorizado para anular comandas.'}, status=403)

    try:
        data = json.loads(request.body)
        comanda_id = data.get('comanda_id')
        if not comanda_id:
            return JsonResponse({'success': False, 'error': 'Identificador de comanda no proporcionado.'}, status=400)

        with transaction.atomic():
            comanda = Comanda.objects.select_for_update().filter(id=comanda_id).first()
            if not comanda:
                return JsonResponse({'success': False, 'error': f'Comanda #{comanda_id} no encontrada.'}, status=404)
            if comanda.estado in ['cancelado', 'anulado']:
                return JsonResponse({'success': False, 'error': 'La comanda ya fue anulada previamente.'}, status=400)

            # Restituir stock si fue descontado
            devolver_stock_comanda(comanda)
            comanda.estado = 'cancelado'
            comanda.save(update_fields=['estado'])

            if comanda.mesa_rel:
                comanda.mesa_rel.estado = 'desocupada'
                comanda.mesa_rel.save(update_fields=['estado'])

            usuario_obj = Usuario.objects.filter(id=usuario.get('id')).first()
            registrar_auditoria(usuario_obj, 'ACTUALIZAR', 'Comandas', f"Comanda {comanda.folio} anulada - Stock restituido")
            return JsonResponse({'success': True, 'message': f'Comanda {comanda.folio} anulada exitosamente.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error al anular comanda: {str(e)}'}, status=500)


