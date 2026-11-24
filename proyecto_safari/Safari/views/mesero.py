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
    sanitizar_texto_defensivo,
    validar_cantidad_entera,
    validar_entero_estricto,
)
from .auth import obtener_usuario
from .admin_panel import (
    error_400_view,
    error_401_view,
    error_403_view,
    error_404_view,
)


def mesero_view(request):
    """Módulo de salón para el mesero con navegación por pestañas y contadores."""
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

    # Desglose en 4 secciones clave:
    # 1. Comandas listas para servir (Cocina terminó el plato)
    comandas_listas = Comanda.objects.filter(
        estado__in=['listo', 'LISTO'],
        pagada=False
    ).select_related('mesa_rel').order_by('-fecha')

    # 2. Mesas disponibles para asignar y tomar pedido
    mesas_disponibles = mesas.filter(estado__in=['disponible', 'desocupada'])

    # 3. Mesas ocupadas con comida en preparación o esperando comida
    mesas_ocupadas = mesas.filter(estado='ocupada', comida_entregada=False)

    # 4. Mesas servidas (comida entregada) o listas para cobro en caja
    mesas_servidas = mesas.filter(
        Q(estado='ocupada', comida_entregada=True) |
        Q(estado__in=['LISTO_PARA_COBRO', 'PENDIENTE_PAGO'])
    )

    count_listos_servir = comandas_listas.count()
    count_disponibles = mesas_disponibles.count()
    count_ocupadas = mesas_ocupadas.count()
    count_servidas = mesas_servidas.count()

    # Pestaña activa persistente
    tab_activa = (request.GET.get('tab') or request.session.get('tab_mesero_activa') or '').strip().lower()
    if tab_activa not in ['listos_servir', 'disponibles', 'ocupadas', 'servidas']:
        tab_activa = 'listos_servir' if count_listos_servir > 0 else 'disponibles'
    request.session['tab_mesero_activa'] = tab_activa

    context = {
        'usuario': usuario.get('nombre'),
        'rol': usuario.get('rol'),
        'tab_activa': tab_activa,
        'mesas': mesas,
        'comandas_listas': comandas_listas,
        'mesas_disponibles': mesas_disponibles,
        'mesas_ocupadas': mesas_ocupadas,
        'mesas_servidas': mesas_servidas,
        'count_listos_servir': count_listos_servir,
        'count_disponibles': count_disponibles,
        'count_ocupadas': count_ocupadas,
        'count_servidas': count_servidas,
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
        # 1. Validar rigurosamente que cada cantidad sea un entero positivo mayor a 0 y <= 50
        # 2. Consultar siempre el precio real directo del modelo Producto en la BD
        items_solicitados = []
        for item in items:
            if not isinstance(item, dict):
                return JsonResponse({'success': False, 'error': 'Formato de ítem no válido en el pedido.'}, status=400)

            prod_id_raw = item.get('id')
            prod_id, id_valido, _ = validar_entero_estricto(prod_id_raw, nombre_campo='ID de producto', permitir_cero=False)
            if not id_valido:
                return JsonResponse({'success': False, 'error': 'Identificador de producto inválido en el pedido.'}, status=400)

            raw_cant = item.get('cantidad')
            cant, cant_valida, msg_cant = validar_cantidad_entera(raw_cant, nombre_campo='cantidad', max_cant=50)
            if not cant_valida:
                return JsonResponse({'success': False, 'error': f'Petición rechazada: {msg_cant}'}, status=400)

            items_solicitados.append((prod_id, cant))

        # Control transaccional atómico con select_for_update() para evitar sobreventa concurrente
        with transaction.atomic():
            prod_ids = [pid for pid, _ in items_solicitados]
            productos_bloqueados = {p.id: p for p in Producto.objects.select_for_update().filter(id__in=prod_ids)}

            for prod_id, cant in items_solicitados:
                prod = productos_bloqueados.get(prod_id)
                if not prod:
                    return JsonResponse({'success': False, 'error': f'Producto #{prod_id} no encontrado en la base de datos.'}, status=400)
                if prod.stock <= 0 or prod.stock < cant:
                    return JsonResponse({
                        'success': False,
                        'error': f'Stock insuficiente para "{prod.nombre}". Solicitado: {cant}, disponible: {prod.stock}.'
                    }, status=400)

            detalle_texto = []
            total_calculado = Decimal('0.00')
            items_limpios = []

            for prod_id, cant in items_solicitados:
                prod = productos_bloqueados[prod_id]
                precio_bd = prod.precio
                subtotal = Decimal(str(cant)) * precio_bd
                total_calculado += subtotal

                detalle_texto.append(f"{cant}x {prod.nombre} (${subtotal:,.0f})")
                items_limpios.append({'id': prod.id, 'nombre': prod.nombre, 'cantidad': cant, 'precio': float(precio_bd), 'stock_descontado': False})

            # 1. Mesa pasa a estado 'ocupada'
            mesa.estado = 'ocupada'
            mesa.comida_entregada = False
            mesa.save()

            usuario_obj = Usuario.objects.filter(id=usuario.get('id')).first()

            # 2. Aislamiento estricto por Mesa:
            # Si la mesa ya tiene una comanda activa no pagada, consolidar productos de esa misma sesión de mesa
            comanda_activa = Comanda.objects.select_for_update().filter(Q(mesa_rel=mesa) | Q(mesa_rel_id=mesa.id), pagada=False).last()
            if not comanda_activa:
                comanda_activa = Comanda.objects.select_for_update().filter(mesa=mesa.nombre, pagada=False).last()

            if comanda_activa:
                try:
                    items_existentes = json.loads(comanda_activa.items_json)
                except Exception:
                    items_existentes = []

                dict_items = {it['id']: it for it in items_existentes if isinstance(it, dict) and 'id' in it}
                for il in items_limpios:
                    pid = il['id']
                    if pid in dict_items:
                        nueva_cant = dict_items[pid]['cantidad'] + il['cantidad']
                        prod_ref = productos_bloqueados.get(pid)
                        if prod_ref and nueva_cant > prod_ref.stock:
                            return JsonResponse({
                                'success': False,
                                'error': f'Stock insuficiente para "{prod_ref.nombre}". Total acumulado solicitado: {nueva_cant}, disponible: {prod_ref.stock}.'
                            }, status=400)
                        if nueva_cant > 50:
                            return JsonResponse({
                                'success': False,
                                'error': f'La cantidad acumulada máxima permitida por producto es de 50 unidades (solicitado: {nueva_cant}).'
                            }, status=400)
                        dict_items[pid]['cantidad'] = nueva_cant
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


def mesero_marcar_entregado(request):
    """
    Marca una comanda de cocina como 'entregado' y actualiza mesa.comida_entregada = True.
    - Exclusivo para 'mesero' y 'administrador'.
    - Requiere método POST.
    - Actualización atómica en base de datos y registro en HistorialAccion.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido. Se requiere POST.'}, status=405)

    usuario = obtener_usuario(request)
    if not usuario or usuario.get('rol') not in ['mesero', 'administrador']:
        return JsonResponse({'success': False, 'error': 'No autorizado para marcar comandas como servidas.'}, status=403)

    try:
        data = json.loads(request.body)
        comanda_id = data.get('comanda_id')
        mesa_id = data.get('mesa_id')

        if not comanda_id and not mesa_id:
            return JsonResponse({'success': False, 'error': 'Identificador de comanda o mesa no proporcionado.'}, status=400)

        with transaction.atomic():
            comanda = None
            if comanda_id:
                comanda = Comanda.objects.select_for_update().filter(id=comanda_id).first()
            if not comanda and mesa_id:
                comanda = Comanda.objects.select_for_update().filter(
                    Q(mesa_rel_id=mesa_id) | Q(mesa__iexact=f"Mesa {mesa_id}"),
                    pagada=False
                ).last()

            mesa = None
            if comanda and comanda.mesa_rel:
                mesa = Mesa.objects.select_for_update().filter(id=comanda.mesa_rel_id).first()
            elif mesa_id:
                mesa = Mesa.objects.select_for_update().filter(id=mesa_id).first()
            elif comanda and comanda.mesa:
                mesa = Mesa.objects.select_for_update().filter(nombre=comanda.mesa).first()

            if comanda:
                comanda.estado = 'entregado'
                comanda.save(update_fields=['estado'])

            if mesa:
                mesa.comida_entregada = True
                mesa.save(update_fields=['comida_entregada'])

            if not comanda and not mesa:
                return JsonResponse({'success': False, 'error': 'No se encontró la comanda ni la mesa especificada.'}, status=404)

        usuario_obj = Usuario.objects.filter(id=usuario.get('id')).first()
        folio_str = comanda.folio if comanda else 'N/A'
        mesa_str = mesa.nombre if mesa else (comanda.mesa if comanda else 'Mesa')
        registrar_auditoria(
            usuario_obj,
            'ACTUALIZAR',
            'Comandas',
            f"Comanda {folio_str} ({mesa_str}) marcada como SERVIDA / ENTREGADA por {usuario_obj.nombre if usuario_obj else 'Mesero'}."
        )

        return JsonResponse({
            'success': True,
            'comanda_id': comanda.id if comanda else None,
            'mesa_id': mesa.id if mesa else None,
            'mesa_nombre': mesa_str,
            'folio': folio_str,
            'estado': 'entregado',
            'comida_entregada': True,
            'message': f'Comanda {folio_str} de {mesa_str} marcada como Servido / Entregado.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def api_mesero_estado(request):
    """
    Endpoint JSON para sincronización periódica y polling en tiempo real del módulo de Mesero (cada 5-8 seg).
    Retorna contadores de cada tab, lista de comandas listas para servir y detalle de mesas de salón.
    Acceso restringido: Exclusivo para 'mesero' y 'administrador'.
    """
    usuario = obtener_usuario(request)
    if not usuario or usuario.get('rol') not in ['mesero', 'administrador']:
        return JsonResponse({'success': False, 'error': 'No autorizado'}, status=403)

    # 1. Comandas listas para servir
    comandas_listas_qs = Comanda.objects.filter(
        estado__in=['listo', 'LISTO'],
        pagada=False
    ).select_related('mesa_rel').order_by('-fecha')

    comandas_listas_data = []
    for cmd in comandas_listas_qs:
        comandas_listas_data.append({
            'id': cmd.id,
            'folio': cmd.folio,
            'mesa': cmd.mesa,
            'mesa_id': cmd.mesa_rel_id if cmd.mesa_rel else None,
            'mesa_numero': cmd.mesa_rel.numero if cmd.mesa_rel else None,
            'items': cmd.items,
            'notas': cmd.notas,
            'total': float(cmd.total),
            'hora': cmd.fecha.strftime("%H:%M") if cmd.fecha else '',
            'es_reemision': cmd.es_reemision,
            'motivo_reemision': cmd.motivo_reemision or '',
        })

    # 2. Mesas de salón y contadores
    mesas_all = Mesa.objects.all().order_by('numero')
    count_disponibles = mesas_all.filter(estado__in=['disponible', 'desocupada']).count()
    count_ocupadas = mesas_all.filter(estado='ocupada', comida_entregada=False).count()
    count_servidas = mesas_all.filter(
        Q(estado='ocupada', comida_entregada=True) |
        Q(estado__in=['LISTO_PARA_COBRO', 'PENDIENTE_PAGO'])
    ).count()
    count_listos_servir = len(comandas_listas_data)

    mesas_data = []
    for m in mesas_all:
        cmd_activa = Comanda.objects.filter(Q(mesa_rel=m) | Q(mesa_rel_id=m.id), pagada=False).last()
        if not cmd_activa:
            cmd_activa = Comanda.objects.filter(mesa=m.nombre, pagada=False).last()

        mesas_data.append({
            'id': m.id,
            'numero': m.numero,
            'nombre': m.nombre,
            'capacidad': m.capacidad,
            'estado': m.estado,
            'comida_entregada': m.comida_entregada,
            'comanda': {
                'id': cmd_activa.id,
                'folio': cmd_activa.folio,
                'total': float(cmd_activa.total),
                'estado': cmd_activa.estado,
                'notas': cmd_activa.notas,
                'items': cmd_activa.items,
            } if cmd_activa else None
        })

    return JsonResponse({
        'success': True,
        'contadores': {
            'listos_servir': count_listos_servir,
            'disponibles': count_disponibles,
            'ocupadas': count_ocupadas,
            'servidas': count_servidas,
        },
        'comandas_listas': comandas_listas_data,
        'mesas': mesas_data
    })



