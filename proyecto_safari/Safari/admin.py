from django.contrib import admin
from .models import (
    Usuario,
    PuntoDeVenta,
    Menu,
    Producto,
    Venta,
    DetalleVenta,
    Comanda,
    Mesa,
    ControlCaja,
    SecuenciaFolio,
    HistorialAccion
)

class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0

@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ('rut', 'nombre', 'username', 'correo', 'rol', 'estado')
    search_fields = ('rut', 'nombre', 'username', 'correo')
    list_filter = ('rol', 'estado')

@admin.register(PuntoDeVenta)
class PuntoDeVentaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'ubicacion', 'estado')
    list_filter = ('estado',)
    search_fields = ('nombre', 'ubicacion')

@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion', 'estado')
    list_filter = ('estado',)
    search_fields = ('nombre',)

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'menu', 'precio', 'stock')
    search_fields = ('codigo', 'nombre')
    list_filter = ('menu',)

@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ('numero', 'nombre', 'capacidad', 'estado', 'comida_entregada')
    list_filter = ('estado', 'comida_entregada')
    search_fields = ('numero', 'nombre')

@admin.register(HistorialAccion)
class HistorialAccionAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'usuario', 'accion', 'modulo', 'detalle')
    list_filter = ('accion', 'modulo', 'fecha')
    search_fields = ('detalle', 'usuario__username', 'usuario__nombre')

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'tipo_venta', 'usuario', 'mesero', 'mesa', 'metodo_pago', 'total', 'fecha')
    list_filter = ('tipo_venta', 'metodo_pago', 'fecha')
    search_fields = ('usuario__nombre', 'mesero__nombre', 'mesa__nombre', 'notas')
    inlines = [DetalleVentaInline]

@admin.register(DetalleVenta)
class DetalleVentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'venta', 'producto', 'cantidad', 'subtotal')

@admin.register(Comanda)
class ComandaAdmin(admin.ModelAdmin):
    list_display = ('folio', 'tipo_pedido', 'mesa', 'mesero', 'total', 'estado', 'es_reemision', 'motivo_reemision', 'pagada', 'fecha')
    list_filter = ('tipo_pedido', 'estado', 'es_reemision', 'pagada', 'fecha')
    search_fields = ('folio', 'mesa', 'notas', 'motivo_reemision')

@admin.register(ControlCaja)
class ControlCajaAdmin(admin.ModelAdmin):
    list_display = ('id', 'estado', 'abierta', 'usuario', 'punto_venta', 'monto_inicial', 'total_ventas_sistema', 'total_efectivo_declarado', 'diferencia_cuadratura', 'fecha_apertura', 'fecha_cierre', 'cerrada_por')
    list_filter = ('estado', 'abierta', 'fecha_apertura', 'punto_venta', 'punto_de_venta')
    search_fields = ('usuario__nombre', 'cajero_responsable__nombre', 'punto_venta__nombre')

@admin.register(SecuenciaFolio)
class SecuenciaFolioAdmin(admin.ModelAdmin):
    list_display = ('id', 'tipo', 'ultimo_numero')
