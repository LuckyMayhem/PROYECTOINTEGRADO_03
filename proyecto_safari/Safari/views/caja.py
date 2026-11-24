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
    validar_entero_estricto,
)
from .auth import obtener_usuario
from .admin_panel import (
    error_400_view,
    error_401_view,
    error_403_view,
    error_404_view,
    error_500_view,
)


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

        # Control transaccional atómico con select_for_update() para evitar sobreventa o condiciones de carrera
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

            total_calculado = Decimal('0.00')
            detalle_texto = []
            productos_detalle = []
            items_limpios_json = []

            for prod_id, cant in items_solicitados:
                prod = productos_bloqueados[prod_id]
                precio_bd = prod.precio
                subtotal = Decimal(str(cant)) * precio_bd
                total_calculado += subtotal

                # Descontar stock verificado de forma atómica
                prod.stock = max(0, prod.stock - cant)
                prod.save(update_fields=['stock'])

                productos_detalle.append((prod, cant, subtotal))
                detalle_texto.append(f"{cant}x {prod.nombre} (${subtotal:,.0f})")
                items_limpios_json.append({'id': prod.id, 'nombre': prod.nombre, 'cantidad': cant, 'precio': float(precio_bd), 'stock_descontado': True})

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
        items_solicitados = []
        for item in items:
            prod_id = item.get('id')
            cant_raw = item.get('cantidad', 1)
            cant, cant_valida, msg_cant = validar_cantidad_entera(cant_raw, nombre_campo="cantidad", max_cant=50)
            if not cant_valida:
                return JsonResponse({'success': False, 'error': f'Petición rechazada: {msg_cant}'}, status=400)
            items_solicitados.append((prod_id, cant))

        # Control transaccional atómico con select_for_update() para evitar condiciones de carrera y sobreventa
        with transaction.atomic():
            prod_ids = [pid for pid, _ in items_solicitados]
            productos_bloqueados = {p.id: p for p in Producto.objects.select_for_update().filter(id__in=prod_ids)}

            # Consistencia de inventario: Verificar si la comanda ya descontó stock al enviarse a cocina
            comanda_ya_desconto = getattr(comanda, 'stock_descontado', False)
            if not comanda_ya_desconto:
                try:
                    data_items = json.loads(comanda.items_json)
                    if isinstance(data_items, list) and len(data_items) > 0 and all(it.get('stock_descontado') for it in data_items if isinstance(it, dict)):
                        comanda_ya_desconto = True
                except Exception:
                    pass

            for prod_id, cant in items_solicitados:
                prod = productos_bloqueados.get(prod_id)
                if not prod:
                    return JsonResponse({'success': False, 'error': f'Producto #{prod_id} de la orden no encontrado en la base de datos.'}, status=400)

                # Si el stock no fue descontado previamente por mesero, verificar disponibilidad
                if not comanda_ya_desconto:
                    if prod.stock <= 0 or prod.stock < cant:
                        return JsonResponse({
                            'success': False,
                            'error': f'Stock insuficiente para liquidar "{prod.nombre}". Solicitado: {cant}, disponible en inventario: {prod.stock}.'
                        }, status=400)

            total_calculado = Decimal('0.00')
            productos_detalle = []
            for prod_id, cant in items_solicitados:
                prod = productos_bloqueados[prod_id]
                subtotal = Decimal(str(cant)) * prod.precio
                total_calculado += subtotal

                # Descontar stock SOLO una vez por flujo
                if not comanda_ya_desconto:
                    prod.stock = max(0, prod.stock - cant)
                    prod.save(update_fields=['stock'])

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
            setattr(comanda, 'stock_descontado', True)
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


def devolver_stock_venta(venta):
    """
    Restaura atómicamente el inventario de los productos asociados a una venta anulada:
    - Utiliza transaction.atomic() y select_for_update() para evitar condiciones de carrera.
    - Respeta el límite máximo de stock de 99.999 unidades por producto.
    """
    with transaction.atomic():
        detalles = list(DetalleVenta.objects.filter(venta=venta))
        pids = [d.producto_id for d in detalles if d.producto_id]
        if not pids:
            return
        prods = {p.id: p for p in Producto.objects.select_for_update().filter(id__in=pids)}
        for d in detalles:
            if d.producto_id and d.producto_id in prods:
                p = prods[d.producto_id]
                p.stock = min(99999, p.stock + d.cantidad)
                p.save(update_fields=['stock'])


def cajero_anular_venta(request):
    """
    Anula una venta en caja y restituye automáticamente el stock al inventario.
    Blindaje de método: Exige POST. Requiere rol de cajero o administrador.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido. Se requiere POST.'}, status=405)

    usuario = obtener_usuario(request)
    if not usuario or usuario.get('rol') not in ['cajero', 'administrador']:
        return JsonResponse({'success': False, 'error': 'No autorizado para anular ventas.'}, status=403)

    try:
        data = json.loads(request.body)
        venta_id = data.get('venta_id')
        if not venta_id:
            return JsonResponse({'success': False, 'error': 'Identificador de venta no proporcionado.'}, status=400)

        with transaction.atomic():
            venta = Venta.objects.select_for_update().filter(id=venta_id).first()
            if not venta:
                return JsonResponse({'success': False, 'error': f'Venta #{venta_id} no encontrada.'}, status=404)
            if 'ANULADA' in (venta.notas or '').upper():
                return JsonResponse({'success': False, 'error': 'La venta ya fue anulada previamente.'}, status=400)

            devolver_stock_venta(venta)
            venta.notas = f"[ANULADA] {venta.notas or ''}".strip()
            venta.save(update_fields=['notas'])

            usuario_obj = Usuario.objects.filter(id=usuario.get('id')).first()
            registrar_auditoria(usuario_obj, 'ACTUALIZAR', 'Ventas', f"Venta #{venta.id} anulada - Stock restituido correctamente")
            return JsonResponse({'success': True, 'message': f'Venta #{venta_id} anulada y stock devuelto exitosamente.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error al anular venta: {str(e)}'}, status=500)


