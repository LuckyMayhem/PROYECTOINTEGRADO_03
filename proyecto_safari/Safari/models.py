from decimal import Decimal
from django.db import models


class Usuario(models.Model):
    rut = models.CharField(max_length=20, blank=True, default='', help_text="RUT o cédula de identidad")
    nombre = models.CharField(max_length=100)
    correo = models.EmailField(unique=True)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=128)
    rol = models.CharField(max_length=50, default='cajero', help_text="Rol o perfil del usuario (administrador, cajero, mesero, cocinero)")
    estado = models.CharField(max_length=20, default='activo', help_text="Estado de la cuenta: 'activo' o 'inactivo'")

    @property
    def is_active(self):
        return self.estado == 'activo'

    def __str__(self):
        return f"{self.nombre} ({self.rol})"


class PuntoDeVenta(models.Model):
    """Puntos de venta o cajas registradoras físicas / terminales POS."""
    nombre = models.CharField(max_length=100, help_text="Nombre o identificador de caja (ej: Caja Principal, Caja Terraza)")
    ubicacion = models.CharField(max_length=100, blank=True, default='', help_text="Ubicación física dentro del restaurante")
    estado = models.CharField(max_length=20, default='activo', help_text="'activo' o 'inactivo'")

    def __str__(self):
        return f"{self.nombre} ({self.ubicacion})" if self.ubicacion else self.nombre


class Menu(models.Model):
    """Menú o categorías de la carta (ej: Platos de fondo, Bebestibles, Postres)."""
    nombre = models.CharField(max_length=100, help_text="Nombre de sección (Platos de fondo, Bebestibles, Postres, etc.)")
    descripcion = models.CharField(max_length=255, blank=True, default='')
    estado = models.CharField(max_length=20, default='activo', help_text="'activo' o 'inactivo'")

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    codigo = models.CharField(max_length=50, blank=True, default='', help_text="Código identificador o SKU del producto")
    nombre = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=255, blank=True, default='')
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    menu = models.ForeignKey(Menu, on_delete=models.SET_NULL, null=True, blank=True, related_name='productos', help_text="Categoría o sección del menú")

    @property
    def categoria(self):
        return self.menu.nombre if self.menu else self.descripcion

    def __str__(self):
        return self.nombre


class Mesa(models.Model):
    numero = models.IntegerField(unique=True, help_text="Número único de mesa")
    nombre = models.CharField(max_length=50, help_text="Nombre descriptivo (ej: Mesa Terraza 1, Mesa Central 4)")
    capacidad = models.IntegerField(default=4, help_text="Capacidad de comensales")
    estado = models.CharField(max_length=20, default='disponible', help_text="'disponible', 'ocupada', 'reservada'")
    comida_entregada = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.nombre} ({self.estado})"


class HistorialAccion(models.Model):
    """Registro de Auditoría de operaciones del sistema."""
    ACCIONES = [
        ('CREAR', 'Crear registro'),
        ('ACTUALIZAR', 'Actualizar registro'),
        ('ELIMINAR', 'Eliminar registro'),
        ('LOGIN', 'Inicio de sesión'),
        ('CIERRE_CAJA', 'Cierre de caja y arqueo'),
    ]

    usuario = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='historial_acciones')
    accion = models.CharField(max_length=50, choices=ACCIONES, help_text="Acción realizada")
    modulo = models.CharField(max_length=50, help_text="Módulo o tabla afectada")
    detalle = models.TextField(blank=True, default='', help_text="Detalle breve de la acción")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Historial de Acción'
        verbose_name_plural = 'Historial de Acciones'

    def __str__(self):
        user_str = self.usuario.username if self.usuario else 'Sistema'
        return f"[{self.fecha.strftime('%d/%m/%Y %H:%M')}] {self.accion} en {self.modulo} por {user_str}"


