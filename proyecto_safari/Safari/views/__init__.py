"""
Paquete Safari.views organizado por dominio funcional:
- auth: Autenticación, sesión y control de inactividad
- caja: Apertura/cierre de caja, cobros, arqueo y liquidación de mesas
- mesero: Gestión de mesas, toma de pedidos y comanda
- cocina: Monitor de comandas, estados y re-emisiones
- mantenedores: CRUDs completos (usuarios, productos, mesas, puntos de venta, menús, stock)
- admin_panel: Dashboard administrativo, reportes, auditoría y manejadores de error HTTP
- common: Helpers de sanitización y validaciones de seguridad defensiva OWASP

Re-exporta todas las vistas y funciones públicas para mantener 100% de compatibilidad
con Safari/urls.py y Safari/tests.py.
"""

from .common import (
    REGEX_INYECCION_SQL,
    REGEX_SQL_ESCAPE,
    REGEX_CARACTERES_PROHIBIDOS,
    REGEX_SOLO_DIGITOS,
    MAX_INTENTOS_LOGIN,
    BLOQUEO_SEGUNDOS,
    sanitizar_cadena,
    sanitizar_texto_defensivo,
    validar_cantidad_entera,
    validar_parametro_get_seguro,
    verificar_peticion_get_segura,
    validar_entero_estricto,
)
from .auth import (
    obtener_usuario,
    login_view,
    logout_view,
)
from .caja import (
    cajero_view,
    cajero_registrar_venta,
    cajero_mesa_cuenta,
    cajero_liquidar_mesa,
    api_mesas_con_cuenta,
    api_resumen_caja_actual,
    admin_abrir_caja,
    admin_cerrar_caja,
    devolver_stock_venta,
    cajero_anular_venta,
)
from .mesero import (
    mesero_view,
    mesero_tomar_pedido,
    mesero_solicitar_cuenta,
    mesero_cambiar_mesa,
)
from .cocina import (
    cocinero_view,
    cocina_reorden,
    cocina_cambiar_estado,
    devolver_stock_comanda,
    cocina_anular_comanda,
)
from .mantenedores import (
    mantenedores_hub_view,
    mantenedor_usuarios_view,
    mantenedor_usuario_registrar_view,
    mantenedor_usuario_actualizar_view,
    mantenedor_usuario_guardar,
    mantenedor_usuario_eliminar,
    mantenedor_mesas_view,
    mantenedor_mesa_registrar_view,
    mantenedor_mesa_actualizar_view,
    mantenedor_mesa_guardar,
    mantenedor_mesa_eliminar,
    mantenedor_puntos_venta_view,
    mantenedor_punto_venta_registrar_view,
    mantenedor_punto_venta_actualizar_view,
    mantenedor_punto_venta_guardar,
    mantenedor_punto_venta_eliminar,
    mantenedor_menus_view,
    mantenedor_menu_registrar_view,
    mantenedor_menu_actualizar_view,
    mantenedor_menu_guardar,
    mantenedor_menu_eliminar,
    mantenedor_productos_view,
    mantenedor_producto_registrar_view,
    mantenedor_producto_actualizar_view,
    mantenedor_producto_guardar,
    mantenedor_producto_eliminar,
    admin_guardar_usuario,
    admin_eliminar_usuario,
    stock_view,
    admin_guardar_producto,
    admin_agregar_stock,
    admin_eliminar_producto,
)
from .admin_panel import (
    _verificar_admin,
    administrador_view,
    ventas_view,
    mantenedor_auditoria_view,
    error_404_view,
    error_500_view,
    error_403_view,
    error_400_view,
    error_401_view,
    error_502_view,
    error_503_view,
    error_504_view,
)

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
