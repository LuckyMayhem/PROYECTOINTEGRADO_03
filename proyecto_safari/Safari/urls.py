from django.urls import path, re_path
from . import views

urlpatterns = [
    # Autenticación
    path('', views.login_view, name='login_root'),
    path('login/', views.login_view, name='login'),
    path('login', views.login_view),
    path('logout/', views.logout_view, name='logout'),
    path('logout', views.logout_view),

    # Módulos principales por rol
    path('cajero/', views.cajero_view, name='cajero'),
    path('cajero', views.cajero_view),
    path('mesero/', views.mesero_view, name='mesero'),
    path('mesero', views.mesero_view),
    path('cocinero/', views.cocinero_view, name='cocinero'),
    path('cocinero', views.cocinero_view),
    path('administrador/', views.administrador_view, name='administrador'),
    path('administrador', views.administrador_view),

    # Stock (accesible para todos en modo lectura; administración para el admin)
    path('stock/', views.stock_view, name='stock'),
    path('stock/guardar/', views.admin_guardar_producto, name='stock_guardar'),
    path('stock/agregar/', views.admin_agregar_stock, name='stock_agregar'),
    path('stock/eliminar/<int:id>/', views.admin_eliminar_producto, name='stock_eliminar'),

    # Ventas (historial con tiempo exacto de venta para el admin)
    path('ventas/', views.ventas_view, name='ventas'),

    # Acciones operativas
    path('cajero/registrar-venta/', views.cajero_registrar_venta, name='cajero_registrar_venta'),
    path('cajero/mesa-cuenta/<int:mesa_id>/', views.cajero_mesa_cuenta, name='cajero_mesa_cuenta'),
    path('cajero/liquidar-mesa/', views.cajero_liquidar_mesa, name='cajero_liquidar_mesa'),
    path('cajero/anular-venta/', views.cajero_anular_venta, name='cajero_anular_venta'),
    path('api/mesas-con-cuenta/', views.api_mesas_con_cuenta, name='api_mesas_con_cuenta'),
    path('mesero/tomar-pedido/', views.mesero_tomar_pedido, name='mesero_tomar_pedido'),
    path('mesero/solicitar-cuenta/', views.mesero_solicitar_cuenta, name='mesero_solicitar_cuenta'),
    path('mesero/finalizar-venta/', views.mesero_solicitar_cuenta, name='mesero_finalizar_venta'),
    path('mesero/cambiar-mesa/', views.mesero_cambiar_mesa, name='mesero_cambiar_mesa'),
    path('cocina/cambiar-estado/', views.cocina_cambiar_estado, name='cocina_cambiar_estado'),
    path('cocina/reorden/', views.cocina_reorden, name='cocina_reorden'),
    path('cocina/re-orden/', views.cocina_reorden, name='cocina_re_orden'),
    path('cocina/anular-comanda/', views.cocina_anular_comanda, name='cocina_anular_comanda'),
    path('administrador/cerrar-caja/', views.admin_cerrar_caja, name='admin_cerrar_caja'),
    path('administrador/abrir-caja/', views.admin_abrir_caja, name='admin_abrir_caja'),
    path('caja/abrir/', views.admin_abrir_caja, name='caja_abrir'),
    path('caja/cerrar/', views.admin_cerrar_caja, name='caja_cerrar'),
    path('caja/resumen/', views.api_resumen_caja_actual, name='caja_resumen'),
    path('administrador/guardar-usuario/', views.admin_guardar_usuario, name='admin_guardar_usuario'),
    path('administrador/eliminar-usuario/<int:id>/', views.admin_eliminar_usuario, name='admin_eliminar_usuario'),

    # Módulos Mantenedores (CRUDs completos con validación de Administrador)
    path('mantenedores/', views.mantenedores_hub_view, name='mantenedores_hub'),

    # Mantenedor: Usuarios
    path('mantenedores/usuarios/', views.mantenedor_usuarios_view, name='mantenedor_usuarios'),
    path('mantenedores/usuarios/registrar/', views.mantenedor_usuario_registrar_view, name='mantenedor_usuario_registrar'),
    path('mantenedores/usuarios/actualizar/<int:id>/', views.mantenedor_usuario_actualizar_view, name='mantenedor_usuario_actualizar'),
    path('mantenedores/usuarios/guardar/', views.mantenedor_usuario_guardar, name='mantenedor_usuario_guardar'),
    path('mantenedores/usuarios/eliminar/<int:id>/', views.mantenedor_usuario_eliminar, name='mantenedor_usuario_eliminar'),

    # Mantenedor: Mesas
    path('mantenedores/mesas/', views.mantenedor_mesas_view, name='mantenedor_mesas'),
    path('mantenedores/mesas/registrar/', views.mantenedor_mesa_registrar_view, name='mantenedor_mesa_registrar'),
    path('mantenedores/mesas/actualizar/<int:id>/', views.mantenedor_mesa_actualizar_view, name='mantenedor_mesa_actualizar'),
    path('mantenedores/mesas/guardar/', views.mantenedor_mesa_guardar, name='mantenedor_mesa_guardar'),
    path('mantenedores/mesas/eliminar/<int:id>/', views.mantenedor_mesa_eliminar, name='mantenedor_mesa_eliminar'),

    # Mantenedor: Puntos de Venta
    path('mantenedores/puntos-de-venta/', views.mantenedor_puntos_venta_view, name='mantenedor_puntos_venta'),
    path('mantenedores/puntos-de-venta/registrar/', views.mantenedor_punto_venta_registrar_view, name='mantenedor_punto_venta_registrar'),
    path('mantenedores/puntos-de-venta/actualizar/<int:id>/', views.mantenedor_punto_venta_actualizar_view, name='mantenedor_punto_venta_actualizar'),
    path('mantenedores/puntos-de-venta/guardar/', views.mantenedor_punto_venta_guardar, name='mantenedor_punto_venta_guardar'),
    path('mantenedores/puntos-de-venta/eliminar/<int:id>/', views.mantenedor_punto_venta_eliminar, name='mantenedor_punto_venta_eliminar'),

    # Mantenedor: Menús / Categorías
    path('mantenedores/menus/', views.mantenedor_menus_view, name='mantenedor_menus'),
    path('mantenedores/menus/registrar/', views.mantenedor_menu_registrar_view, name='mantenedor_menu_registrar'),
    path('mantenedores/menus/actualizar/<int:id>/', views.mantenedor_menu_actualizar_view, name='mantenedor_menu_actualizar'),
    path('mantenedores/menus/guardar/', views.mantenedor_menu_guardar, name='mantenedor_menu_guardar'),
    path('mantenedores/menus/eliminar/<int:id>/', views.mantenedor_menu_eliminar, name='mantenedor_menu_eliminar'),

    # Mantenedor: Productos
    path('mantenedores/productos/', views.mantenedor_productos_view, name='mantenedor_productos'),
    path('mantenedores/productos/registrar/', views.mantenedor_producto_registrar_view, name='mantenedor_producto_registrar'),
    path('mantenedores/productos/actualizar/<int:id>/', views.mantenedor_producto_actualizar_view, name='mantenedor_producto_actualizar'),
    path('mantenedores/productos/guardar/', views.mantenedor_producto_guardar, name='mantenedor_producto_guardar'),
    path('mantenedores/productos/eliminar/<int:id>/', views.mantenedor_producto_eliminar, name='mantenedor_producto_eliminar'),

    # Historial de Acciones / Auditoría
    path('mantenedores/auditoria/', views.mantenedor_auditoria_view, name='mantenedor_auditoria'),


    # Rutas para visualización y prueba de errores HTTP personalizados
    path('error/400/', views.error_400_view, name='error_400'),
    path('error/401/', views.error_401_view, name='error_401'),
    path('error/403/', views.error_403_view, name='error_403'),
    path('error/404/', views.error_404_view, name='error_404'),
    path('error/500/', views.error_500_view, name='error_500'),
    path('error/502/', views.error_502_view, name='error_502'),
    path('error/503/', views.error_503_view, name='error_503'),
    path('error/504/', views.error_504_view, name='error_504'),

    # Enrutamiento de captura para cualquier ruta no declarada (Error 404 personalizado)
    re_path(r'^(?!static/).*$', views.error_404_view, name='catch_all_404'),
]