class ControlCaja(models.Model):
    # Campos formales para control operativo y auditoría de turnos
    usuario = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='cajas_usuario')
    punto_venta = models.ForeignKey(PuntoDeVenta, on_delete=models.SET_NULL, null=True, blank=True, related_name='controles_caja_pv')
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    monto_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    total_ventas_sistema = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_efectivo_declarado = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, null=True, blank=True)
    diferencia_cuadratura = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=[('ABIERTA', 'ABIERTA'), ('CERRADA', 'CERRADA')], default='ABIERTA')

    # Arqueo detallado de efectivo: Billetes (CLP)
    billetes_20000 = models.PositiveIntegerField(default=0)
    billetes_10000 = models.PositiveIntegerField(default=0)
    billetes_5000 = models.PositiveIntegerField(default=0)
    billetes_1000 = models.PositiveIntegerField(default=0)

    # Arqueo detallado de efectivo: Monedas (CLP)
    monedas_500 = models.PositiveIntegerField(default=0)
    monedas_100 = models.PositiveIntegerField(default=0)
    monedas_50 = models.PositiveIntegerField(default=0)
    monedas_5 = models.PositiveIntegerField(default=0)
    monedas_1 = models.PositiveIntegerField(default=0)

    # Campos de compatibilidad con versiones previas y modelos relacionados
    abierta = models.BooleanField(default=True)
    cajero_responsable = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='cajas_abiertas')
    cerrada_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='cajas_cerradas')
    punto_de_venta = models.ForeignKey(PuntoDeVenta, on_delete=models.SET_NULL, null=True, blank=True, related_name='controles_caja')
    total_ventas = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_efectivo = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_tarjeta = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_transferencia = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    monto_real = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, null=True, blank=True)
    diferencia = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, null=True, blank=True)

    def calcular_total_arqueo_efectivo(self):
        """Calcula el total de efectivo a partir del conteo de cada billete y moneda."""
        return (
            (self.billetes_20000 or 0) * 20000 +
            (self.billetes_10000 or 0) * 10000 +
            (self.billetes_5000 or 0) * 5000 +
            (self.billetes_1000 or 0) * 1000 +
            (self.monedas_500 or 0) * 500 +
            (self.monedas_100 or 0) * 100 +
            (self.monedas_50 or 0) * 50 +
            (self.monedas_5 or 0) * 5 +
            (self.monedas_1 or 0) * 1
        )

    def save(self, *args, **kwargs):
        # Sincronización bidireccional entre usuario y cajero_responsable
        if self.usuario and not self.cajero_responsable:
            self.cajero_responsable = self.usuario
        elif self.cajero_responsable and not self.usuario:
            self.usuario = self.cajero_responsable

        # Sincronización bidireccional entre punto_venta y punto_de_venta
        if self.punto_venta and not self.punto_de_venta:
            self.punto_de_venta = self.punto_venta
        elif self.punto_de_venta and not self.punto_venta:
            self.punto_venta = self.punto_de_venta

        # Sincronización bidireccional de estado operativo
        if self.estado == 'CERRADA' or self.abierta is False:
            self.estado = 'CERRADA'
            self.abierta = False
        else:
            self.estado = 'ABIERTA'
            self.abierta = True

        # Sincronización de totales y diferencias contables
        if self.total_ventas_sistema and not self.total_ventas:
            self.total_ventas = self.total_ventas_sistema
        elif self.total_ventas and not self.total_ventas_sistema:
            self.total_ventas_sistema = self.total_ventas
        elif self.total_ventas_sistema:
            self.total_ventas = self.total_ventas_sistema

        if self.total_efectivo_declarado is not None and (self.monto_real is None or self.monto_real == 0 or self.monto_real == Decimal('0.00')):
            self.monto_real = self.total_efectivo_declarado
        elif self.monto_real is not None and (self.total_efectivo_declarado is None or self.total_efectivo_declarado == 0 or self.total_efectivo_declarado == Decimal('0.00')):
            self.total_efectivo_declarado = self.monto_real
        elif self.total_efectivo_declarado is not None:
            self.monto_real = self.total_efectivo_declarado

        if self.diferencia_cuadratura is not None and (self.diferencia is None or self.diferencia == 0 or self.diferencia == Decimal('0.00')):
            self.diferencia = self.diferencia_cuadratura
        elif self.diferencia is not None and (self.diferencia_cuadratura is None or self.diferencia_cuadratura == 0 or self.diferencia_cuadratura == Decimal('0.00')):
            self.diferencia_cuadratura = self.diferencia
        elif self.diferencia_cuadratura is not None:
            self.diferencia = self.diferencia_cuadratura

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Caja {'Abierta' if self.abierta else 'Cerrada'} (Estado: {self.estado}) - Apertura: {self.fecha_apertura} (Inicial: ${self.monto_inicial})"


