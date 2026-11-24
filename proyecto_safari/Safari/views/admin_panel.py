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
    verificar_peticion_get_segura,
    validar_parametro_get_seguro,
    validar_entero_estricto,
)
from .auth import obtener_usuario


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


def _verificar_admin(request):
    """Auxiliar para validar sesión activa de Administrador en los mantenedores."""
    usuario = obtener_usuario(request)
    if not usuario:
        return None, error_401_view(request, mensaje='Se requiere iniciar sesión como Administrador para acceder a los módulos mantenedores.')
    if usuario.get('rol') != 'administrador':
        return None, error_403_view(request, mensaje=f'Acceso denegado: El rol "{usuario.get("rol")}" no tiene permisos para acceder a los mantenedores del sistema.')
    return usuario, None


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