class Venta(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='ventas', null=True, blank=True)
    mesero = models.ForeignKey(Usuario, on_delete=models.SET_NULL, related_name='ventas_mesero', null=True, blank=True)
    control_caja = models.ForeignKey(ControlCaja, on_delete=models.SET_NULL, related_name='ventas', null=True, blank=True)
    metodo_pago = models.CharField(max_length=20, default='efectivo')  # 'efectivo', 'tarjeta', 'transferencia'
    tipo_venta = models.CharField(max_length=20, default='barra', help_text="'barra' o 'mesa'")
    mesa = models.ForeignKey(Mesa, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas')
    notas = models.TextField(blank=True, default='', help_text="Comentarios o notas de comanda")
    fecha = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    @property
    def folio(self):
        return f"BOL-{self.id:04d}"

    @property
    def cajero(self):
        return self.usuario

    def __str__(self):
        return f"Venta {self.id} - Total: {self.total} ({self.metodo_pago}) [{self.tipo_venta}]"


class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='detalles', null=True, blank=True)
    cantidad = models.IntegerField(default=1)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre if self.producto else 'Item'}"


class ComandaQuerySet(models.QuerySet):
    """QuerySet personalizado para Comanda que soporta filtrado estricto por mesa_id."""
    def filter(self, *args, **kwargs):
        if 'mesa_id' in kwargs:
            kwargs['mesa_rel_id'] = kwargs.pop('mesa_id')
        return super().filter(*args, **kwargs)

    def get(self, *args, **kwargs):
        if 'mesa_id' in kwargs:
            kwargs['mesa_rel_id'] = kwargs.pop('mesa_id')
        return super().get(*args, **kwargs)


class Comanda(models.Model):
    folio = models.CharField(max_length=50)
    mesa = models.CharField(max_length=50, default='Mesa 1')
    mesa_rel = models.ForeignKey(Mesa, on_delete=models.SET_NULL, null=True, blank=True, related_name='comandas')
    mesero = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='comandas_mesero')
    venta = models.ForeignKey(Venta, on_delete=models.SET_NULL, null=True, blank=True, related_name='comandas')
    items = models.TextField(help_text="Detalle de productos en formato texto")
    items_json = models.TextField(blank=True, default='[]', help_text="Detalle de productos en formato JSON")
    notas = models.TextField(blank=True, default='', help_text="Notas o comentarios para cocina")
    tipo_pedido = models.CharField(max_length=20, default='barra', help_text="'barra' o 'mesa'")
    pagada = models.BooleanField(default=False)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, default='preparacion', help_text="'en_espera', 'preparacion', 'PREPARANDO', 'listo', 'LISTO', 'entregado', 'ENTREGADO', 'RE_ORDEN', 'LISTO_PARA_COBRO'")
    es_reemision = models.BooleanField(default=False, help_text="Indica si la comanda fue re-emitida para cambios o recalentados")
    motivo_reemision = models.CharField(max_length=150, blank=True, null=True, help_text="Motivo de la re-emisión o re-orden")
    fecha = models.DateTimeField(auto_now_add=True)

    objects = ComandaQuerySet.as_manager()

    @property
    def mesa_id(self):
        return self.mesa_rel_id if self.mesa_rel else None

    def save(self, *args, **kwargs):
        if not self.mesa_rel and self.mesa:
            m = Mesa.objects.filter(nombre=self.mesa).first()
            if m:
                self.mesa_rel = m
        elif self.mesa_rel and (not self.mesa or self.mesa == 'Mesa 1'):
            self.mesa = self.mesa_rel.nombre
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Comanda {self.folio} - {self.mesa} ({self.estado})"


class SecuenciaFolio(models.Model):
    tipo = models.CharField(max_length=20, unique=True, help_text="Tipo de secuencia ('venta', 'comanda')")
    ultimo_numero = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.tipo}: {self.ultimo_numero}"


def obtener_siguiente_folio(tipo='comanda'):
    """Genera de manera concurrente y segura el siguiente folio correlativo."""
    secuencia, _ = SecuenciaFolio.objects.get_or_create(tipo=tipo)
    secuencia.ultimo_numero += 1
    secuencia.save()
    prefijo = 'BOL' if tipo == 'venta' else 'COM'
    return f"{prefijo}-{secuencia.ultimo_numero:04d}"


def registrar_auditoria(usuario, accion, modulo, detalle=''):
    """Registra de manera segura una acción en la bitácora de auditoría."""
    try:
        u = None
        if isinstance(usuario, Usuario):
            u = usuario
        elif isinstance(usuario, dict) and 'id' in usuario:
            u = Usuario.objects.filter(id=usuario['id']).first()
        elif hasattr(usuario, 'id'):
            u = Usuario.objects.filter(id=usuario.id).first()

        return HistorialAccion.objects.create(
            usuario=u,
            accion=accion,
            modulo=modulo,
            detalle=detalle
        )
    except Exception:
        return None
