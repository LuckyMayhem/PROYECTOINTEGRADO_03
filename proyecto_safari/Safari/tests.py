import os
import json
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.conf import settings
from django.urls import reverse, resolve
from django.contrib.messages import get_messages
from .models import (
    Usuario,
    Producto,
    Mesa,
    ControlCaja,
    Venta,
    DetalleVenta,
    Comanda,
    SecuenciaFolio,
    PuntoDeVenta,
    Menu,
    HistorialAccion
)
class PruebasModelosTestCase(TestCase):
    """
    Pruebas unitarias para la capa de Modelos del ORM:
    - Creación y verificación de atributos en Usuario, Producto, Mesa y ControlCaja.
    - Validación de métodos auxiliares, propiedades (folio, cajero) y cálculo de totales.
    """

    def setUp(self):
        self.usuario = Usuario.objects.create(
            nombre="Carlos Administrador",
            correo="carlos@safari.cl",
            username="carlos_admin",
            password="adminpassword123",
            rol="administrador"
        )
        self.producto = Producto.objects.create(
            nombre="Hamburguesa Safari Clásica",
            descripcion="Carne de res premium con queso cheddar y papas fritas",
            precio=Decimal("6500.00"),
            stock=25
        )
        self.mesa = Mesa.objects.create(
            numero=4,
            nombre="Mesa Terraza 4",
            estado="desocupada",
            comida_entregada=False
        )
        self.caja = ControlCaja.objects.create(
            abierta=True,
            cajero_responsable=self.usuario,
            monto_inicial=Decimal("50000.00"),
            total_ventas=Decimal("0.00"),
            total_efectivo=Decimal("0.00"),
            total_tarjeta=Decimal("0.00"),
            total_transferencia=Decimal("0.00")
        )

    def test_creacion_y_campos_usuario(self):
        """Verifica la correcta persistencia y representación del modelo Usuario."""
        self.assertEqual(self.usuario.nombre, "Carlos Administrador")
        self.assertEqual(self.usuario.correo, "carlos@safari.cl")
        self.assertEqual(self.usuario.username, "carlos_admin")
        self.assertEqual(self.usuario.rol, "administrador")
        self.assertEqual(str(self.usuario), "Carlos Administrador (administrador)")

    def test_creacion_y_campos_producto(self):
        """Verifica la persistencia de campos y método __str__ de Producto."""
        self.assertEqual(self.producto.nombre, "Hamburguesa Safari Clásica")
        self.assertEqual(self.producto.precio, Decimal("6500.00"))
        self.assertEqual(self.producto.stock, 25)
        self.assertEqual(str(self.producto), "Hamburguesa Safari Clásica")

    def test_creacion_y_campos_mesa(self):
        """Verifica la persistencia y estados de la Mesa."""
        self.assertEqual(self.mesa.numero, 4)
        self.assertEqual(self.mesa.nombre, "Mesa Terraza 4")
        self.assertEqual(self.mesa.estado, "desocupada")
        self.assertFalse(self.mesa.comida_entregada)
        self.assertEqual(str(self.mesa), "Mesa Terraza 4 (desocupada)")

    def test_creacion_control_caja_y_calculo_totales(self):
        """Verifica la apertura de caja, creación de Venta, DetalleVenta y cálculo de totales."""
        self.assertTrue(self.caja.abierta)
        self.assertEqual(self.caja.cajero_responsable, self.usuario)
        self.assertEqual(self.caja.monto_inicial, Decimal("50000.00"))
        self.assertIn("Caja Abierta", str(self.caja))

        # Crear una venta vinculada a la caja
        venta = Venta.objects.create(
            usuario=self.usuario,
            control_caja=self.caja,
            metodo_pago="efectivo",
            total=Decimal("13000.00")
        )

        # Crear dos detalles de venta asociados
        detalle = DetalleVenta.objects.create(
            venta=venta,
            producto=self.producto,
            cantidad=2,
            subtotal=Decimal("13000.00")
        )

        # Comprobar métodos auxiliares y propiedades
        self.assertEqual(venta.folio, f"BOL-{venta.id:04d}")
        self.assertEqual(venta.cajero, self.usuario)
        self.assertIn(f"Venta {venta.id}", str(venta))
        self.assertEqual(str(detalle), f"2 x {self.producto.nombre}")

        # Comprobar consistencia del subtotal calculado
        calculo_esperado = self.producto.precio * detalle.cantidad
        self.assertEqual(detalle.subtotal, calculo_esperado)

    def test_modelo_control_caja_campos_formales_y_arqueo(self):
        """Verifica todos los campos y métodos formales del modelo ControlCaja según auditoría."""
        pv = PuntoDeVenta.objects.create(nombre="Caja Principal", ubicacion="Salón")
        caja = ControlCaja.objects.create(
            usuario=self.usuario,
            punto_venta=pv,
            monto_inicial=Decimal("35000.00"),
            estado='ABIERTA',
            billetes_20000=2,
            billetes_10000=3,
            billetes_5000=2,
            billetes_1000=4,
            monedas_500=4,
            monedas_100=5,
            monedas_50=2,
            monedas_5=4,
            monedas_1=10
        )

        # Verificación de sincronización bidireccional
        self.assertEqual(caja.cajero_responsable, self.usuario)
        self.assertEqual(caja.punto_de_venta, pv)
        self.assertTrue(caja.abierta)
        self.assertEqual(caja.estado, 'ABIERTA')
        self.assertEqual(caja.monto_inicial, Decimal("35000.00"))

        # Verificación de campos de desglose de efectivo
        self.assertEqual(caja.billetes_20000, 2)
        self.assertEqual(caja.billetes_10000, 3)
        self.assertEqual(caja.billetes_5000, 2)
        self.assertEqual(caja.billetes_1000, 4)
        self.assertEqual(caja.monedas_500, 4)
        self.assertEqual(caja.monedas_100, 5)
        self.assertEqual(caja.monedas_50, 2)
        self.assertEqual(caja.monedas_5, 4)
        self.assertEqual(caja.monedas_1, 10)

        # Cálculo esperado de arqueo:
        # Billetes: (2*20000) + (3*10000) + (2*5000) + (4*1000) = 40000 + 30000 + 10000 + 4000 = 84000
        # Monedas: (4*500) + (5*100) + (2*50) + (4*5) + (10*1) = 2000 + 500 + 100 + 20 + 10 = 2630
        # Total Arqueo = 84000 + 2630 = 86630
        self.assertEqual(caja.calcular_total_arqueo_efectivo(), 86630)

        # Cierre y actualización de estado
        caja.estado = 'CERRADA'
        caja.total_ventas_sistema = Decimal("50000.00")
        caja.total_efectivo_declarado = Decimal("86630.00")
        caja.diferencia_cuadratura = Decimal("1630.00")
        caja.save()

        caja.refresh_from_db()
        self.assertFalse(caja.abierta)
        self.assertEqual(caja.estado, 'CERRADA')
        self.assertEqual(caja.total_ventas, Decimal("50000.00"))
        self.assertEqual(caja.monto_real, Decimal("86630.00"))
        self.assertEqual(caja.diferencia, Decimal("1630.00"))
class PruebasAutenticacionTestCase(TestCase):
    """
    Pruebas de autenticación, validación de formularios y control de sesiones:
    - Login exitoso según rol (cajero, mesero, cocinero, administrador).
    - Rechazo por contraseña incorrecta o usuario inexistente.
    - Validación de campos vacíos en el formulario de login.
    - Cierre de sesión (logout).
    """

    def setUp(self):
        self.client = Client()

        # Creación de usuarios para cada uno de los cuatro roles del sistema
        self.admin = Usuario.objects.create(
            nombre="Admin Safari",
            correo="admin@safari.cl",
            username="admin_user",
            password="adminpassword123",
            rol="administrador"
        )
        self.cajero = Usuario.objects.create(
            nombre="Cajero Central",
            correo="cajero@safari.cl",
            username="cajero_user",
            password="cajeropassword123",
            rol="cajero"
        )
        self.mesero = Usuario.objects.create(
            nombre="Mesero Salón",
            correo="mesero@safari.cl",
            username="mesero_user",
            password="meseropassword123",
            rol="mesero"
        )
        self.cocinero = Usuario.objects.create(
            nombre="Cocinero Maestro",
            correo="cocinero@safari.cl",
            username="cocinero_user",
            password="cocineropassword123",
            rol="cocinero"
        )

    def test_login_exitoso_administrador(self):
        """Verifica que el login con credenciales de Administrador redirija a /administrador/."""
        response = self.client.post('/login/', {
            'username': 'admin_user',
            'password': 'adminpassword123'
        })
        self.assertRedirects(response, '/administrador/')
        session_user = self.client.session.get('usuario')
        self.assertIsNotNone(session_user)
        self.assertEqual(session_user['rol'], 'administrador')

    def test_login_exitoso_cajero(self):
        """Verifica que el login con credenciales de Cajero redirija a /cajero/."""
        response = self.client.post('/login/', {
            'username': 'cajero_user',
            'password': 'cajeropassword123'
        })
        self.assertRedirects(response, '/cajero/')
        session_user = self.client.session.get('usuario')
        self.assertIsNotNone(session_user)
        self.assertEqual(session_user['rol'], 'cajero')

    def test_login_exitoso_mesero(self):
        """Verifica que el login con credenciales de Mesero redirija a /mesero/."""
        response = self.client.post('/login/', {
            'username': 'mesero_user',
            'password': 'meseropassword123'
        })
        self.assertRedirects(response, '/mesero/')
        session_user = self.client.session.get('usuario')
        self.assertIsNotNone(session_user)
        self.assertEqual(session_user['rol'], 'mesero')

    def test_login_exitoso_cocinero(self):
        """Verifica que el login con credenciales de Cocinero redirija a /cocinero/."""
        response = self.client.post('/login/', {
            'username': 'cocinero_user',
            'password': 'cocineropassword123'
        })
        self.assertRedirects(response, '/cocinero/')
        session_user = self.client.session.get('usuario')
        self.assertIsNotNone(session_user)
        self.assertEqual(session_user['rol'], 'cocinero')

    def test_login_exitoso_utilizando_correo(self):
        """Verifica que el inicio de sesión funcione tanto con nombre de usuario como con correo electrónico."""
        response = self.client.post('/login/', {
            'username': 'cajero@safari.cl',
            'password': 'cajeropassword123'
        })
        self.assertRedirects(response, '/cajero/')
        session_user = self.client.session.get('usuario')
        self.assertIsNotNone(session_user)
        self.assertEqual(session_user['username'], 'cajero_user')

    def test_rechazo_contrasena_incorrecta(self):
        """Verifica que se deniegue el acceso cuando la contraseña ingresada no coincide."""
        response = self.client.post('/login/', {
            'username': 'admin_user',
            'password': 'password_erronea_999'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Usuario o contraseña incorrectos')
        self.assertIsNone(self.client.session.get('usuario'))

    def test_rechazo_usuario_inexistente(self):
        """Verifica el rechazo seguro ante un identificador de usuario no registrado en el sistema."""
        response = self.client.post('/login/', {
            'username': 'usuario_fantasma',
            'password': 'cualquier_clave'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Usuario o contraseña incorrectos')
        self.assertIsNone(self.client.session.get('usuario'))

    def test_validacion_campos_vacios_login(self):
        """Verifica que el formulario exija obligatoriamente usuario y contraseña."""
        response = self.client.post('/login/', {
            'username': '',
            'password': ''
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Debe ingresar tanto el usuario como la contraseña')

    def test_cierre_de_sesion(self):
        """Verifica que el endpoint de logout limpie la sesión y redirija a /login/."""
        # Iniciar sesión previamente
        self.client.post('/login/', {'username': 'cajero_user', 'password': 'cajeropassword123'})
        self.assertIsNotNone(self.client.session.get('usuario'))

        # Cerrar sesión
        response = self.client.get('/logout/')
        self.assertRedirects(response, '/login/')
        self.assertIsNone(self.client.session.get('usuario'))
class PruebasFlujoOperativoTestCase(TestCase):
    """
    Pruebas del flujo operativo completo del restaurante:
    - Apertura de caja obligatoria y verificación de estado activo.
    - Bloqueo estricto de ventas si la caja no está abierta.
    - Registro de venta, asignación a la caja y descuento de stock en productos.
    - Generación automática de comanda para cocina y ciclo de estados (preparación -> listo -> entregado).
    - Cierre de jornada con arqueo y cálculo de diferencias (sobrante / faltante).
    """

    def setUp(self):
        self.client = Client()

        # Usuarios
        self.cajero = Usuario.objects.create(
            nombre="Javier Cajero",
            correo="javier@safari.cl",
            username="javier_cajero",
            password="password123",
            rol="cajero"
        )
        self.mesero = Usuario.objects.create(
            nombre="Pedro Mesero",
            correo="pedro@safari.cl",
            username="pedro_mesero",
            password="password123",
            rol="mesero"
        )
        self.cocinero = Usuario.objects.create(
            nombre="Lucas Cocinero",
            correo="lucas@safari.cl",
            username="lucas_cocinero",
            password="password123",
            rol="cocinero"
        )
        self.admin = Usuario.objects.create(
            nombre="Admin Jefe",
            correo="jefe@safari.cl",
            username="admin_jefe",
            password="password123",
            rol="administrador"
        )

        # Productos de prueba
        self.prod_hamburguesa = Producto.objects.create(
            nombre="Hamburguesa Safari Doble",
            descripcion="Doble carne, queso cheddar y tocino",
            precio=Decimal("7000.00"),
            stock=10
        )
        self.prod_bebida = Producto.objects.create(
            nombre="Bebida Cola 500cc",
            descripcion="Bebida refrescante",
            precio=Decimal("2000.00"),
            stock=15
        )

        # Mesa
        self.mesa = Mesa.objects.create(numero=1, nombre="Mesa 1", estado="ocupada")

    def _autenticar_como(self, usuario):
        """Método auxiliar para simular la sesión de un usuario."""
        session = self.client.session
        session['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'username': usuario.username,
            'rol': usuario.rol,
        }
        session.save()

    def test_bloqueo_venta_si_caja_cerrada(self):
        """Verifica que el sistema rechace con HTTP 400 cualquier venta si no hay caja abierta."""
        # Asegurar que no hay caja abierta
        ControlCaja.objects.all().delete()

        self._autenticar_como(self.cajero)
        payload = {
            'items': [{'id': self.prod_hamburguesa.id, 'cantidad': 1}],
            'total': 7000,
            'mesa': 'Mesa 1',
            'metodo_pago': 'efectivo',
            'mesero_id': self.mesero.id
        }
        response = self.client.post(
            '/cajero/registrar-venta/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn("CERRADA", data['error'])

    def test_apertura_caja_y_verificacion_estado_activo(self):
        """Verifica la apertura obligatoria de jornada y registro de fondo inicial."""
        ControlCaja.objects.all().delete()
        self._autenticar_como(self.admin)

        response = self.client.post(
            '/caja/abrir/',
            data=json.dumps({
                'cajero_id': self.cajero.id,
                'monto_inicial': 45000
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        # Comprobar en base de datos
        caja_activa = ControlCaja.objects.filter(abierta=True).first()
        self.assertIsNotNone(caja_activa)
        self.assertEqual(caja_activa.cajero_responsable, self.cajero)
        self.assertEqual(caja_activa.monto_inicial, Decimal("45000.00"))

    def test_registro_venta_y_descuento_de_stock(self):
        """Verifica el registro de venta, creación de detalles y descuento exacto de inventario."""
        # 1. Apertura de caja previa
        caja = ControlCaja.objects.create(
            abierta=True,
            cajero_responsable=self.cajero,
            monto_inicial=Decimal("30000.00")
        )

        stock_inicial_hamburguesa = self.prod_hamburguesa.stock  # 10
        stock_inicial_bebida = self.prod_bebida.stock            # 15

        self._autenticar_como(self.cajero)
        payload = {
            'items': [
                {'id': self.prod_hamburguesa.id, 'cantidad': 2},
                {'id': self.prod_bebida.id, 'cantidad': 3}
            ],
            'total': 20000,
            'mesa': 'Mesa 1',
            'metodo_pago': 'efectivo',
            'mesero_id': self.mesero.id
        }

        response = self.client.post(
            '/cajero/registrar-venta/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        # 2. Verificar descuento en stock
        self.prod_hamburguesa.refresh_from_db()
        self.prod_bebida.refresh_from_db()
        self.assertEqual(self.prod_hamburguesa.stock, stock_inicial_hamburguesa - 2)
        self.assertEqual(self.prod_bebida.stock, stock_inicial_bebida - 3)

        # 3. Verificar creación de Venta y DetalleVenta
        venta = Venta.objects.filter(control_caja=caja).latest('id')
        self.assertEqual(venta.total, Decimal("20000.00"))
        self.assertEqual(venta.metodo_pago, 'efectivo')
        self.assertEqual(venta.mesero, self.mesero)
        self.assertEqual(venta.detalles.count(), 2)

    def test_generacion_comanda_y_cambio_de_estado_en_cocina(self):
        """Verifica que una venta genere una comanda y que el cocinero pueda cambiar su estado."""
        # 1. Crear comanda inicial en estado 'preparacion'
        comanda = Comanda.objects.create(
            folio="BOL-9999",
            mesa="Mesa 1",
            items="2x Hamburguesa Safari Doble ($14000)",
            total=Decimal("14000.00"),
            estado="preparacion"
        )
        self.assertEqual(comanda.estado, "preparacion")

        # 2. Autenticar como cocinero y cambiar a 'listo'
        self._autenticar_como(self.cocinero)
        response_listo = self.client.post(
            '/cocina/cambiar-estado/',
            data=json.dumps({
                'comanda_id': comanda.id,
                'nuevo_estado': 'listo'
            }),
            content_type='application/json'
        )
        self.assertEqual(response_listo.status_code, 200)
        self.assertTrue(response_listo.json()['success'])

        comanda.refresh_from_db()
        self.assertEqual(comanda.estado, "listo")

        # 3. Cambiar a 'entregado'
        response_entregado = self.client.post(
            '/cocina/cambiar-estado/',
            data=json.dumps({
                'comanda_id': comanda.id,
                'nuevo_estado': 'entregado'
            }),
            content_type='application/json'
        )
        self.assertEqual(response_entregado.status_code, 200)
        self.assertTrue(response_entregado.json()['success'])

        comanda.refresh_from_db()
        self.assertEqual(comanda.estado, "entregado")

    def test_cierre_de_caja_con_arqueo_y_diferencias(self):
        """Verifica el cálculo de arqueo: monto inicial + ventas efectivo vs monto contado."""
        # 1. Caja abierta con fondo inicial de $50,000
        caja = ControlCaja.objects.create(
            abierta=True,
            cajero_responsable=self.cajero,
            monto_inicial=Decimal("50000.00")
        )

        # 2. Venta en efectivo por $15,000 y venta con tarjeta por $10,000
        Venta.objects.create(usuario=self.cajero, control_caja=caja, metodo_pago="efectivo", total=Decimal("15000.00"))
        Venta.objects.create(usuario=self.cajero, control_caja=caja, metodo_pago="tarjeta", total=Decimal("10000.00"))

        # El efectivo esperado en gaveta es: $50,000 + $15,000 = $65,000
        # Supongamos que el cajero cuenta $66,000 (sobrante de $1,000)
        self._autenticar_como(self.admin)
        response = self.client.post(
            '/caja/cerrar/',
            data=json.dumps({'monto_real': 66000}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['arqueo']['diferencia'], 1000.0)
        self.assertEqual(data['arqueo']['estado_diferencia'], 'sobrante')

        caja.refresh_from_db()
        self.assertFalse(caja.abierta)
        self.assertEqual(caja.total_ventas, Decimal("25000.00"))
        self.assertEqual(caja.total_efectivo, Decimal("15000.00"))
        self.assertEqual(caja.total_tarjeta, Decimal("10000.00"))
        self.assertEqual(caja.diferencia, Decimal("1000.00"))

    def test_apertura_caja_rechaza_si_cajero_ya_tiene_caja_abierta(self):
        """Verifica que un cajero no pueda abrir dos cajas simultáneas en estado ABIERTA."""
        ControlCaja.objects.all().delete()
        self._autenticar_como(self.admin)

        # 1. Primera apertura exitosa
        resp1 = self.client.post(
            '/caja/abrir/',
            data=json.dumps({'cajero_id': self.cajero.id, 'monto_inicial': 30000}),
            content_type='application/json'
        )
        self.assertEqual(resp1.status_code, 200)
        self.assertTrue(resp1.json()['success'])

        # 2. Intento de segunda apertura para el mismo cajero debe ser rechazado
        resp2 = self.client.post(
            '/caja/abrir/',
            data=json.dumps({'cajero_id': self.cajero.id, 'monto_inicial': 20000}),
            content_type='application/json'
        )
        self.assertEqual(resp2.status_code, 400)
        data2 = resp2.json()
        self.assertFalse(data2['success'])
        self.assertIn("ABIERTA", data2['error'])

    def test_apertura_caja_validacion_monto_inicial_obligatorio_y_positivo(self):
        """Verifica que se exija un monto_inicial numérico mayor o igual a 0."""
        ControlCaja.objects.all().delete()
        self._autenticar_como(self.admin)

        # Caso a: monto inicial negativo
        resp_negativo = self.client.post(
            '/caja/abrir/',
            data=json.dumps({'cajero_id': self.cajero.id, 'monto_inicial': -5000}),
            content_type='application/json'
        )
        self.assertEqual(resp_negativo.status_code, 400)
        self.assertFalse(resp_negativo.json()['success'])

        # Caso b: monto inicial no numérico
        resp_letras = self.client.post(
            '/caja/abrir/',
            data=json.dumps({'cajero_id': self.cajero.id, 'monto_inicial': 'mil'}),
            content_type='application/json'
        )
        self.assertEqual(resp_letras.status_code, 400)
        self.assertFalse(resp_letras.json()['success'])

        # Caso c: monto inicial ausente
        resp_vacio = self.client.post(
            '/caja/abrir/',
            data=json.dumps({'cajero_id': self.cajero.id}),
            content_type='application/json'
        )
        self.assertEqual(resp_vacio.status_code, 400)
        self.assertFalse(resp_vacio.json()['success'])

    def test_cierre_caja_con_arqueo_detallado_y_recalculo_servidor(self):
        """
        Verifica el cierre y cuadratura con conteo de billetes y monedas:
        - Envío de conteo físico de cada denominación.
        - Recálculo obligatorio en backend ignorando manipulaciones del cliente en monto_real.
        - Registro exacto de diferencia de cuadratura y actualización del estado a CERRADA.
        """
        ControlCaja.objects.all().delete()
        caja = ControlCaja.objects.create(
            abierta=True,
            estado='ABIERTA',
            usuario=self.cajero,
            cajero_responsable=self.cajero,
            monto_inicial=Decimal("50000.00")
        )

        # Ventas en el turno: $15.000 efectivo y $10.000 tarjeta
        Venta.objects.create(usuario=self.cajero, control_caja=caja, metodo_pago="efectivo", total=Decimal("15000.00"))
        Venta.objects.create(usuario=self.cajero, control_caja=caja, metodo_pago="tarjeta", total=Decimal("10000.00"))
        # Efectivo esperado en gaveta: 50.000 + 15.000 = $65.000 CLP

        # Arqueo físico:
        # Billetes: 2 x $20.000 ($40.000) + 2 x $10.000 ($20.000) + 1 x $5.000 ($5.000) + 1 x $1.000 ($1.000) = $66.000
        # Monedas: 1 x $500 ($500) + 2 x $100 ($200) + 1 x $50 ($50) + 1 x $5 ($5) + 5 x $1 ($5) = $760
        # Total Real Recalculado en Backend = $66.760 CLP (Sobrante: +$1.760 CLP)
        self._autenticar_como(self.admin)
        payload = {
            'billetes_20000': 2,
            'billetes_10000': 2,
            'billetes_5000': 1,
            'billetes_1000': 1,
            'monedas_500': 1,
            'monedas_100': 2,
            'monedas_50': 1,
            'monedas_5': 1,
            'monedas_1': 5,
            'monto_real': 999999  # Manipulación intencional enviada por cliente
        }

        response = self.client.post('/caja/cerrar/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        # Comprobar que el backend RECALCULÓ obligatoriamente el total sin fiarse del cliente
        self.assertEqual(data['arqueo']['total_efectivo_declarado'], 66760.0)
        self.assertEqual(data['arqueo']['diferencia_cuadratura'], 1760.0)
        self.assertEqual(data['arqueo']['estado_diferencia'], 'sobrante')
        self.assertEqual(data['arqueo']['estado'], 'CERRADA')

        # Comprobar persistencia detallada en la base de datos
        caja.refresh_from_db()
        self.assertEqual(caja.estado, 'CERRADA')
        self.assertFalse(caja.abierta)
        self.assertEqual(caja.total_ventas_sistema, Decimal("25000.00"))
        self.assertEqual(caja.total_efectivo_declarado, Decimal("66760.00"))
        self.assertEqual(caja.diferencia_cuadratura, Decimal("1760.00"))
        self.assertEqual(caja.billetes_20000, 2)
        self.assertEqual(caja.billetes_10000, 2)
        self.assertEqual(caja.billetes_5000, 1)
        self.assertEqual(caja.billetes_1000, 1)
        self.assertEqual(caja.monedas_500, 1)
        self.assertEqual(caja.monedas_100, 2)
        self.assertEqual(caja.monedas_50, 1)
        self.assertEqual(caja.monedas_5, 1)
        self.assertEqual(caja.monedas_1, 5)
        self.assertEqual(caja.calcular_total_arqueo_efectivo(), 66760)

    def test_bloqueo_operativo_venta_si_punto_venta_no_abierto(self):
        """Verifica que no se pueda registrar una venta si la caja o el punto de venta no están en estado ABIERTA."""
        ControlCaja.objects.all().delete()
        pv1 = PuntoDeVenta.objects.create(nombre="Caja Principal Salon", estado="activo")
        pv2 = PuntoDeVenta.objects.create(nombre="Caja Secundaria Barra", estado="activo")

        self._autenticar_como(self.cajero)

        # 1. Sin ninguna caja abierta
        response = self.client.post(
            '/cajero/registrar-venta/',
            data=json.dumps({
                'items': [{'id': self.prod_hamburguesa.id, 'cantidad': 1}],
                'total': 8500,
                'metodo_pago': 'efectivo',
                'punto_venta_id': pv1.id
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn("Operación no permitida", data['error'])

        # 2. Con caja abierta para pv1, intento de venta en pv2 sin caja abierta debe ser bloqueado
        caja_pv1 = ControlCaja.objects.create(
            abierta=True,
            estado='ABIERTA',
            usuario=self.cajero,
            punto_venta=pv1,
            monto_inicial=Decimal("30000.00")
        )

        response_pv2 = self.client.post(
            '/cajero/registrar-venta/',
            data=json.dumps({
                'items': [{'id': self.prod_hamburguesa.id, 'cantidad': 1}],
                'total': 8500,
                'metodo_pago': 'efectivo',
                'punto_venta_id': pv2.id
            }),
            content_type='application/json'
        )
        self.assertEqual(response_pv2.status_code, 400)
        data_pv2 = response_pv2.json()
        self.assertFalse(data_pv2['success'])
        self.assertIn("punto de venta no está ABIERTA", data_pv2['error'])
class PruebasManejoErroresHTTPTestCase(TestCase):
    """
    Pruebas de visualización y personalización de respuestas y errores HTTP:
    - Retorno de código 404 ante rutas no declaradas como problema de enrutamiento general.
    - Respuesta HTTP 401 (No Autenticado) ante intentos de ingresar a rutas protegidas sin sesión.
    - Respuesta HTTP 403 (Acceso Prohibido / Rol no autorizado) cuando un rol intenta ingresar a otro módulo vía URL.
    - Respuesta HTTP 400 (Petición Incorrecta) ante el envío de malos datos o parámetros inválidos.
    """

    def setUp(self):
        self.client = Client()
        self.admin = Usuario.objects.create(
            nombre="Admin Principal",
            correo="admin@safari.cl",
            username="admin_test",
            password="password123",
            rol="administrador"
        )
        self.cajero = Usuario.objects.create(
            nombre="Cajero Central",
            correo="cajero@safari.cl",
            username="cajero_test",
            password="password123",
            rol="cajero"
        )
        self.mesero = Usuario.objects.create(
            nombre="Mario Mesero",
            correo="mario@safari.cl",
            username="mario_mesero",
            password="password123",
            rol="mesero"
        )
        self.cocinero = Usuario.objects.create(
            nombre="Lucas Cocinero",
            correo="lucas@safari.cl",
            username="lucas_cocinero",
            password="password123",
            rol="cocinero"
        )

    def _autenticar_como(self, usuario):
        """Simula la sesión del usuario especificado."""
        session = self.client.session
        session['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'username': usuario.username,
            'rol': usuario.rol,
        }
        session.save()

    def test_ruta_no_declarada_capturada_por_enrutamiento_404(self):
        """Verifica que cualquier ruta no declarada sea capturada por el enrutamiento general y retorne código 404."""
        response = self.client.get('/esta/ruta/no/existe/en/el/sistema/')
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, 'errors/404.html')
        self.assertContains(response, '404', status_code=404)

    def test_vista_explicita_error_404(self):
        """Verifica el endpoint de apoyo /error/404/ configurado en el sistema."""
        response = self.client.get('/error/404/')
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, 'errors/404.html')

    def test_acceso_sin_autenticacion_retorna_401(self):
        """Verifica que un usuario anónimo sin sesión que intente ingresar a rutas protegidas reciba HTTP 401."""
        rutas_protegidas = ['/cajero/', '/mesero/', '/cocinero/', '/administrador/', '/stock/', '/ventas/']
        for ruta in rutas_protegidas:
            response = self.client.get(ruta)
            self.assertEqual(response.status_code, 401, f"La ruta {ruta} no retornó 401 para usuario sin sesión")
            self.assertTemplateUsed(response, 'errors/401.html')
            self.assertContains(response, '401', status_code=401)

    def test_vista_explicita_error_401_plantilla(self):
        """Verifica que el endpoint /error/401/ retorne código 401 y renderice errors/401.html."""
        response = self.client.get('/error/401/')
        self.assertEqual(response.status_code, 401)
        self.assertTemplateUsed(response, 'errors/401.html')

    def test_cajero_intentando_entrar_a_cocinero_retorna_403(self):
        """Verifica que un cajero autenticado que intente ingresar a /cocinero/ por URL reciba HTTP 403."""
        self._autenticar_como(self.cajero)
        response = self.client.get('/cocinero/')
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'errors/403.html')
        self.assertContains(response, '403', status_code=403)

    def test_cajero_intentando_entrar_a_administrador_retorna_403(self):
        """Verifica que un cajero autenticado que intente ingresar a /administrador/ por URL reciba HTTP 403."""
        self._autenticar_como(self.cajero)
        response = self.client.get('/administrador/')
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'errors/403.html')

    def test_mesero_o_cocinero_intentando_acceder_a_stock_retorna_403(self):
        """Verifica que meseros y cocineros tengan prohibido el acceso a /stock/ con HTTP 403."""
        self._autenticar_como(self.mesero)
        res_mesero = self.client.get('/stock/')
        self.assertEqual(res_mesero.status_code, 403)
        self.assertTemplateUsed(res_mesero, 'errors/403.html')

        self._autenticar_como(self.cocinero)
        res_cocinero = self.client.get('/stock/')
        self.assertEqual(res_cocinero.status_code, 403)
        self.assertTemplateUsed(res_cocinero, 'errors/403.html')

    def test_vista_explicita_error_403_plantilla(self):
        """Verifica que el endpoint /error/403/ retorne código 403 y renderice errors/403.html."""
        response = self.client.get('/error/403/')
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'errors/403.html')
        self.assertContains(response, '403', status_code=403)

    def test_envio_mal_dato_en_producto_retorna_400(self):
        """Verifica que enviar un mal dato (precio negativo o nombre vacío) retorne HTTP 400."""
        self._autenticar_como(self.admin)
        # 1. Nombre vacío
        res_vacio = self.client.post('/stock/guardar/', {
            'nombre': '',
            'descripcion': 'Test',
            'precio': '5000',
            'stock': '10'
        })
        self.assertEqual(res_vacio.status_code, 400)
        self.assertTemplateUsed(res_vacio, 'errors/400.html')

        # 2. Precio negativo
        res_precio_invalido = self.client.post('/stock/guardar/', {
            'nombre': 'Pizza Mal Dato',
            'descripcion': 'Test',
            'precio': '-1500',
            'stock': '10'
        })
        self.assertEqual(res_precio_invalido.status_code, 400)
        self.assertTemplateUsed(res_precio_invalido, 'errors/400.html')

    def test_vista_explicita_error_400_plantilla(self):
        """Verifica que el endpoint /error/400/ retorne código 400 y renderice errors/400.html."""
        response = self.client.get('/error/400/')
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, 'errors/400.html')
class PruebasMantenedoresYAuditoriaTestCase(TestCase):
    """
    Suite de pruebas unitarias y de integración para:
    - Módulos Mantenedores CRUD (Usuarios, Mesas, Puntos de Venta, Menús, Productos).
    - Control de acceso por sesión de Administrador (HTTP 401 si no autenticado, 403 si rol no autorizado).
    - Inserción automática de registros en HistorialAccion ante CREAR, ACTUALIZAR y ELIMINAR.
    - Bitácora de Auditoría: listado y filtros por acción, módulo, usuario, fecha y texto.
    """

    def setUp(self):
        self.client = Client()

        # Usuario Administrador
        self.admin = Usuario.objects.create(
            rut="11.111.111-1",
            nombre="Administrador General",
            correo="admin@safari.cl",
            username="admin_test",
            password="adminpassword123",
            rol="administrador",
            estado="activo"
        )

        # Usuario Cajero para pruebas de restricción de permisos
        self.cajero = Usuario.objects.create(
            rut="22.222.222-2",
            nombre="Cajero Operativo",
            correo="cajero@safari.cl",
            username="cajero_test",
            password="cajeropassword123",
            rol="cajero",
            estado="activo"
        )

        # Menú base
        self.menu_fondos = Menu.objects.create(
            nombre="Platos Principales",
            descripcion="Platos de fondo tradicionales y carnes",
            estado="activo"
        )

        # Mesa base
        self.mesa_base = Mesa.objects.create(
            numero=10,
            nombre="Mesa Salón 10",
            capacidad=4,
            estado="disponible"
        )

        # Punto de Venta base
        self.pdv_base = PuntoDeVenta.objects.create(
            nombre="Caja Central Salón",
            ubicacion="Barra Principal",
            estado="activo"
        )

        # Producto base
        self.producto_base = Producto.objects.create(
            codigo="CAR-001",
            nombre="Lomo a lo Pobre",
            descripcion="Lomo vetado con papas fritas y huevo",
            precio=Decimal("9500.00"),
            stock=15,
            menu=self.menu_fondos
        )

    def _autenticar_como(self, usuario):
        """Helper para establecer la sesión con el usuario especificado."""
        session = self.client.session
        session['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'username': usuario.username,
            'rol': usuario.rol,
        }
        session.save()

    def test_mantenedores_sin_autenticacion_retorna_401(self):
        """Verifica que un usuario no autenticado reciba HTTP 401 en todas las rutas mantenedoras."""
        rutas = [
            '/mantenedores/',
            '/mantenedores/usuarios/',
            '/mantenedores/mesas/',
            '/mantenedores/puntos-de-venta/',
            '/mantenedores/menus/',
            '/mantenedores/productos/',
            '/mantenedores/auditoria/',
        ]
        for ruta in rutas:
            res = self.client.get(ruta)
            self.assertEqual(res.status_code, 401, f"La ruta {ruta} debía retornar 401 para usuario anónimo.")
            self.assertTemplateUsed(res, 'errors/401.html')

    def test_mantenedores_con_rol_no_admin_retorna_403(self):
        """Verifica que un usuario no administrador (como cajero) reciba HTTP 403 en los mantenedores."""
        self._autenticar_como(self.cajero)
        rutas = [
            '/mantenedores/',
            '/mantenedores/usuarios/',
            '/mantenedores/mesas/',
            '/mantenedores/puntos-de-venta/',
            '/mantenedores/menus/',
            '/mantenedores/productos/',
            '/mantenedores/auditoria/',
        ]
        for ruta in rutas:
            res = self.client.get(ruta)
            self.assertEqual(res.status_code, 403, f"La ruta {ruta} debía retornar 403 para rol cajero.")
            self.assertTemplateUsed(res, 'errors/403.html')

    def test_hub_mantenedores_carga_correctamente_para_admin(self):
        """Verifica que el panel principal de mantenedores retorne 200 y calcule contadores."""
        self._autenticar_como(self.admin)
        res = self.client.get('/mantenedores/')
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'mantenedores/index.html')
        self.assertIn('total_usuarios', res.context)
        self.assertIn('total_mesas', res.context)
        self.assertIn('total_pdv', res.context)
        self.assertIn('total_menus', res.context)
        self.assertIn('total_productos', res.context)
        self.assertIn('total_auditorias', res.context)

    # --------------------------------------------------------------------------
    # CRUD: Usuarios y Auditoría
    # --------------------------------------------------------------------------
    def test_crud_usuario_y_registro_auditoria(self):
        """Prueba completa de Crear, Actualizar y Eliminar Usuario con registro en HistorialAccion."""
        self._autenticar_como(self.admin)

        # 1. CREAR
        res_crear = self.client.post('/mantenedores/usuarios/guardar/', {
            'rut': '33.333.333-3',
            'nombre': 'Valeria Mesera',
            'correo': 'valeria@safari.cl',
            'username': 'valeria_mesera',
            'password': 'password123',
            'rol': 'mesero',
            'estado': 'activo'
        })
        self.assertEqual(res_crear.status_code, 302)
        nuevo_user = Usuario.objects.filter(username='valeria_mesera').first()
        self.assertIsNotNone(nuevo_user)
        self.assertEqual(nuevo_user.rut, '33.333.333-3')
        self.assertEqual(nuevo_user.rol, 'mesero')

        # Verificar auditoría de creación
        log_crear = HistorialAccion.objects.filter(modulo='Usuarios', accion='CREAR', detalle__icontains='valeria_mesera').first()
        self.assertIsNotNone(log_crear)
        self.assertEqual(log_crear.usuario, self.admin)

        # 2. ACTUALIZAR
        res_actualizar = self.client.post('/mantenedores/usuarios/guardar/', {
            'user_id': nuevo_user.id,
            'rut': '33.333.333-3',
            'nombre': 'Valeria Actualizada',
            'correo': 'valeria_nueva@safari.cl',
            'username': 'valeria_mesera',
            'password': '',
            'rol': 'mesero',
            'estado': 'inactivo'
        })
        self.assertEqual(res_actualizar.status_code, 302)
        nuevo_user.refresh_from_db()
        self.assertEqual(nuevo_user.nombre, 'Valeria Actualizada')
        self.assertEqual(nuevo_user.estado, 'inactivo')

        # Verificar auditoría de actualización
        log_act = HistorialAccion.objects.filter(modulo='Usuarios', accion='ACTUALIZAR', detalle__icontains='valeria_mesera').first()
        self.assertIsNotNone(log_act)

        # 3. ELIMINAR
        user_id = nuevo_user.id
        res_eliminar = self.client.get(f'/mantenedores/usuarios/eliminar/{user_id}/')
        self.assertEqual(res_eliminar.status_code, 302)
        self.assertFalse(Usuario.objects.filter(id=user_id).exists())

        # Verificar auditoría de eliminación
        log_del = HistorialAccion.objects.filter(modulo='Usuarios', accion='ELIMINAR', detalle__icontains='valeria_mesera').first()
        self.assertIsNotNone(log_del)

    # --------------------------------------------------------------------------
    # CRUD: Mesas y Auditoría
    # --------------------------------------------------------------------------
    def test_crud_mesa_y_registro_auditoria(self):
        """Prueba completa de Crear, Actualizar y Eliminar Mesa con registro en HistorialAccion."""
        self._autenticar_como(self.admin)

        # 1. CREAR
        res_crear = self.client.post('/mantenedores/mesas/guardar/', {
            'numero': 25,
            'nombre': 'Mesa Terraza VIP 25',
            'capacidad': 6,
            'estado': 'disponible'
        })
        self.assertEqual(res_crear.status_code, 302)
        mesa = Mesa.objects.filter(numero=25).first()
        self.assertIsNotNone(mesa)
        self.assertEqual(mesa.capacidad, 6)

        # Verificar auditoría de creación
        log_crear = HistorialAccion.objects.filter(modulo='Mesas', accion='CREAR', detalle__icontains='25').first()
        self.assertIsNotNone(log_crear)

        # 2. ACTUALIZAR
        res_actualizar = self.client.post('/mantenedores/mesas/guardar/', {
            'mesa_id': mesa.id,
            'numero': 25,
            'nombre': 'Mesa Terraza Modificada',
            'capacidad': 8,
            'estado': 'reservada'
        })
        self.assertEqual(res_actualizar.status_code, 302)
        mesa.refresh_from_db()
        self.assertEqual(mesa.capacidad, 8)
        self.assertEqual(mesa.estado, 'reservada')

        # Verificar auditoría de actualización
        log_act = HistorialAccion.objects.filter(modulo='Mesas', accion='ACTUALIZAR', detalle__icontains='25').first()
        self.assertIsNotNone(log_act)

        # 3. ELIMINAR
        mesa_id = mesa.id
        res_eliminar = self.client.get(f'/mantenedores/mesas/eliminar/{mesa_id}/')
        self.assertEqual(res_eliminar.status_code, 302)
        self.assertFalse(Mesa.objects.filter(id=mesa_id).exists())

        # Verificar auditoría de eliminación
        log_del = HistorialAccion.objects.filter(modulo='Mesas', accion='ELIMINAR', detalle__icontains='25').first()
        self.assertIsNotNone(log_del)

    # --------------------------------------------------------------------------
    # CRUD: Puntos de Venta y Auditoría
    # --------------------------------------------------------------------------
    def test_crud_punto_de_venta_y_registro_auditoria(self):
        """Prueba completa de Crear, Actualizar y Eliminar Punto de Venta con auditoría."""
        self._autenticar_como(self.admin)

        # 1. CREAR
        res_crear = self.client.post('/mantenedores/puntos-de-venta/guardar/', {
            'nombre': 'Caja Terraza 2',
            'ubicacion': 'Sector Norte',
            'estado': 'activo'
        })
        self.assertEqual(res_crear.status_code, 302)
        pdv = PuntoDeVenta.objects.filter(nombre='Caja Terraza 2').first()
        self.assertIsNotNone(pdv)
        self.assertEqual(pdv.ubicacion, 'Sector Norte')

        # Verificar auditoría de creación
        log_crear = HistorialAccion.objects.filter(modulo='Puntos de Venta', accion='CREAR', detalle__icontains='Caja Terraza 2').first()
        self.assertIsNotNone(log_crear)

        # 2. ACTUALIZAR
        res_actualizar = self.client.post('/mantenedores/puntos-de-venta/guardar/', {
            'pdv_id': pdv.id,
            'nombre': 'Caja Terraza 2 VIP',
            'ubicacion': 'Sector Norte Segundo Piso',
            'estado': 'inactivo'
        })
        self.assertEqual(res_actualizar.status_code, 302)
        pdv.refresh_from_db()
        self.assertEqual(pdv.nombre, 'Caja Terraza 2 VIP')
        self.assertEqual(pdv.estado, 'inactivo')

        # Verificar auditoría de actualización
        log_act = HistorialAccion.objects.filter(modulo='Puntos de Venta', accion='ACTUALIZAR', detalle__icontains='Caja Terraza 2 VIP').first()
        self.assertIsNotNone(log_act)

        # 3. ELIMINAR
        pdv_id = pdv.id
        res_eliminar = self.client.get(f'/mantenedores/puntos-de-venta/eliminar/{pdv_id}/')
        self.assertEqual(res_eliminar.status_code, 302)
        self.assertFalse(PuntoDeVenta.objects.filter(id=pdv_id).exists())

        # Verificar auditoría de eliminación
        log_del = HistorialAccion.objects.filter(modulo='Puntos de Venta', accion='ELIMINAR', detalle__icontains='Caja Terraza 2 VIP').first()
        self.assertIsNotNone(log_del)

    # --------------------------------------------------------------------------
    # CRUD: Menús y Auditoría
    # --------------------------------------------------------------------------
    def test_crud_menu_y_registro_auditoria(self):
        """Prueba completa de Crear, Actualizar y Eliminar Menú con auditoría."""
        self._autenticar_como(self.admin)

        # 1. CREAR
        res_crear = self.client.post('/mantenedores/menus/guardar/', {
            'nombre': 'Postres Artesanales',
            'descripcion': 'Tortas, helados y café',
            'estado': 'activo'
        })
        self.assertEqual(res_crear.status_code, 302)
        menu = Menu.objects.filter(nombre='Postres Artesanales').first()
        self.assertIsNotNone(menu)
        self.assertEqual(menu.estado, 'activo')

        # Verificar auditoría de creación
        log_crear = HistorialAccion.objects.filter(modulo='Menús', accion='CREAR', detalle__icontains='Postres Artesanales').first()
        self.assertIsNotNone(log_crear)

        # 2. ACTUALIZAR
        res_actualizar = self.client.post('/mantenedores/menus/guardar/', {
            'menu_id': menu.id,
            'nombre': 'Postres y Cafetería',
            'descripcion': 'Variedad de pasteles y bebidas calientes',
            'estado': 'activo'
        })
        self.assertEqual(res_actualizar.status_code, 302)
        menu.refresh_from_db()
        self.assertEqual(menu.nombre, 'Postres y Cafetería')

        # Verificar auditoría de actualización
        log_act = HistorialAccion.objects.filter(modulo='Menús', accion='ACTUALIZAR', detalle__icontains='Postres y Cafetería').first()
        self.assertIsNotNone(log_act)

        # 3. ELIMINAR
        menu_id = menu.id
        res_eliminar = self.client.get(f'/mantenedores/menus/eliminar/{menu_id}/')
        self.assertEqual(res_eliminar.status_code, 302)
        self.assertFalse(Menu.objects.filter(id=menu_id).exists())

        # Verificar auditoría de eliminación
        log_del = HistorialAccion.objects.filter(modulo='Menús', accion='ELIMINAR', detalle__icontains='Postres y Cafetería').first()
        self.assertIsNotNone(log_del)

    # --------------------------------------------------------------------------
    # CRUD: Productos y Auditoría
    # --------------------------------------------------------------------------
    def test_crud_producto_y_registro_auditoria(self):
        """Prueba completa de Crear, Actualizar y Eliminar Producto con SKU, Menú y auditoría."""
        self._autenticar_como(self.admin)

        # 1. CREAR
        res_crear = self.client.post('/mantenedores/productos/guardar/', {
            'codigo': 'POS-005',
            'nombre': 'Torta Selva Negra',
            'descripcion': 'Bizcocho de chocolate con crema y cerezas',
            'precio': '4500',
            'stock': '12',
            'menu_id': self.menu_fondos.id
        })
        self.assertEqual(res_crear.status_code, 302)
        prod = Producto.objects.filter(codigo='POS-005').first()
        self.assertIsNotNone(prod)
        self.assertEqual(prod.precio, Decimal('4500'))
        self.assertEqual(prod.stock, 12)
        self.assertEqual(prod.menu, self.menu_fondos)

        # Verificar auditoría de creación
        log_crear = HistorialAccion.objects.filter(modulo='Productos', accion='CREAR', detalle__icontains='Torta Selva Negra').first()
        self.assertIsNotNone(log_crear)

        # 2. ACTUALIZAR
        res_actualizar = self.client.post('/mantenedores/productos/guardar/', {
            'prod_id': prod.id,
            'codigo': 'POS-005',
            'nombre': 'Torta Selva Negra XL',
            'descripcion': 'Porción extra grande',
            'precio': '5200',
            'stock': '18',
            'menu_id': self.menu_fondos.id
        })
        self.assertEqual(res_actualizar.status_code, 302)
        prod.refresh_from_db()
        self.assertEqual(prod.nombre, 'Torta Selva Negra XL')
        self.assertEqual(prod.precio, Decimal('5200'))
        self.assertEqual(prod.stock, 18)

        # Verificar auditoría de actualización
        log_act = HistorialAccion.objects.filter(modulo='Productos', accion='ACTUALIZAR', detalle__icontains='Torta Selva Negra XL').first()
        self.assertIsNotNone(log_act)

        # 3. ELIMINAR
        prod_id = prod.id
        res_eliminar = self.client.get(f'/mantenedores/productos/eliminar/{prod_id}/')
        self.assertEqual(res_eliminar.status_code, 302)
        self.assertFalse(Producto.objects.filter(id=prod_id).exists())

        # Verificar auditoría de eliminación
        log_del = HistorialAccion.objects.filter(modulo='Productos', accion='ELIMINAR', detalle__icontains='Torta Selva Negra XL').first()
        self.assertIsNotNone(log_del)

    # --------------------------------------------------------------------------
    # Bitácora de Auditoría: Listado y Filtros
    # --------------------------------------------------------------------------
    def test_auditoria_listado_y_filtros(self):
        """Verifica la visualización de la bitácora de auditoría y los filtros por acción, módulo y búsqueda."""
        self._autenticar_como(self.admin)

        # Generar acciones de prueba
        HistorialAccion.objects.create(
            usuario=self.admin,
            accion='CREAR',
            modulo='Mesas',
            detalle='Creación de prueba mesa auditoría'
        )
        HistorialAccion.objects.create(
            usuario=self.admin,
            accion='ACTUALIZAR',
            modulo='Productos',
            detalle='Actualización de precio producto auditoría'
        )

        # 1. Consulta general
        res_todos = self.client.get('/mantenedores/auditoria/')
        self.assertEqual(res_todos.status_code, 200)
        self.assertTemplateUsed(res_todos, 'mantenedores/auditoria.html')
        self.assertGreaterEqual(len(res_todos.context['historial']), 2)

        # 2. Filtro por acción
        res_accion = self.client.get('/mantenedores/auditoria/?accion=CREAR')
        self.assertEqual(res_accion.status_code, 200)
        for h in res_accion.context['historial']:
            self.assertEqual(h.accion, 'CREAR')

        # 3. Filtro por módulo
        res_modulo = self.client.get('/mantenedores/auditoria/?modulo=Productos')
        self.assertEqual(res_modulo.status_code, 200)
        for h in res_modulo.context['historial']:
            self.assertEqual(h.modulo, 'Productos')

        # 4. Búsqueda por texto libre
        res_busqueda = self.client.get('/mantenedores/auditoria/?q=auditoría')
        self.assertEqual(res_busqueda.status_code, 200)
        self.assertGreaterEqual(len(res_busqueda.context['historial']), 2)

    def test_vistas_dedicadas_registrar_y_actualizar_plantillas(self):
        """Verifica que las vistas y plantillas dedicadas de registrar.html y actualizar.html funcionen con código 200."""
        self._autenticar_como(self.admin)

        # 1. Usuarios
        res_user_reg = self.client.get('/mantenedores/usuarios/registrar/')
        self.assertEqual(res_user_reg.status_code, 200)
        self.assertTemplateUsed(res_user_reg, 'mantenedores/usuarios/registrar.html')
        res_user_act = self.client.get(f'/mantenedores/usuarios/actualizar/{self.cajero.id}/')
        self.assertEqual(res_user_act.status_code, 200)
        self.assertTemplateUsed(res_user_act, 'mantenedores/usuarios/actualizar.html')
        # Verificar que el admin no puede auto-modificar su propia cuenta
        res_user_propio = self.client.get(f'/mantenedores/usuarios/actualizar/{self.admin.id}/')
        self.assertEqual(res_user_propio.status_code, 302)
        self.assertRedirects(res_user_propio, '/mantenedores/usuarios/')

        # 2. Mesas
        res_mesa_reg = self.client.get('/mantenedores/mesas/registrar/')
        self.assertEqual(res_mesa_reg.status_code, 200)
        self.assertTemplateUsed(res_mesa_reg, 'mantenedores/mesas/registrar.html')
        res_mesa_act = self.client.get(f'/mantenedores/mesas/actualizar/{self.mesa_base.id}/')
        self.assertEqual(res_mesa_act.status_code, 200)
        self.assertTemplateUsed(res_mesa_act, 'mantenedores/mesas/actualizar.html')

        # 3. Puntos de Venta
        res_pdv_reg = self.client.get('/mantenedores/puntos-de-venta/registrar/')
        self.assertEqual(res_pdv_reg.status_code, 200)
        self.assertTemplateUsed(res_pdv_reg, 'mantenedores/puntos_venta/registrar.html')
        res_pdv_act = self.client.get(f'/mantenedores/puntos-de-venta/actualizar/{self.pdv_base.id}/')
        self.assertEqual(res_pdv_act.status_code, 200)
        self.assertTemplateUsed(res_pdv_act, 'mantenedores/puntos_venta/actualizar.html')

        # 4. Menús
        res_menu_reg = self.client.get('/mantenedores/menus/registrar/')
        self.assertEqual(res_menu_reg.status_code, 200)
        self.assertTemplateUsed(res_menu_reg, 'mantenedores/menus/registrar.html')
        res_menu_act = self.client.get(f'/mantenedores/menus/actualizar/{self.menu_fondos.id}/')
        self.assertEqual(res_menu_act.status_code, 200)
        self.assertTemplateUsed(res_menu_act, 'mantenedores/menus/actualizar.html')

        # 5. Productos
        res_prod_reg = self.client.get('/mantenedores/productos/registrar/')
        self.assertEqual(res_prod_reg.status_code, 200)
        self.assertTemplateUsed(res_prod_reg, 'mantenedores/productos/registrar.html')
        res_prod_act = self.client.get(f'/mantenedores/productos/actualizar/{self.producto_base.id}/')
        self.assertEqual(res_prod_act.status_code, 200)
        self.assertTemplateUsed(res_prod_act, 'mantenedores/productos/actualizar.html')

    def test_operaciones_generan_mensajes_django_success_y_error(self):
        """Verifica que las operaciones CRUD invoquen messages.success y messages.error de Django."""
        self._autenticar_como(self.admin)

        # 1. messages.success en creación de mesa
        res_crear = self.client.post('/mantenedores/mesas/guardar/', {
            'numero': 88,
            'nombre': 'Mesa Con Mensaje',
            'capacidad': 4,
            'estado': 'disponible'
        }, follow=True)
        msgs_crear = [m.message for m in get_messages(res_crear.wsgi_request)]
        self.assertTrue(any('creada exitosamente' in m for m in msgs_crear))

        # 2. messages.error ante número de mesa duplicado
        res_error = self.client.post('/mantenedores/mesas/guardar/', {
            'numero': 88,
            'nombre': 'Mesa Duplicada',
            'capacidad': 4,
            'estado': 'disponible'
        }, follow=True)
        msgs_error = [m.message for m in get_messages(res_error.wsgi_request)]
        self.assertTrue(any('Ya existe una mesa con el número #88' in m for m in msgs_error))
class PruebasInactividadYError404TestCase(TestCase):
    """
    Pruebas unitarias para:
    1. Vencimiento de sesión por inactividad (30 minutos) configurado en settings.py.
    2. Lógica condicional en plantilla 404 (errors/404.html):
       - Usuario autenticado: oculta botón Iniciar Sesión y muestra Volver al Menú Principal según rol.
       - Usuario no autenticado: muestra únicamente botón Iniciar Sesión hacia /login/.
       - Presencia de la imagen estática error404.jpg.
    """

    def setUp(self):
        self.client = Client()
        self.admin = Usuario.objects.create(
            rut="11.111.111-1",
            nombre="Admin Test",
            correo="admin@test.cl",
            username="admin_404",
            password="pass",
            rol="administrador"
        )
        self.cajero = Usuario.objects.create(
            rut="22.222.222-2",
            nombre="Cajero Test",
            correo="cajero@test.cl",
            username="cajero_404",
            password="pass",
            rol="cajero"
        )
        self.mesero = Usuario.objects.create(
            rut="33.333.333-3",
            nombre="Mesero Test",
            correo="mesero@test.cl",
            username="mesero_404",
            password="pass",
            rol="mesero"
        )
        self.cocinero = Usuario.objects.create(
            rut="44.444.444-4",
            nombre="Cocinero Test",
            correo="cocinero@test.cl",
            username="cocinero_404",
            password="pass",
            rol="cocinero"
        )

    def _autenticar_como(self, usuario):
        session = self.client.session
        session['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'username': usuario.username,
            'rol': usuario.rol,
        }
        session.save()

    def test_configuracion_inactividad_sesion_en_settings(self):
        """Verifica que settings.py configure 30 minutos de inactividad, reinicio en cada request y cierre con navegador."""
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1800, "SESSION_COOKIE_AGE debe ser 1800 segundos (30 minutos).")
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST, "SESSION_SAVE_EVERY_REQUEST debe ser True.")
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE, "SESSION_EXPIRE_AT_BROWSER_CLOSE debe ser True.")

    def test_404_usuario_no_autenticado_muestra_solo_iniciar_sesion(self):
        """Verifica que un usuario anónimo en 404 vea únicamente 'Iniciar Sesión' y la imagen 404."""
        res = self.client.get('/ruta-inexistente-anonimo/')
        self.assertEqual(res.status_code, 404)
        self.assertTemplateUsed(res, 'errors/404.html')

        # Debe mostrar botón Iniciar Sesión hacia /login/
        self.assertContains(res, 'Iniciar Sesión', status_code=404)
        self.assertContains(res, 'href="/login/"', status_code=404)

        # No debe mostrar Volver al Menú Principal
        self.assertNotContains(res, 'Volver al Menú Principal', status_code=404)

        # Debe contener la imagen del error 404
        self.assertContains(res, 'error404.jpg', status_code=404)

    def test_404_usuario_administrador_muestra_volver_al_menu_principal(self):
        """Verifica que el Administrador vea 'Volver al Menú Principal' hacia /administrador/ y no 'Iniciar Sesión'."""
        self._autenticar_como(self.admin)
        res = self.client.get('/ruta-inexistente-admin/')
        self.assertEqual(res.status_code, 404)

        # Debe mostrar Volver al Menú Principal dirigido a /administrador/
        self.assertContains(res, 'Volver al Menú Principal', status_code=404)
        self.assertContains(res, 'href="/administrador/"', status_code=404)

        # Debe ocultar por completo Iniciar Sesión
        self.assertNotContains(res, 'Iniciar Sesión', status_code=404)

    def test_404_usuario_cajero_muestra_volver_a_cajero(self):
        """Verifica que el Cajero vea 'Volver al Menú Principal' hacia /cajero/ y no 'Iniciar Sesión'."""
        self._autenticar_como(self.cajero)
        res = self.client.get('/ruta-inexistente-cajero/')
        self.assertEqual(res.status_code, 404)

        self.assertContains(res, 'Volver al Menú Principal', status_code=404)
        self.assertContains(res, 'href="/cajero/"', status_code=404)
        self.assertNotContains(res, 'Iniciar Sesión', status_code=404)

    def test_404_usuario_mesero_y_cocinero_muestra_sus_respectivas_rutas(self):
        """Verifica que Mesero y Cocinero sean redirigidos a /mesero/ y /cocinero/ respectivamente en 404."""
        # Mesero
        self._autenticar_como(self.mesero)
        res_mesero = self.client.get('/ruta-inexistente-mesero/')
        self.assertEqual(res_mesero.status_code, 404)
        self.assertContains(res_mesero, 'Volver al Menú Principal', status_code=404)
        self.assertContains(res_mesero, 'href="/mesero/"', status_code=404)
        self.assertNotContains(res_mesero, 'Iniciar Sesión', status_code=404)

        # Cocinero
        self._autenticar_como(self.cocinero)
        res_cocinero = self.client.get('/ruta-inexistente-cocinero/')
        self.assertEqual(res_cocinero.status_code, 404)
        self.assertContains(res_cocinero, 'Volver al Menú Principal', status_code=404)
        self.assertContains(res_cocinero, 'href="/cocinero/"', status_code=404)
        self.assertNotContains(res_cocinero, 'Iniciar Sesión', status_code=404)
# ==============================================================================
# SUITE DE PRUEBAS: CAPA DE VALIDACIÓN FRONTEND / BACKEND PARA PRODUCTOS
# ==============================================================================

class PruebasValidacionesProductoFrontendBackendTestCase(TestCase):
    """
    Verifica las reglas de validación en tiempo real y submit para Productos:
    - Longitud y bloqueo de espacios en blanco.
    - Bloqueo de caracteres especiales peligrosos (<, >, ", ', ;, --) para XSS e inyecciones.
    - Rechazo de números negativos, puntos (.), comas (,) y secuencias mal formateadas en Precio y Stock.
    - Inclusión del archivo JavaScript de validación en las plantillas correspondientes.
    """

    def setUp(self):
        self.client = Client()
        self.admin = Usuario.objects.create(
            rut="1-9",
            nombre="Admin Test",
            correo="admin.val@safari.cl",
            username="admin_val",
            password="admin123",
            rol="administrador",
            estado="activo"
        )
        self.menu_fondos = Menu.objects.create(
            nombre="Platos Fuertes",
            descripcion="Platos de fondo",
            estado="activo"
        )

    def _autenticar_admin(self):
        session = self.client.session
        session['usuario'] = {
            'id': self.admin.id,
            'nombre': self.admin.nombre,
            'rol': self.admin.rol,
            'username': self.admin.username,
        }
        session.save()

    def test_templates_incluyen_script_validaciones_producto(self):
        """Verifica que las plantillas de Producto vinculen el script validaciones_producto.js."""
        self._autenticar_admin()
        
        # 1. Pantalla de creación de producto
        res_crear = self.client.get('/mantenedores/productos/registrar/')
        self.assertEqual(res_crear.status_code, 200)
        self.assertContains(res_crear, 'validaciones_producto.js')

        # 2. Pantalla principal de mantenedor de productos
        res_lista = self.client.get('/mantenedores/productos/')
        self.assertEqual(res_lista.status_code, 200)
        self.assertContains(res_lista, 'validaciones_producto.js')

        # 3. Pantalla de inventario y stock
        res_stock = self.client.get('/stock/')
        self.assertEqual(res_stock.status_code, 200)
        self.assertContains(res_stock, 'validaciones_producto.js')

    def test_rechazo_caracteres_prohibidos_xss_inyeccion_en_nombre(self):
        """Rechaza caracteres prohibidos (<, >, \", ', ;, --) en el nombre del producto."""
        self._autenticar_admin()
        payloads_inseguros = [
            '<script>alert("xss")</script>',
            'Hamburguesa <Especial>',
            'Plato "Safari"',
            "Churrasco'; DROP TABLE productos;--",
            'Bebida -- comentario sql',
            'Postre; SELECT 1',
        ]
        for payload in payloads_inseguros:
            res = self.client.post('/mantenedores/productos/guardar/', {
                'codigo': 'SKU-SEC',
                'nombre': payload,
                'descripcion': 'Descripción normal',
                'precio': '7500',
                'stock': '15',
                'menu_id': str(self.menu_fondos.id)
            })
            self.assertEqual(res.status_code, 400, f"Se esperaba error 400 para payload: {payload}")
            self.assertTemplateUsed(res, 'errors/400.html')

    def test_rechazo_caracteres_prohibidos_en_descripcion_y_codigo(self):
        """Rechaza caracteres prohibidos en descripción o código SKU."""
        self._autenticar_admin()

        # En descripción
        res_desc = self.client.post('/mantenedores/productos/guardar/', {
            'codigo': 'SKU-001',
            'nombre': 'Lomo Saltado',
            'descripcion': '<img src=x onerror=alert(1)>',
            'precio': '8900',
            'stock': '10',
            'menu_id': str(self.menu_fondos.id)
        })
        self.assertEqual(res_desc.status_code, 400)

        # En código SKU
        res_sku = self.client.post('/mantenedores/productos/guardar/', {
            'codigo': "SKU'--",
            'nombre': 'Lomo Saltado',
            'descripcion': 'Carne con papas fritas',
            'precio': '8900',
            'stock': '10',
            'menu_id': str(self.menu_fondos.id)
        })
        self.assertEqual(res_sku.status_code, 400)

    def test_rechazo_precio_y_stock_negativos_o_decimales(self):
        """Rechaza explícitamente el signo menos (-), puntos (.), comas (,) y secuencias mal formateadas."""
        self._autenticar_admin()

        casos_precio_invalido = ['-5000', '5000.50', '5000,00', '5000..0', '5000.-', '0']
        for p_invalido in casos_precio_invalido:
            res = self.client.post('/mantenedores/productos/guardar/', {
                'codigo': 'SKU-NUM',
                'nombre': 'Producto Test Número',
                'descripcion': 'Validación numérica',
                'precio': p_invalido,
                'stock': '10',
                'menu_id': str(self.menu_fondos.id)
            })
            self.assertEqual(res.status_code, 400, f"Se esperaba 400 para precio inválido: {p_invalido}")

        casos_stock_invalido = ['-1', '10.5', '10,0', '10..2', '10.-']
        for s_invalido in casos_stock_invalido:
            res = self.client.post('/mantenedores/productos/guardar/', {
                'codigo': 'SKU-NUM',
                'nombre': 'Producto Test Stock',
                'descripcion': 'Validación de stock',
                'precio': '5000',
                'stock': s_invalido,
                'menu_id': str(self.menu_fondos.id)
            })
            self.assertEqual(res.status_code, 400, f"Se esperaba 400 para stock inválido: {s_invalido}")

    def test_creacion_y_actualizacion_exitosa_con_datos_validos(self):
        """Crea y actualiza satisfactoriamente un producto que cumple todas las reglas estrictas."""
        self._autenticar_admin()

        # Creación válida
        res_crear = self.client.post('/mantenedores/productos/guardar/', {
            'codigo': 'HAM-099',
            'nombre': 'Hamburguesa Safari Premium',
            'descripcion': 'Doble carne, queso cheddar y papas',
            'precio': '7990',
            'stock': '25',
            'menu_id': str(self.menu_fondos.id)
        })
        self.assertRedirects(res_crear, '/mantenedores/productos/')

        prod = Producto.objects.filter(codigo='HAM-099').first()
        self.assertIsNotNone(prod)
        self.assertEqual(prod.nombre, 'Hamburguesa Safari Premium')
        self.assertEqual(prod.precio, 7990)
        self.assertEqual(prod.stock, 25)

        # Actualización válida
        res_act = self.client.post('/mantenedores/productos/guardar/', {
            'prod_id': str(prod.id),
            'codigo': 'HAM-099-XL',
            'nombre': 'Hamburguesa Safari Premium XL',
            'descripcion': 'Triple carne con tocino',
            'precio': '9490',
            'stock': '30',
            'menu_id': str(self.menu_fondos.id)
        })
        self.assertRedirects(res_act, '/mantenedores/productos/')

        prod.refresh_from_db()
        self.assertEqual(prod.codigo, 'HAM-099-XL')
        self.assertEqual(prod.nombre, 'Hamburguesa Safari Premium XL')
        self.assertEqual(prod.precio, 9490)
        self.assertEqual(prod.stock, 30)
# ==============================================================================
# SUITE DE PRUEBAS: VALIDACIÓN BACKEND ROBUSTA Y BLINDAJE CONTRA INYECCIÓN SQL
# ==============================================================================

class PruebasValidacionBackendYBlindajeSQLTestCase(TestCase):
    """
    Verifica las protecciones backend en Safari/views.py:
    - Validación y rechazo temprano de parámetros GET maliciosos (', ", ;, --, /*).
    - Limpieza de parámetros con .strip() y descarte antes de ejecutar consultas a la BD.
    - Validación segura de formatos específicos (IDs numéricos, fechas AAAA-MM-DD).
    - Sanitización y verificación de Producto (descarte de cadenas vacías/espacios, control de longitud).
    - Validación numérica estricta en precio y stock (bloqueo de letras, signos negativos, decimales).
    - Garantía de consultas parametrizadas exclusivas con el ORM de Django.
    """

    def setUp(self):
        self.client = Client()
        self.admin = Usuario.objects.create(
            rut="1-9",
            nombre="Admin Backend",
            correo="admin.backend@safari.cl",
            username="admin_backend",
            password="adminpassword123",
            rol="administrador",
            estado="activo"
        )
        self.menu_fondos = Menu.objects.create(
            nombre="Fondos Gourmet",
            descripcion="Platos principales",
            estado="activo"
        )
        self.producto_demo = Producto.objects.create(
            codigo="SKU-DEMO",
            nombre="Costillar al Horno",
            descripcion="Costillar con papas rústicas",
            precio=12500,
            stock=15,
            menu=self.menu_fondos
        )

    def _autenticar_admin(self):
        session = self.client.session
        session['usuario'] = {
            'id': self.admin.id,
            'nombre': self.admin.nombre,
            'rol': self.admin.rol,
            'username': self.admin.username,
        }
        session.save()

    def test_rechazo_inyeccion_sql_parametros_get_auditoria(self):
        """Rechaza de inmediato solicitudes GET en auditoría si contienen caracteres de inyección SQL."""
        self._autenticar_admin()

        payloads_inyeccion = [
            "/mantenedores/auditoria/?q=' OR '1'='1",
            "/mantenedores/auditoria/?accion=CREAR; DROP TABLE usuarios;--",
            "/mantenedores/auditoria/?modulo=/*comentario*/",
            "/mantenedores/auditoria/?usuario_id=1'--",
            "/mantenedores/auditoria/?q=\" OR \"\"=\"",
        ]
        for url in payloads_inyeccion:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 400, f"Se esperaba código 400 para querystring maliciosa: {url}")
            self.assertTemplateUsed(res, 'errors/400.html')

    def test_rechazo_formatos_invalidos_get_auditoria(self):
        """Rechaza solicitudes con parámetros GET que no cumplan el formato esperado antes de consultar BD."""
        self._autenticar_admin()

        # ID de usuario no numérico
        res_usr = self.client.get('/mantenedores/auditoria/?usuario_id=abc_invalido')
        self.assertEqual(res_usr.status_code, 400)
        self.assertTemplateUsed(res_usr, 'errors/400.html')

        # Formato de fecha desde incorrecto (no es AAAA-MM-DD)
        res_fdesde = self.client.get('/mantenedores/auditoria/?fecha_desde=01-10-2026')
        self.assertEqual(res_fdesde.status_code, 400)

        # Formato de fecha hasta incorrecto
        res_fhasta = self.client.get('/mantenedores/auditoria/?fecha_hasta=2026/10/31')
        self.assertEqual(res_fhasta.status_code, 400)

    def test_rechazo_inyeccion_sql_get_stock_ventas_y_productos(self):
        """Rechaza querystrings con inyección SQL en stock, ventas y mantenedor de productos."""
        self._autenticar_admin()

        # Stock GET
        res_stock = self.client.get("/stock/?q=' OR 1=1--")
        self.assertEqual(res_stock.status_code, 400)

        # Ventas GET
        res_ventas = self.client.get("/ventas/?fecha=2026-10-01; DROP TABLE ventas;--")
        self.assertEqual(res_ventas.status_code, 400)

        # Mantenedor Productos GET
        res_prod = self.client.get("/mantenedores/productos/?menu_id=1' OR '1'='1")
        self.assertEqual(res_prod.status_code, 400)

    def test_busqueda_get_segura_aplica_strip_y_orm_parametrizado(self):
        """Valida que parámetros GET legítimos sean limpiados con .strip() y procesados con ORM."""
        self._autenticar_admin()

        # Búsqueda en stock con espacios laterales
        res_stock = self.client.get("/stock/?q=%20%20Costillar%20%20")
        self.assertEqual(res_stock.status_code, 200)
        self.assertContains(res_stock, "Costillar al Horno")

        # Búsqueda en mantenedor productos con espacios
        res_prod = self.client.get("/mantenedores/productos/?q=%20%20SKU-DEMO%20%20")
        self.assertEqual(res_prod.status_code, 200)
        self.assertContains(res_prod, "SKU-DEMO")

    def test_backend_rechazo_producto_nombre_solo_espacios_o_vacio(self):
        """Rechaza nombres vacíos o formados exclusivamente por espacios en blanco."""
        self._autenticar_admin()

        casos_vacios = ["", "   ", "\t   \n"]
        for nombre_invalido in casos_vacios:
            res = self.client.post('/mantenedores/productos/guardar/', {
                'codigo': 'SKU-TEST',
                'nombre': nombre_invalido,
                'descripcion': 'Plato válido',
                'precio': '8500',
                'stock': '10',
                'menu_id': str(self.menu_fondos.id)
            })
            self.assertEqual(res.status_code, 400)
            self.assertTemplateUsed(res, 'errors/400.html')

    def test_backend_rechazo_producto_precio_y_stock_con_letras_y_simbolos(self):
        """Rechaza precios y stock si contienen letras, símbolos prohibidos o números negativos."""
        self._autenticar_admin()

        # Precios con letras o símbolos
        precios_invalidos = ["cincomil", "5000$", "5.000", "5,000", "-5000", "5000-", "5e3"]
        for p_inv in precios_invalidos:
            res = self.client.post('/mantenedores/productos/guardar/', {
                'codigo': 'SKU-P',
                'nombre': 'Plato Precio Test',
                'descripcion': 'Descripción',
                'precio': p_inv,
                'stock': '10',
                'menu_id': str(self.menu_fondos.id)
            })
            self.assertEqual(res.status_code, 400, f"Se esperaba 400 para precio: {p_inv}")

        # Stock con letras o símbolos
        stock_invalidos = ["diez", "10unidades", "10.0", "10,5", "-10", "10+"]
        for s_inv in stock_invalidos:
            res = self.client.post('/mantenedores/productos/guardar/', {
                'codigo': 'SKU-S',
                'nombre': 'Plato Stock Test',
                'descripcion': 'Descripción',
                'precio': '6000',
                'stock': s_inv,
                'menu_id': str(self.menu_fondos.id)
            })
            self.assertEqual(res.status_code, 400, f"Se esperaba 400 para stock: {s_inv}")

    def test_backend_rechazo_producto_con_ids_manipulados_por_post(self):
        """Rechaza prod_id o menu_id si se intentan manipular con caracteres de inyección."""
        self._autenticar_admin()

        res_prod_id = self.client.post('/mantenedores/productos/guardar/', {
            'prod_id': "1' OR '1'='1",
            'codigo': 'SKU-ID',
            'nombre': 'Plato ID Malicioso',
            'descripcion': 'Descripción',
            'precio': '7000',
            'stock': '10',
        })
        self.assertEqual(res_prod_id.status_code, 400)

        res_menu_id = self.client.post('/mantenedores/productos/guardar/', {
            'menu_id': "1; DROP TABLE menu;--",
            'codigo': 'SKU-ID2',
            'nombre': 'Plato Menu Malicioso',
            'descripcion': 'Descripción',
            'precio': '7000',
            'stock': '10',
        })
        self.assertEqual(res_menu_id.status_code, 400)
# ==============================================================================
# SUITE DE PRUEBAS: ERRORES UNIFICADOS 401, 403, 404 Y SEGURIDAD CONTRA DEVTOOLS GET
# ==============================================================================

class PruebasErroresUnificadosYSeguridadFormulariosTestCase(TestCase):
    """
    Suite de pruebas unitarias para:
    1. Unificación de los errores 401, 403 y 404:
       - Rol autenticado (Administrador, Cajero, Mesero, Cocinero) muestra "Volver al Menú Principal"
         con destino dinámico a su respectivo panel (/administrador/, /cajero/, /mesero/, /cocinero/).
       - Botón "Cambiar Cuenta" presente en 401, 403 y 404 (/logout/ con sesión, /login/ anónimo).
       - Ocultamiento de redirección al menú principal para usuarios no autenticados.
    2. Blindaje contra manipulación por DevTools (cambio de method POST a GET):
       - Rechazo y redirección inmediata en formularios de login, stock y los 5 mantenedores.
       - Prevención de exposición de credenciales y campos en la URL querystring.
       - Verificación de no persistencia en base de datos.
    """

    def setUp(self):
        self.client = Client()
        self.admin = Usuario.objects.create(
            rut="11.111.111-1",
            nombre="Admin Test",
            correo="admin@safari.cl",
            username="admin_unif",
            password="adminpassword123",
            rol="administrador",
            estado="activo"
        )
        self.cajero = Usuario.objects.create(
            rut="22.222.222-2",
            nombre="Cajero Test",
            correo="cajero@safari.cl",
            username="cajero_unif",
            password="cajeropassword123",
            rol="cajero",
            estado="activo"
        )
        self.mesero = Usuario.objects.create(
            rut="33.333.333-3",
            nombre="Mesero Test",
            correo="mesero@safari.cl",
            username="mesero_unif",
            password="meseropassword123",
            rol="mesero",
            estado="activo"
        )
        self.cocinero = Usuario.objects.create(
            rut="44.444.444-4",
            nombre="Cocinero Test",
            correo="cocinero@safari.cl",
            username="cocinero_unif",
            password="cocineropassword123",
            rol="cocinero",
            estado="activo"
        )

    def _autenticar_como(self, usuario):
        session = self.client.session
        session['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'username': usuario.username,
            'rol': usuario.rol,
        }
        session.save()

    def test_error_401_usuario_autenticado_administrador(self):
        """Error 401 con usuario administrador autenticado muestra 'Volver al Menú Principal' a /administrador/ y 'Cambiar Cuenta'."""
        self._autenticar_como(self.admin)
        res = self.client.get('/error/401/')
        self.assertEqual(res.status_code, 401)
        self.assertContains(res, 'Volver al Menú Principal', status_code=401)
        self.assertContains(res, 'href="/administrador/"', status_code=401)
        self.assertContains(res, 'Cambiar Cuenta', status_code=401)
        self.assertContains(res, 'href="/logout/"', status_code=401)

    def test_error_401_usuario_autenticado_cajero(self):
        """Error 401 con cajero autenticado muestra 'Volver al Menú Principal' a /cajero/ y 'Cambiar Cuenta'."""
        self._autenticar_como(self.cajero)
        res = self.client.get('/error/401/')
        self.assertEqual(res.status_code, 401)
        self.assertContains(res, 'Volver al Menú Principal', status_code=401)
        self.assertContains(res, 'href="/cajero/"', status_code=401)
        self.assertContains(res, 'Cambiar Cuenta', status_code=401)
        self.assertContains(res, 'href="/logout/"', status_code=401)

    def test_error_401_usuario_anonimo(self):
        """Error 401 sin sesión no muestra 'Volver al Menú Principal' y muestra 'Cambiar Cuenta' hacia /login/."""
        res = self.client.get('/error/401/')
        self.assertEqual(res.status_code, 401)
        self.assertNotContains(res, 'Volver al Menú Principal', status_code=401)
        self.assertContains(res, 'Cambiar Cuenta', status_code=401)
        self.assertContains(res, 'href="/login/"', status_code=401)

    def test_error_403_usuario_autenticado_mesero(self):
        """Error 403 con mesero autenticado muestra 'Volver al Menú Principal' a /mesero/ y 'Cambiar Cuenta'."""
        self._autenticar_como(self.mesero)
        res = self.client.get('/administrador/')  # Mesero intentando entrar a admin
        self.assertEqual(res.status_code, 403)
        self.assertContains(res, 'Volver al Menú Principal', status_code=403)
        self.assertContains(res, 'href="/mesero/"', status_code=403)
        self.assertContains(res, 'Cambiar Cuenta', status_code=403)
        self.assertContains(res, 'href="/logout/"', status_code=403)

    def test_error_403_usuario_autenticado_cocinero(self):
        """Error 403 con cocinero autenticado muestra 'Volver al Menú Principal' a /cocinero/ y 'Cambiar Cuenta'."""
        self._autenticar_como(self.cocinero)
        res = self.client.get('/error/403/')
        self.assertEqual(res.status_code, 403)
        self.assertContains(res, 'Volver al Menú Principal', status_code=403)
        self.assertContains(res, 'href="/cocinero/"', status_code=403)
        self.assertContains(res, 'Cambiar Cuenta', status_code=403)
        self.assertContains(res, 'href="/logout/"', status_code=403)

    def test_error_403_usuario_anonimo(self):
        """Error 403 sin sesión no muestra 'Volver al Menú Principal' y muestra 'Cambiar Cuenta' hacia /login/."""
        res = self.client.get('/error/403/')
        self.assertEqual(res.status_code, 403)
        self.assertNotContains(res, 'Volver al Menú Principal', status_code=403)
        self.assertContains(res, 'Cambiar Cuenta', status_code=403)
        self.assertContains(res, 'href="/login/"', status_code=403)

    def test_error_404_usuario_autenticado_muestra_cambiar_cuenta(self):
        """Error 404 con usuario autenticado muestra tanto 'Volver al Menú Principal' como 'Cambiar Cuenta'."""
        self._autenticar_como(self.admin)
        res = self.client.get('/ruta-inexistente-404-test/')
        self.assertEqual(res.status_code, 404)
        self.assertContains(res, 'Volver al Menú Principal', status_code=404)
        self.assertContains(res, 'Cambiar Cuenta', status_code=404)
        self.assertContains(res, 'href="/logout/"', status_code=404)

    def test_bloqueo_manipulacion_devtools_login_get(self):
        """Envío del formulario de Login por GET (manipulación de DevTools) debe ser bloqueado y redirigido a /login/ limpio."""
        res = self.client.get('/login/?username=admin_unif&password=adminpassword123', follow=True)
        # Debe redirigir y no haber iniciado sesión
        self.assertNotIn('usuario', self.client.session)
        self.assertEqual(res.status_code, 200)

    def test_bloqueo_manipulacion_devtools_producto_stock_get(self):
        """Envío del formulario de producto (/stock/guardar/) por GET debe ser rechazado y redirigido sin insertar registro."""
        self._autenticar_como(self.admin)
        conteo_previo = Producto.objects.filter(nombre='Producto Manipulado GET').count()

        res = self.client.get('/stock/guardar/?nombre=Producto+Manipulado+GET&precio=9990&stock=5', follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertRedirects(res, '/stock/')
        self.assertEqual(Producto.objects.filter(nombre='Producto Manipulado GET').count(), conteo_previo)

    def test_bloqueo_manipulacion_devtools_mantenedor_producto_get(self):
        """Envío de mantenedor de producto por GET debe ser rechazado y redirigido a /mantenedores/productos/."""
        self._autenticar_como(self.admin)
        conteo_previo = Producto.objects.filter(nombre='Producto Mantenedor GET').count()

        res = self.client.get('/mantenedores/productos/guardar/?nombre=Producto+Mantenedor+GET&precio=5000&stock=10', follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertRedirects(res, '/mantenedores/productos/')
        self.assertEqual(Producto.objects.filter(nombre='Producto Mantenedor GET').count(), conteo_previo)

    def test_bloqueo_manipulacion_devtools_mantenedor_usuario_get(self):
        """Envío de mantenedor de usuario por GET debe ser rechazado y redirigido a /mantenedores/usuarios/."""
        self._autenticar_como(self.admin)
        conteo_previo = Usuario.objects.filter(username='hack_user').count()

        res = self.client.get('/mantenedores/usuarios/guardar/?username=hack_user&password=123&nombre=Hack', follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertRedirects(res, '/mantenedores/usuarios/')
        self.assertEqual(Usuario.objects.filter(username='hack_user').count(), conteo_previo)

    def test_bloqueo_manipulacion_devtools_mantenedor_mesa_get(self):
        """Envío de mantenedor de mesa por GET debe ser rechazado y redirigido a /mantenedores/mesas/."""
        self._autenticar_como(self.admin)
        conteo_previo = Mesa.objects.filter(nombre='Mesa Hack GET').count()

        res = self.client.get('/mantenedores/mesas/guardar/?nombre=Mesa+Hack+GET&numero=99&capacidad=4', follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertRedirects(res, '/mantenedores/mesas/')
        self.assertEqual(Mesa.objects.filter(nombre='Mesa Hack GET').count(), conteo_previo)

    def test_bloqueo_manipulacion_devtools_mantenedor_punto_venta_get(self):
        """Envío de mantenedor de punto de venta por GET debe ser rechazado y redirigido a /mantenedores/puntos-de-venta/."""
        self._autenticar_como(self.admin)
        conteo_previo = PuntoDeVenta.objects.filter(nombre='PDV Hack GET').count()

        res = self.client.get('/mantenedores/puntos-de-venta/guardar/?nombre=PDV+Hack+GET&ubicacion=Zona+1', follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertRedirects(res, '/mantenedores/puntos-de-venta/')
        self.assertEqual(PuntoDeVenta.objects.filter(nombre='PDV Hack GET').count(), conteo_previo)

    def test_bloqueo_manipulacion_devtools_mantenedor_menu_get(self):
        """Envío de mantenedor de menú por GET debe ser rechazado y redirigido a /mantenedores/menus/."""
        self._autenticar_como(self.admin)
        conteo_previo = Menu.objects.filter(nombre='Menu Hack GET').count()

        res = self.client.get('/mantenedores/menus/guardar/?nombre=Menu+Hack+GET&descripcion=Prueba', follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertRedirects(res, '/mantenedores/menus/')
        self.assertEqual(Menu.objects.filter(nombre='Menu Hack GET').count(), conteo_previo)
# ==============================================================================
# SUITE DE PRUEBAS: BLOQUEO ESTRICTO DE CARACTERES ESPECIALES EN CAMPOS
# ==============================================================================

class PruebasBloqueoCaracteresEspecialesCamposEscrituraTestCase(TestCase):
    """
    Verifica la eliminación y rechazo estricto de caracteres especiales (<, >, ", ', ;, $, --, /*)
    en todos los campos de escritura del sistema (Login, Mantenedores, Stock, Modales).
    """

    def setUp(self):
        self.client = Client()
        self.admin = Usuario.objects.create(
            rut="11.111.111-1",
            nombre="Admin General",
            correo="admin@safari.cl",
            username="admin_seguro",
            password="adminpassword123",
            rol="administrador",
            estado="activo"
        )
        self.cajero = Usuario.objects.create(
            rut="22.222.222-2",
            nombre="Cajero Central",
            correo="cajero@safari.cl",
            username="cajero_seguro",
            password="cajeropassword123",
            rol="cajero",
            estado="activo"
        )

    def _autenticar_admin(self):
        session = self.client.session
        session['usuario'] = {
            'id': self.admin.id,
            'nombre': self.admin.nombre,
            'username': self.admin.username,
            'rol': self.admin.rol,
        }
        session.save()

    def test_login_rechaza_caracteres_especiales_en_password(self):
        """Verifica que el login rechace contraseñas con caracteres especiales peligrosos (<, >, ', ", ;, $, --)."""
        passwords_maliciosas = [
            "<script>alert(1)</script>",
            "password' OR '1'='1",
            "password;--",
            "clave$secreta",
            'admin" OR ""="',
            "pass/*comentario*/word",
        ]
        for p_mal in passwords_maliciosas:
            res = self.client.post('/login/', {'username': 'admin_seguro', 'password': p_mal})
            self.assertEqual(res.status_code, 200)
            self.assertTemplateUsed(res, 'login.html')
            self.assertContains(res, 'caracteres especiales no permitidos')
            self.assertNotIn('usuario', self.client.session)

    def test_login_rechaza_caracteres_especiales_en_username(self):
        """Verifica que el login rechace usuarios con caracteres especiales."""
        usuarios_maliciosos = [
            "admin<script>",
            "user';--",
            "admin$root",
            'cajero" OR 1=1'
        ]
        for u_mal in usuarios_maliciosos:
            res = self.client.post('/login/', {'username': u_mal, 'password': 'password123'})
            self.assertEqual(res.status_code, 200)
            self.assertContains(res, 'caracteres')
            self.assertNotIn('usuario', self.client.session)

    def test_admin_guardar_usuario_rechaza_caracteres_especiales(self):
        """admin_guardar_usuario rechaza caracteres especiales en nombre, correo, usuario o password con HTTP 400."""
        self._autenticar_admin()

        # Nombre con caracteres especiales
        res = self.client.post('/administrador/guardar-usuario/', {
            'nombre': 'Juan <script>alert(1)</script>',
            'correo': 'juan@safari.cl',
            'username': 'juanp',
            'password': 'password123',
            'rol': 'cajero'
        })
        self.assertEqual(res.status_code, 400)

        # Password con caracteres especiales
        res_pass = self.client.post('/administrador/guardar-usuario/', {
            'nombre': 'Juan Perez',
            'correo': 'juan@safari.cl',
            'username': 'juanp',
            'password': 'pass; DROP TABLE usuario;--',
            'rol': 'cajero'
        })
        self.assertEqual(res_pass.status_code, 400)

    def test_mantenedor_usuario_rechaza_caracteres_especiales_en_password_y_correo(self):
        """mantenedor_usuario_guardar rechaza caracteres especiales en correo y password con HTTP 400."""
        self._autenticar_admin()

        res_correo = self.client.post('/mantenedores/usuarios/guardar/', {
            'nombre': 'Pedro Soto',
            'correo': 'pedro<script>@safari.cl',
            'username': 'pedrosoto',
            'password': 'password123',
            'rol': 'mesero'
        })
        self.assertEqual(res_correo.status_code, 400)

        res_pass = self.client.post('/mantenedores/usuarios/guardar/', {
            'nombre': 'Pedro Soto',
            'correo': 'pedro@safari.cl',
            'username': 'pedrosoto',
            'password': 'pass<script>',
            'rol': 'mesero'
        })
        self.assertEqual(res_pass.status_code, 400)

    def test_mantenedor_mesa_rechaza_caracteres_especiales(self):
        """mantenedor_mesa_guardar rechaza caracteres especiales en nombre de mesa con HTTP 400."""
        self._autenticar_admin()

        res = self.client.post('/mantenedores/mesas/guardar/', {
            'nombre': 'Mesa 1 <script>',
            'numero': '1',
            'capacidad': '4'
        })
        self.assertEqual(res.status_code, 400)

    def test_mantenedor_punto_venta_rechaza_caracteres_especiales(self):
        """mantenedor_punto_venta_guardar rechaza caracteres especiales en nombre o ubicación con HTTP 400."""
        self._autenticar_admin()

        res = self.client.post('/mantenedores/puntos-de-venta/guardar/', {
            'nombre': 'Caja 1;--',
            'ubicacion': 'Terraza'
        })
        self.assertEqual(res.status_code, 400)

    def test_mantenedor_menu_rechaza_caracteres_especiales(self):
        """mantenedor_menu_guardar rechaza caracteres especiales en nombre o descripción con HTTP 400."""
        self._autenticar_admin()

        res = self.client.post('/mantenedores/menus/guardar/', {
            'nombre': 'Platos <Fuertes>',
            'descripcion': 'Descripción normal'
        })
        self.assertEqual(res.status_code, 400)

    def test_script_seguridad_formularios_incluido_en_todas_las_paginas(self):
        """Verifica que el script seguridad_formularios.js se cargue en login, administrador, cajero y stock."""
        # Login
        res_login = self.client.get('/login/')
        self.assertContains(res_login, 'seguridad_formularios.js')

        # Administrador
        self._autenticar_admin()
        res_admin = self.client.get('/administrador/')
        self.assertContains(res_admin, 'seguridad_formularios.js')

        # Cajero
        res_cajero = self.client.get('/cajero/')
        self.assertContains(res_cajero, 'seguridad_formularios.js')

        # Stock
        res_stock = self.client.get('/stock/')
        self.assertContains(res_stock, 'seguridad_formularios.js')
class FlujoVentasDobleModalidadTestCase(TestCase):
    """
    Pruebas unitarias para el nuevo flujo operativo de ventas en doble modalidad:
    1. Venta en Barra (Inmediata):
       - Cajero selecciona productos, añade notas de comanda y método de pago.
       - Descuenta stock de inmediato.
       - Genera correlativo de boleta oficial (BOL-XXXX) al instante.
       - Envía comanda automática a cocina en estado de preparación (marcada como pagada).

    2. Toma de Pedido de Garzón / Mesero:
       - Mesero selecciona mesa física (la mesa pasa inmediatamente a estado 'ocupada').
       - Carga productos con notas de comanda para cocina.
       - Genera comanda hacia cocina en estado 'en_espera' (folio COM-XXXX).
       - NO emite boleta (Venta no creada) ni descuenta stock en este momento.

    3. Liquidación de Mesa en Terminal de Caja:
       - El cliente solicita la cuenta y el cajero liquida la mesa en su terminal.
       - Valida que la caja esté ABIERTA.
       - Descuenta stock en este momento.
       - Emite boleta correlativa oficial (BOL-XXXX) vinculada a la caja abierta.
       - Marca la comanda como pagada y desocupa la mesa física ('desocupada').
    """

    def setUp(self):
        self.client = Client()
        self.cajero = Usuario.objects.create(
            nombre="Sofía Cajera",
            correo="sofia@safari.cl",
            username="sofiacaja",
            password="password123",
            rol="cajero"
        )
        self.mesero = Usuario.objects.create(
            nombre="Martín Garzón",
            correo="martin@safari.cl",
            username="martingarzon",
            password="password123",
            rol="mesero"
        )
        self.cocinero = Usuario.objects.create(
            nombre="Hugo Chef",
            correo="hugo@safari.cl",
            username="hugochef",
            password="password123",
            rol="cocinero"
        )
        self.prod_hamburguesa = Producto.objects.create(
            nombre="Hamburguesa Austral",
            descripcion="Carne con queso y papas",
            precio=Decimal("7000.00"),
            stock=15
        )
        self.prod_jugo = Producto.objects.create(
            nombre="Jugo Natural",
            descripcion="Fruta fresca 500ml",
            precio=Decimal("2500.00"),
            stock=20
        )
        self.mesa1 = Mesa.objects.create(
            numero=10,
            nombre="Mesa 10",
            estado="desocupada",
            comida_entregada=False
        )
        self.caja_abierta = ControlCaja.objects.create(
            abierta=True,
            estado='ABIERTA',
            cajero_responsable=self.cajero,
            monto_inicial=Decimal("50000.00")
        )

    def _autenticar(self, usuario):
        session = self.client.session
        session['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'correo': usuario.correo,
            'username': usuario.username,
            'rol': usuario.rol
        }
        session.save()

    def test_venta_rapida_en_barra_inmediata(self):
        """
        Venta en Barra Inmediata:
        - Cajero selecciona productos, notas, método de pago.
        - Descuenta stock de inmediato.
        - Emite boleta correlativa BOL-XXXX al instante.
        - Genera comanda a cocina con notas.
        """
        self._autenticar(self.cajero)

        stock_inicial_hab = self.prod_hamburguesa.stock  # 15
        stock_inicial_jugo = self.prod_jugo.stock        # 20

        payload = {
            'tipo_venta': 'barra',
            'mesa': 'Barra Principal',
            'metodo_pago': 'efectivo',
            'notas': 'Sin tomate y bebida bien helada',
            'items': [
                {'id': self.prod_hamburguesa.id, 'cantidad': 2},
                {'id': self.prod_jugo.id, 'cantidad': 1}
            ],
            'total': 16500
        }

        response = self.client.post(
            '/cajero/registrar-venta/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['tipo_venta'], 'barra')
        self.assertTrue(data['folio'].startswith('BOL-'))
        self.assertEqual(data['notas'], 'Sin tomate y bebida bien helada')

        # 1. Descuento de stock inmediato
        self.prod_hamburguesa.refresh_from_db()
        self.prod_jugo.refresh_from_db()
        self.assertEqual(self.prod_hamburguesa.stock, stock_inicial_hab - 2)
        self.assertEqual(self.prod_jugo.stock, stock_inicial_jugo - 1)

        # 2. Venta oficial registrada
        venta_id = int(data['folio'].replace('BOL-', ''))
        venta = Venta.objects.filter(id=venta_id).first()
        self.assertIsNotNone(venta)
        self.assertEqual(venta.folio, data['folio'])
        self.assertEqual(venta.tipo_venta, 'barra')
        self.assertEqual(venta.total, Decimal("16500.00"))
        self.assertEqual(venta.metodo_pago, 'efectivo')
        self.assertEqual(venta.notas, 'Sin tomate y bebida bien helada')

        # 3. Comanda generada para cocina
        comanda = Comanda.objects.filter(venta=venta).first()
        self.assertIsNotNone(comanda)
        self.assertEqual(comanda.tipo_pedido, 'barra')
        self.assertEqual(comanda.notas, 'Sin tomate y bebida bien helada')
        self.assertTrue(comanda.pagada)
        self.assertEqual(comanda.estado, 'preparacion')

    def test_toma_pedido_mesero_sin_emision_boleta_y_estado_en_espera(self):
        """
        Toma de Pedido de Garzón:
        - Mesero selecciona mesa física (pasa a 'ocupada').
        - Genera comanda hacia cocina en estado 'en_espera' con notas.
        - NO emite boleta (no se crea Venta).
        - El stock no se descuenta aún.
        """
        self._autenticar(self.mesero)

        self.assertEqual(self.mesa1.estado, 'desocupada')
        stock_inicial = self.prod_hamburguesa.stock

        payload = {
            'mesa_id': self.mesa1.id,
            'notas': 'Carne término tres cuartos, aderezo aparte',
            'items': [
                {'id': self.prod_hamburguesa.id, 'cantidad': 3}
            ]
        }

        response = self.client.post(
            '/mesero/tomar-pedido/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['estado'], 'en_espera')
        self.assertEqual(data['mesa_estado'], 'ocupada')
        self.assertTrue(data['folio'].startswith('COM-'))

        # 1. Mesa pasa a 'ocupada'
        self.mesa1.refresh_from_db()
        self.assertEqual(self.mesa1.estado, 'ocupada')

        # 2. Comanda en cocina creada en 'en_espera'
        comanda = Comanda.objects.filter(id=data['comanda_id']).first()
        self.assertIsNotNone(comanda)
        self.assertEqual(comanda.estado, 'en_espera')
        self.assertEqual(comanda.notas, 'Carne término tres cuartos, aderezo aparte')
        self.assertEqual(comanda.tipo_pedido, 'mesa')
        self.assertFalse(comanda.pagada)
        self.assertEqual(comanda.mesa_rel, self.mesa1)

        # 3. NO emite boleta (no existe Venta generada para este pedido)
        self.assertEqual(Venta.objects.count(), 0)

        # 4. Stock intacto (se descontará al liquidar)
        self.prod_hamburguesa.refresh_from_db()
        self.assertEqual(self.prod_hamburguesa.stock, stock_inicial)

    def test_liquidacion_mesa_en_caja_emite_boleta_y_libera_mesa(self):
        """
        Liquidación de Mesa en Caja:
        - Cliente pide la cuenta.
        - Cajero visualiza la cuenta (/cajero/mesa-cuenta/<id>/).
        - Cajero liquida la mesa (/cajero/liquidar-mesa/).
        - Descuenta stock en este momento.
        - Emite boleta correlativa BOL-XXXX.
        - Marca comanda pagada y desocupa la mesa ('desocupada').
        """
        # Paso 1: Garzón toma pedido
        self._autenticar(self.mesero)
        self.client.post(
            '/mesero/tomar-pedido/',
            data=json.dumps({
                'mesa_id': self.mesa1.id,
                'notas': 'Mesa 10 - cliente celíaco',
                'items': [{'id': self.prod_hamburguesa.id, 'cantidad': 2}]
            }),
            content_type='application/json'
        )
        self.mesa1.refresh_from_db()
        self.assertEqual(self.mesa1.estado, 'ocupada')

        # Paso 2: Cajero consulta cuenta de la mesa
        self._autenticar(self.cajero)
        res_cuenta = self.client.get(f'/cajero/mesa-cuenta/{self.mesa1.id}/')
        self.assertEqual(res_cuenta.status_code, 200)
        data_cuenta = res_cuenta.json()
        self.assertTrue(data_cuenta['success'])
        self.assertEqual(data_cuenta['total'], 14000.0)
        self.assertEqual(data_cuenta['notas'], 'Mesa 10 - cliente celíaco')
        comanda_id = data_cuenta['comanda_id']

        # Paso 3: Cajero liquida la mesa
        stock_antes_liquidacion = self.prod_hamburguesa.stock  # 15
        res_liquidar = self.client.post(
            '/cajero/liquidar-mesa/',
            data=json.dumps({
                'mesa_id': self.mesa1.id,
                'comanda_id': comanda_id,
                'metodo_pago': 'tarjeta'
            }),
            content_type='application/json'
        )
        self.assertEqual(res_liquidar.status_code, 200)
        data_liq = res_liquidar.json()
        self.assertTrue(data_liq['success'])
        self.assertEqual(data_liq['tipo_venta'], 'mesa')
        self.assertTrue(data_liq['folio'].startswith('BOL-'))

        # 1. Stock descontado ahora
        self.prod_hamburguesa.refresh_from_db()
        self.assertEqual(self.prod_hamburguesa.stock, stock_antes_liquidacion - 2)

        # 2. Boleta emitida vinculada a la mesa y caja
        venta_id = int(data_liq['folio'].replace('BOL-', ''))
        venta = Venta.objects.filter(id=venta_id).first()
        self.assertIsNotNone(venta)
        self.assertEqual(venta.folio, data_liq['folio'])
        self.assertEqual(venta.tipo_venta, 'mesa')
        self.assertEqual(venta.metodo_pago, 'tarjeta')
        self.assertEqual(venta.total, Decimal("14000.00"))
        self.assertEqual(venta.mesa, self.mesa1)
        self.assertEqual(venta.notas, 'Mesa 10 - cliente celíaco')

        # 3. Comanda marcada como pagada y vinculada a la venta
        comanda = Comanda.objects.get(id=comanda_id)
        self.assertTrue(comanda.pagada)
        self.assertEqual(comanda.venta, venta)

        # 4. Mesa liberada ('desocupada')
        self.mesa1.refresh_from_db()
        self.assertEqual(self.mesa1.estado, 'desocupada')

    def test_bloqueo_liquidacion_mesa_con_caja_cerrada(self):
        """Verifica que la liquidación de mesa se bloquee con HTTP 400 si la caja está cerrada."""
        # Garzón toma pedido
        self._autenticar(self.mesero)
        self.client.post(
            '/mesero/tomar-pedido/',
            data=json.dumps({
                'mesa_id': self.mesa1.id,
                'items': [{'id': self.prod_hamburguesa.id, 'cantidad': 1}]
            }),
            content_type='application/json'
        )

        # Cerrar todas las cajas
        ControlCaja.objects.all().update(abierta=False, estado='CERRADA')

        # Cajero intenta liquidar
        self._autenticar(self.cajero)
        res = self.client.post(
            '/cajero/liquidar-mesa/',
            data=json.dumps({
                'mesa_id': self.mesa1.id,
                'metodo_pago': 'efectivo'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertFalse(data['success'])
        self.assertIn('CERRADA', data['error'])

        # Mesa permanece ocupada
        self.mesa1.refresh_from_db()
        self.assertEqual(self.mesa1.estado, 'ocupada')

    def test_api_mesas_con_cuenta(self):
        """Verifica que /api/mesas-con-cuenta/ retorne solo mesas ocupadas con pedidos activos."""
        self._autenticar(self.mesero)
        self.client.post(
            '/mesero/tomar-pedido/',
            data=json.dumps({
                'mesa_id': self.mesa1.id,
                'notas': 'Pedido en mesa 10',
                'items': [{'id': self.prod_jugo.id, 'cantidad': 2}]
            }),
            content_type='application/json'
        )

        self._autenticar(self.cajero)
        res = self.client.get('/api/mesas-con-cuenta/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['mesas']), 1)
        self.assertEqual(data['mesas'][0]['mesa_id'], self.mesa1.id)
        self.assertEqual(data['mesas'][0]['total'], 5000.0)

    def test_cocina_transicion_estado_en_espera(self):
        """Verifica que el cocinero pueda cambiar una comanda de 'en_espera' a 'preparacion', 'listo' y 'entregado'."""
        self._autenticar(self.mesero)
        res_pedido = self.client.post(
            '/mesero/tomar-pedido/',
            data=json.dumps({
                'mesa_id': self.mesa1.id,
                'items': [{'id': self.prod_jugo.id, 'cantidad': 1}]
            }),
            content_type='application/json'
        )
        comanda_id = res_pedido.json()['comanda_id']

        self._autenticar(self.cocinero)
        # 1. En espera -> Preparación
        res_prep = self.client.post(
            '/cocina/cambiar-estado/',
            data=json.dumps({'comanda_id': comanda_id, 'nuevo_estado': 'preparacion'}),
            content_type='application/json'
        )
        self.assertEqual(res_prep.status_code, 200)
        self.assertEqual(res_prep.json()['nuevo_estado'], 'preparacion')

        # 2. Preparación -> Listo
        res_listo = self.client.post(
            '/cocina/cambiar-estado/',
            data=json.dumps({'comanda_id': comanda_id, 'nuevo_estado': 'listo'}),
            content_type='application/json'
        )
        self.assertEqual(res_listo.status_code, 200)
        self.assertEqual(res_listo.json()['nuevo_estado'], 'listo')

        # 3. Listo -> Entregado
        res_ent = self.client.post(
            '/cocina/cambiar-estado/',
            data=json.dumps({'comanda_id': comanda_id, 'nuevo_estado': 'entregado'}),
            content_type='application/json'
        )
        self.assertEqual(res_ent.status_code, 200)
        self.assertEqual(res_ent.json()['nuevo_estado'], 'entregado')
class ReordenComandaTestCase(TestCase):
    """
    Pruebas unitarias para el flujo de re-emisión de platillos para cambios o recalentados:
    - Campos es_reemision y motivo_reemision en modelo Comanda.
    - Estados extendidos con 'RE_ORDEN'.
    - Botón 'Re-hacer / Re-orden' para cocina y garzón desde la sección de entregados.
    - Retorno a la cola activa de preparación en cocina con alerta prioritaria.
    - Registro de la acción en HistorialAccion con el usuario responsable.
    """

    def setUp(self):
        self.client = Client()
        self.cocinero = Usuario.objects.create(
            nombre="Ramón Cocinero",
            correo="ramon@safari.cl",
            username="ramoncocina",
            password="password123",
            rol="cocinero"
        )
        self.mesero = Usuario.objects.create(
            nombre="Lucas Garzón",
            correo="lucas@safari.cl",
            username="lucasgarzon",
            password="password123",
            rol="mesero"
        )
        self.cajero = Usuario.objects.create(
            nombre="Patricia Cajera",
            correo="patricia@safari.cl",
            username="patriciacaja",
            password="password123",
            rol="cajero"
        )
        self.mesa = Mesa.objects.create(
            numero=15,
            nombre="Mesa 15",
            estado="ocupada",
            comida_entregada=True
        )
        self.comanda = Comanda.objects.create(
            folio="COM-1501",
            mesa="Mesa 15",
            mesa_rel=self.mesa,
            mesero=self.mesero,
            items="1x Bife de Chorizo ($12.000)",
            total=Decimal("12000.00"),
            estado="entregado",
            es_reemision=False,
            motivo_reemision=None
        )

    def _autenticar(self, usuario):
        session = self.client.session
        session['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'correo': usuario.correo,
            'username': usuario.username,
            'rol': usuario.rol
        }
        session.save()

    def test_modelo_comanda_campos_reemision(self):
        """Verifica que el modelo Comanda tenga es_reemision (default False) y motivo_reemision."""
        cmd = Comanda.objects.create(
            folio="COM-TEST",
            mesa="Mesa 99",
            items="Prueba de platillo",
            total=Decimal("5000.00"),
            estado="preparacion"
        )
        self.assertFalse(cmd.es_reemision)
        self.assertIsNone(cmd.motivo_reemision)

        cmd.es_reemision = True
        cmd.motivo_reemision = "Plato frío, cliente solicita recalentar"
        cmd.estado = "RE_ORDEN"
        cmd.save()

        cmd.refresh_from_db()
        self.assertTrue(cmd.es_reemision)
        self.assertEqual(cmd.motivo_reemision, "Plato frío, cliente solicita recalentar")
        self.assertEqual(cmd.estado, "RE_ORDEN")

    def test_solicitar_reorden_por_cocinero_desde_entregados(self):
        """
        Al pulsar 'Re-hacer', la orden pasa al estado 'RE_ORDEN',
        se activa es_reemision = True y se registra en HistorialAccion.
        """
        self._autenticar(self.cocinero)

        res = self.client.post(
            '/cocina/reorden/',
            data=json.dumps({
                'comanda_id': self.comanda.id,
                'motivo': 'Platillo frío, recalentar bien caliente con papas nuevas'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['estado'], 'RE_ORDEN')
        self.assertTrue(data['es_reemision'])
        self.assertEqual(data['motivo_reemision'], 'Platillo frío, recalentar bien caliente con papas nuevas')

        # 1. Comanda en BD actualizada
        self.comanda.refresh_from_db()
        self.assertEqual(self.comanda.estado, 'RE_ORDEN')
        self.assertTrue(self.comanda.es_reemision)
        self.assertEqual(self.comanda.motivo_reemision, 'Platillo frío, recalentar bien caliente con papas nuevas')

        # 2. Mesa física reactiva espera de comida
        self.mesa.refresh_from_db()
        self.assertFalse(self.mesa.comida_entregada)

        # 3. Auditoría registrada en HistorialAccion
        accion = HistorialAccion.objects.filter(accion='RE_ORDEN', modulo='Cocina').last()
        self.assertIsNotNone(accion)
        self.assertEqual(accion.usuario, self.cocinero)
        self.assertIn(self.comanda.folio, accion.detalle)
        self.assertIn('Platillo frío', accion.detalle)

    def test_solicitar_reorden_por_garzon_y_reingreso_a_cola_cocina(self):
        """Garzón solicita re-hacer platillo y este reingresa a la cola activa de cocina en sección prioritaria."""
        self._autenticar(self.mesero)

        res = self.client.post(
            '/cocina/reorden/',
            data=json.dumps({
                'comanda_id': self.comanda.id,
                'motivo': 'Cliente solicita cambio de término a tres cuartos'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])

        # Comprobar vista del cocinero
        self._autenticar(self.cocinero)
        res_cocina = self.client.get('/cocinero/')
        self.assertEqual(res_cocina.status_code, 200)

        # La comanda ahora está en comandas_reorden y no en entregados
        comandas_reorden = res_cocina.context['comandas_reorden']
        entregados = res_cocina.context['entregados_recientes']

        self.assertTrue(any(c.id == self.comanda.id for c in comandas_reorden))
        self.assertFalse(any(c.id == self.comanda.id for c in entregados))

        # Verificar renderizado en HTML con clase CSS distintiva y motivo
        self.assertContains(res_cocina, 'RE_ORDEN')
        self.assertContains(res_cocina, 'card-reorden')
        self.assertContains(res_cocina, 'Cliente solicita cambio de término a tres cuartos')

    def test_transicion_estado_reorden_a_listo_y_entregado(self):
        """Verifica que la cocina pueda avanzar una RE_ORDEN a listo y entregado."""
        self.comanda.estado = 'RE_ORDEN'
        self.comanda.es_reemision = True
        self.comanda.motivo_reemision = 'Recalentar'
        self.comanda.save()

        self._autenticar(self.cocinero)

        # RE_ORDEN -> Listo
        res_listo = self.client.post(
            '/cocina/cambiar-estado/',
            data=json.dumps({'comanda_id': self.comanda.id, 'nuevo_estado': 'listo'}),
            content_type='application/json'
        )
        self.assertEqual(res_listo.status_code, 200)
        self.comanda.refresh_from_db()
        self.assertEqual(self.comanda.estado, 'listo')

        # Listo -> Entregado
        res_ent = self.client.post(
            '/cocina/cambiar-estado/',
            data=json.dumps({'comanda_id': self.comanda.id, 'nuevo_estado': 'entregado'}),
            content_type='application/json'
        )
        self.assertEqual(res_ent.status_code, 200)
        self.comanda.refresh_from_db()
        self.assertEqual(self.comanda.estado, 'entregado')

    def test_bloqueo_reorden_usuarios_no_autorizados(self):
        """Usuarios sin rol autorizado (o no autenticados) no pueden solicitar re-órdenes."""
        # Sin sesión
        res_anon = self.client.post(
            '/cocina/reorden/',
            data=json.dumps({'comanda_id': self.comanda.id}),
            content_type='application/json'
        )
        self.assertEqual(res_anon.status_code, 403)

        # Cajero (solo cocinero, mesero y administrador pueden pedir re-orden de cocina)
        self._autenticar(self.cajero)
        res_cajero = self.client.post(
            '/cocina/reorden/',
            data=json.dumps({'comanda_id': self.comanda.id}),
            content_type='application/json'
        )
        self.assertEqual(res_cajero.status_code, 403)
class PruebasAuditoriaSeguridadDefensivaTestCase(TestCase):
    """
    Auditoría de Seguridad Defensiva en Safari/views.py:
    1. Blindaje contra alteración de métodos (POST vs. GET):
       Todas las vistas de modificación de BD rechazan peticiones GET con HTTP 405 (o 400).
    2. Inmunidad ante manipulación desde 'Inspeccionar Elemento' (DevTools):
       - Los precios y totales se consultan y recalculan estrictamente en el backend (precio_bd * cant).
       - Cantidades negativas, decimales o strings son rechazadas con HTTP 400 abortando la transacción.
    3. Mitigación total de SQL Injection:
       - Inputs de texto (notas, comentarios, motivos, nombres) rechazan secuencias de escape (--, ;, /*, ' OR '1'='1').
       - Consultas realizadas exclusivamente mediante ORM parametrizado nativo de Django.
    """

    def setUp(self):
        self.admin = Usuario.objects.create(
            nombre="Admin Seguridad",
            correo="admin.sec@safari.cl",
            username="adminsec",
            password="adminpassword123",
            rol="administrador"
        )
        self.cajero = Usuario.objects.create(
            nombre="Cajero Seguridad",
            correo="cajero.sec@safari.cl",
            username="cajerosec",
            password="cajeropassword123",
            rol="cajero"
        )
        self.mesero = Usuario.objects.create(
            nombre="Mesero Seguridad",
            correo="mesero.sec@safari.cl",
            username="meserosec",
            password="meseropassword123",
            rol="mesero"
        )
        self.cocinero = Usuario.objects.create(
            nombre="Cocinero Seguridad",
            correo="cocinero.sec@safari.cl",
            username="cocinerosec",
            password="cocineropassword123",
            rol="cocinero"
        )
        self.producto = Producto.objects.create(
            nombre="Lomo Vetado Premium",
            descripcion="Corte premium 350g a la parrilla",
            precio=Decimal("14500.00"),
            stock=30
        )
        self.mesa = Mesa.objects.create(
            numero=20,
            nombre="Mesa Seguridad 20",
            estado="desocupada",
            comida_entregada=False
        )
        self.caja = ControlCaja.objects.create(
            abierta=True,
            estado='ABIERTA',
            usuario=self.cajero,
            cajero_responsable=self.cajero,
            monto_inicial=Decimal("50000.00"),
            total_ventas=Decimal("0.00")
        )

    def _autenticar(self, usuario):
        session = self.client.session
        session['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'correo': usuario.correo,
            'username': usuario.username,
            'rol': usuario.rol
        }
        session.save()

    # --------------------------------------------------------------------------
    # 1. Blindaje contra alteración de métodos (POST vs. GET)
    # --------------------------------------------------------------------------
    def test_blindaje_metodos_http_rechazo_get_en_vistas_de_modificacion(self):
        """Todas las vistas que modifican base de datos deben rechazar GET con HTTP 405."""
        self._autenticar(self.admin)

        endpoints_requieren_post = [
            '/cajero/registrar-venta/',
            '/cajero/liquidar-mesa/',
            '/mesero/tomar-pedido/',
            '/mesero/cambiar-mesa/',
            '/cocina/reorden/',
            '/cocina/cambiar-estado/',
            '/caja/abrir/',
            '/caja/cerrar/',
            '/stock/agregar/',
        ]

        for url in endpoints_requieren_post:
            with self.subTest(url=url):
                res = self.client.get(url)
                self.assertEqual(
                    res.status_code, 405,
                    f"El endpoint {url} debería rechazar peticiones GET con HTTP 405 Method Not Allowed."
                )

    # --------------------------------------------------------------------------
    # 2. Inmunidad ante manipulación desde 'Inspeccionar Elemento' (DevTools)
    # --------------------------------------------------------------------------
    def test_inmunidad_devtools_tampering_precio_y_total_en_cajero(self):
        """
        Si un atacante modifica el DOM enviando precio=1 y total=2 en el JSON del cliente,
        el backend ignora por completo esos valores y calcula (precio_bd * cant) = $14,500 * 2 = $29,000.
        """
        self._autenticar(self.cajero)

        payload_manipulado = {
            'tipo_venta': 'barra',
            'metodo_pago': 'efectivo',
            'notas': 'Pedido normal sin cebolla',
            'items': [
                {
                    'id': self.producto.id,
                    'nombre': 'Lomo Vetado Premium',
                    'precio': 1.0,  # Manipulación en cliente
                    'cantidad': 2,
                    'subtotal': 2.0  # Manipulación en cliente
                }
            ],
            'total': 2.0  # Manipulación en cliente
        }

        res = self.client.post(
            '/cajero/registrar-venta/',
            data=json.dumps(payload_manipulado),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])

        # Total devuelto y persistido DEBE ser el precio real de la BD: 14500 * 2 = 29000
        self.assertEqual(data['total'], 29000.0)

        # Verificar directamente en la base de datos
        venta_id = int(data['folio'].replace('BOL-', ''))
        venta = Venta.objects.filter(id=venta_id).first()
        self.assertIsNotNone(venta)
        self.assertEqual(venta.total, Decimal("29000.00"))

        detalle = DetalleVenta.objects.filter(venta=venta).first()
        self.assertIsNotNone(detalle)
        self.assertEqual(detalle.subtotal, Decimal("29000.00"))
        self.assertEqual(detalle.cantidad, 2)

    def test_inmunidad_devtools_cantidad_negativa_en_cajero(self):
        """Cantidad negativa enviada desde el cliente es rechazada con HTTP 400 abortando la venta."""
        self._autenticar(self.cajero)

        payload = {
            'tipo_venta': 'barra',
            'metodo_pago': 'efectivo',
            'items': [{'id': self.producto.id, 'cantidad': -3}]
        }
        res = self.client.post('/cajero/registrar-venta/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn("no se permiten negativos", res.json()['error'])

    def test_inmunidad_devtools_cantidad_decimal_en_cajero(self):
        """Cantidad decimal enviada desde el cliente es rechazada con HTTP 400."""
        self._autenticar(self.cajero)

        payload = {
            'tipo_venta': 'barra',
            'metodo_pago': 'efectivo',
            'items': [{'id': self.producto.id, 'cantidad': 2.5}]
        }
        res = self.client.post('/cajero/registrar-venta/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn("no se permiten decimales", res.json()['error'])

    def test_inmunidad_devtools_cantidad_string_no_numerico_en_cajero(self):
        """Cantidad con string no numérico es rechazada con HTTP 400."""
        self._autenticar(self.cajero)

        payload = {
            'tipo_venta': 'barra',
            'metodo_pago': 'efectivo',
            'items': [{'id': self.producto.id, 'cantidad': "cinco"}]
        }
        res = self.client.post('/cajero/registrar-venta/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_inmunidad_devtools_cantidad_invalida_en_mesero(self):
        """Validación estricta de cantidad en toma de pedidos de garzón / mesero."""
        self._autenticar(self.mesero)

        # 1. Negativa
        res_neg = self.client.post(
            '/mesero/tomar-pedido/',
            data=json.dumps({'mesa_id': self.mesa.id, 'items': [{'id': self.producto.id, 'cantidad': -1}]}),
            content_type='application/json'
        )
        self.assertEqual(res_neg.status_code, 400)

        # 2. Decimal
        res_dec = self.client.post(
            '/mesero/tomar-pedido/',
            data=json.dumps({'mesa_id': self.mesa.id, 'items': [{'id': self.producto.id, 'cantidad': 1.5}]}),
            content_type='application/json'
        )
        self.assertEqual(res_dec.status_code, 400)

        # 3. String no numérico
        res_str = self.client.post(
            '/mesero/tomar-pedido/',
            data=json.dumps({'mesa_id': self.mesa.id, 'items': [{'id': self.producto.id, 'cantidad': "dos"}]}),
            content_type='application/json'
        )
        self.assertEqual(res_str.status_code, 400)

    def test_inmunidad_devtools_cantidad_invalida_en_stock_agregar(self):
        """Reposición de stock rechaza cantidades negativas, decimales o strings no numéricos."""
        self._autenticar(self.admin)

        # Negativo
        res_neg = self.client.post(
            '/stock/agregar/',
            data=json.dumps({'producto_id': self.producto.id, 'cantidad_agregar': -10}),
            content_type='application/json'
        )
        self.assertEqual(res_neg.status_code, 400)

        # Decimal
        res_dec = self.client.post(
            '/stock/agregar/',
            data=json.dumps({'producto_id': self.producto.id, 'cantidad_agregar': 12.5}),
            content_type='application/json'
        )
        self.assertEqual(res_dec.status_code, 400)

    def test_inmunidad_devtools_liquidar_mesa_recalcula_precio_db(self):
        """Al liquidar una mesa, el total se recalcula estrictamente con el precio de BD."""
        self._autenticar(self.cajero)

        comanda = Comanda.objects.create(
            folio="COM-SEC99",
            mesa=self.mesa.nombre,
            mesa_rel=self.mesa,
            mesero=self.mesero,
            items="1x Lomo Vetado",
            items_json=json.dumps([{'id': self.producto.id, 'cantidad': 2}]),
            total=Decimal("999.00"),  # Total alterado en comanda
            pagada=False,
            estado='en_espera'
        )
        self.mesa.estado = 'ocupada'
        self.mesa.save()

        res = self.client.post(
            '/cajero/liquidar-mesa/',
            data=json.dumps({
                'mesa_id': self.mesa.id,
                'comanda_id': comanda.id,
                'metodo_pago': 'efectivo',
                'total': 5.0  # Intento de forzar total
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])

        # Total recalculado por backend: 14500 * 2 = 29000
        self.assertEqual(data['total'], 29000.0)

        comanda.refresh_from_db()
        self.assertTrue(comanda.pagada)
        self.assertEqual(comanda.total, Decimal("29000.00"))

    # --------------------------------------------------------------------------
    # 3. Mitigación total de SQL Injection
    # --------------------------------------------------------------------------
    def test_mitigacion_sql_injection_en_notas_cajero(self):
        """Inyección SQL en notas o comentarios de venta en barra es rechazada con HTTP 400."""
        self._autenticar(self.cajero)

        vectores_maliciosos = [
            "Sin sal; DROP TABLE Safari_venta; --",
            "Mesa 1' OR '1'='1",
            'Mesa 1" OR "1"="1',
            "Notas /* comentario SQL malicioso */ adicionales",
            "Texto con escape -- resto de consulta ignorado"
        ]

        for vector in vectores_maliciosos:
            with self.subTest(vector=vector):
                payload = {
                    'tipo_venta': 'barra',
                    'metodo_pago': 'efectivo',
                    'notas': vector,
                    'items': [{'id': self.producto.id, 'cantidad': 1}]
                }
                res = self.client.post('/cajero/registrar-venta/', data=json.dumps(payload), content_type='application/json')
                self.assertEqual(res.status_code, 400)
                self.assertIn("Petición rechazada", res.json()['error'])

    def test_mitigacion_sql_injection_en_notas_mesero(self):
        """Inyección SQL en notas de comanda de garzón es rechazada con HTTP 400."""
        self._autenticar(self.mesero)

        vectores_maliciosos = [
            "Plato 1; DELETE FROM Safari_comanda; --",
            "' OR '1'='1",
            "/* bypass SQL */ pedido rápido"
        ]

        for vector in vectores_maliciosos:
            with self.subTest(vector=vector):
                payload = {
                    'mesa_id': self.mesa.id,
                    'notas': vector,
                    'items': [{'id': self.producto.id, 'cantidad': 1}]
                }
                res = self.client.post('/mesero/tomar-pedido/', data=json.dumps(payload), content_type='application/json')
                self.assertEqual(res.status_code, 400)
                self.assertIn("Petición rechazada", res.json()['error'])

    def test_mitigacion_sql_injection_en_motivo_reorden(self):
        """Inyección SQL en motivo de re-emisión en cocina es rechazada con HTTP 400."""
        self._autenticar(self.cocinero)

        cmd = Comanda.objects.create(
            folio="COM-RE99",
            mesa="Mesa 1",
            items="Prueba",
            total=Decimal("5000.00"),
            estado="entregado"
        )

        res = self.client.post(
            '/cocina/reorden/',
            data=json.dumps({'comanda_id': cmd.id, 'motivo': "Plato frío' OR '1'='1"}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Petición rechazada", res.json()['error'])

    def test_mitigacion_sql_injection_en_formularios_mantenedores_y_admin(self):
        """Formularios de mantenedores rechazan secuencias de escape e inyección SQL con HTTP 400."""
        self._autenticar(self.admin)

        # 1. Admin guardar usuario con inyección en nombre
        res_usr = self.client.post('/administrador/guardar-usuario/', {
            'nombre': "Hacker -- Drop Table",
            'correo': "hacker@safari.cl",
            'username': "hacker123",
            'password': "password123",
            'rol': "cajero",
            'estado': "activo"
        })
        self.assertEqual(res_usr.status_code, 400)

        # 2. Mantenedor mesa con inyección en nombre
        res_mesa = self.client.post('/mantenedores/mesas/guardar/', {
            'nombre': "Mesa 1' OR '1'='1",
            'numero': 99,
            'capacidad': 4,
            'estado': "disponible"
        })
        self.assertEqual(res_mesa.status_code, 400)

        # 3. Mantenedor producto con inyección en descripción
        res_prod = self.client.post('/mantenedores/productos/guardar/', {
            'nombre': "Bebida Segura",
            'descripcion': "Refresco /* inyeccion */ de cola",
            'precio': 2000,
            'stock': 10
        })
        self.assertEqual(res_prod.status_code, 400)
class PruebasReportesEstadisticosTestCase(TestCase):
    """
    Pruebas unitarias para el módulo robustecido de Reportes Estadísticos:
    - Agregaciones Django ORM (Sum, Count, Avg).
    - Total recaudado en la jornada actual y desglose histórico por fecha.
    - Desglose de ingresos por método de pago (Efectivo vs. Tarjeta).
    - Ranking de los 5 productos con mayor volumen de venta (DetalleVenta con annotate(total_vendido=Sum('cantidad'))).
    - Total de diferencias de caja registradas (sobrantes y faltantes acumulados en cuadraturas).
    - Renderizado limpio en tarjetas métricas y tablas ordenadas en administrador.html.
    """

    def setUp(self):
        self.admin = Usuario.objects.create(
            nombre="Admin Estadísticas",
            correo="admin.stats@safari.cl",
            username="adminstats",
            password="adminpassword123",
            rol="administrador"
        )
        self.cajero = Usuario.objects.create(
            nombre="Cajero Turno",
            correo="cajero.turno@safari.cl",
            username="cajeroturno",
            password="cajeropassword123",
            rol="cajero"
        )
        self.mesero = Usuario.objects.create(
            nombre="Mesero Turno",
            correo="mesero.turno@safari.cl",
            username="meseroturno",
            password="meseropassword123",
            rol="mesero"
        )

        # Crear 6 productos para verificar el ranking de los 5 más vendidos
        self.p1 = Producto.objects.create(nombre="Hamburguesa Gigante", precio=Decimal("10000.00"), stock=50)
        self.p2 = Producto.objects.create(nombre="Papas Rústicas", precio=Decimal("4000.00"), stock=50)
        self.p3 = Producto.objects.create(nombre="Bebida Cola 500ml", precio=Decimal("2000.00"), stock=50)
        self.p4 = Producto.objects.create(nombre="Cerveza Artesanal", precio=Decimal("5000.00"), stock=50)
        self.p5 = Producto.objects.create(nombre="Postre Volcán", precio=Decimal("4500.00"), stock=50)
        self.p6 = Producto.objects.create(nombre="Café Espresso", precio=Decimal("1800.00"), stock=50)

        # Caja abierta actual
        self.caja_activa = ControlCaja.objects.create(
            abierta=True,
            estado='ABIERTA',
            usuario=self.cajero,
            cajero_responsable=self.cajero,
            monto_inicial=Decimal("50000.00")
        )

        # Cajas cerradas previas con sobrantes y faltantes en cuadraturas
        self.caja_cerrada_1 = ControlCaja.objects.create(
            abierta=False,
            estado='CERRADA',
            usuario=self.cajero,
            cajero_responsable=self.cajero,
            cerrada_por=self.admin,
            monto_inicial=Decimal("50000.00"),
            total_ventas=Decimal("100000.00"),
            total_efectivo=Decimal("60000.00"),
            monto_real=Decimal("112000.00"),
            total_efectivo_declarado=Decimal("112000.00"),
            diferencia=Decimal("2000.00"),  # Sobrante +$2.000
            diferencia_cuadratura=Decimal("2000.00")
        )
        self.caja_cerrada_2 = ControlCaja.objects.create(
            abierta=False,
            estado='CERRADA',
            usuario=self.cajero,
            cajero_responsable=self.cajero,
            cerrada_por=self.admin,
            monto_inicial=Decimal("50000.00"),
            total_ventas=Decimal("80000.00"),
            total_efectivo=Decimal("50000.00"),
            monto_real=Decimal("97000.00"),
            total_efectivo_declarado=Decimal("97000.00"),
            diferencia=Decimal("-3000.00"),  # Faltante -$3.000
            diferencia_cuadratura=Decimal("-3000.00")
        )

        # Ventas de hoy
        self.v1 = Venta.objects.create(
            usuario=self.cajero,
            mesero=self.mesero,
            control_caja=self.caja_activa,
            metodo_pago='efectivo',
            total=Decimal("24000.00")
        )
        DetalleVenta.objects.create(venta=self.v1, producto=self.p1, cantidad=2, subtotal=Decimal("20000.00"))
        DetalleVenta.objects.create(venta=self.v1, producto=self.p2, cantidad=1, subtotal=Decimal("4000.00"))

        self.v2 = Venta.objects.create(
            usuario=self.cajero,
            mesero=self.mesero,
            control_caja=self.caja_activa,
            metodo_pago='tarjeta',
            total=Decimal("16000.00")
        )
        DetalleVenta.objects.create(venta=self.v2, producto=self.p1, cantidad=1, subtotal=Decimal("10000.00"))
        DetalleVenta.objects.create(venta=self.v2, producto=self.p3, cantidad=3, subtotal=Decimal("6000.00"))

        self.v3 = Venta.objects.create(
            usuario=self.cajero,
            mesero=self.mesero,
            control_caja=self.caja_activa,
            metodo_pago='tarjeta',
            total=Decimal("15000.00")
        )
        DetalleVenta.objects.create(venta=self.v3, producto=self.p4, cantidad=3, subtotal=Decimal("15000.00"))

        self.v4 = Venta.objects.create(
            usuario=self.cajero,
            mesero=self.mesero,
            control_caja=self.caja_activa,
            metodo_pago='efectivo',
            total=Decimal("9000.00")
        )
        DetalleVenta.objects.create(venta=self.v4, producto=self.p5, cantidad=2, subtotal=Decimal("9000.00"))

        # p6 se vende 1 unidad (no debe clasificar en el top si otros superan su volumen)
        self.v5 = Venta.objects.create(
            usuario=self.cajero,
            mesero=self.mesero,
            control_caja=self.caja_activa,
            metodo_pago='transferencia',
            total=Decimal("1800.00")
        )
        DetalleVenta.objects.create(venta=self.v5, producto=self.p6, cantidad=1, subtotal=Decimal("1800.00"))

    def _autenticar(self, usuario):
        session = self.client.session
        session['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'correo': usuario.correo,
            'username': usuario.username,
            'rol': usuario.rol
        }
        session.save()

    def test_reportes_agregaciones_jornada_actual(self):
        """Verifica el cálculo de totales agregados (Sum, Count, Avg) de la jornada actual."""
        self._autenticar(self.admin)
        res = self.client.get('/administrador/')
        self.assertEqual(res.status_code, 200)

        ctx = res.context
        # Total recaudado jornada = 24.000 + 16.000 + 15.000 + 9.000 + 1.800 = 65.800
        self.assertEqual(ctx['total_jornada'], Decimal("65800.00"))
        self.assertEqual(ctx['cant_jornada'], 5)
        # Ticket promedio = 65.800 / 5 = 13.160
        self.assertEqual(ctx['prom_jornada'], Decimal("13160.00"))
        # Desglose en la jornada
        self.assertEqual(ctx['jornada_efectivo'], Decimal("33000.00"))  # 24.000 + 9.000
        self.assertEqual(ctx['jornada_tarjeta'], Decimal("31000.00"))   # 16.000 + 15.000
        self.assertEqual(ctx['jornada_transferencia'], Decimal("1800.00"))

    def test_desglose_historico_por_fecha(self):
        """Verifica que el desglose histórico agrupe por fecha con agregaciones nativas."""
        self._autenticar(self.admin)
        res = self.client.get('/administrador/')
        self.assertEqual(res.status_code, 200)

        desglose = res.context['desglose_por_fecha']
        self.assertTrue(len(desglose) >= 1)
        # El primer día contiene las ventas creadas en setUp
        primer_dia = desglose[0]
        self.assertIn('fecha_dia', primer_dia)
        self.assertEqual(primer_dia['total_recaudado'], Decimal("65800.00"))
        self.assertEqual(primer_dia['cantidad_ventas'], 5)
        self.assertEqual(primer_dia['total_efectivo'], Decimal("33000.00"))
        self.assertEqual(primer_dia['total_tarjeta'], Decimal("31000.00"))

    def test_desglose_ingresos_por_metodo_pago(self):
        """Verifica desglose de ingresos por método de pago (Efectivo vs. Tarjeta)."""
        self._autenticar(self.admin)
        res = self.client.get('/administrador/')
        self.assertEqual(res.status_code, 200)

        ctx = res.context
        self.assertEqual(ctx['total_efectivo_gral'], Decimal("33000.00"))
        self.assertEqual(ctx['total_tarjeta_gral'], Decimal("31000.00"))
        self.assertEqual(ctx['total_transferencia_gral'], Decimal("1800.00"))

        # Verificar porcentajes calculados
        # Total = 65.800 -> Efectivo = 33000 / 65800 = 50.2%, Tarjeta = 31000 / 65800 = 47.1%
        self.assertAlmostEqual(ctx['pct_efectivo'], 50.2, places=1)
        self.assertAlmostEqual(ctx['pct_tarjeta'], 47.1, places=1)

        # Lista de métodos para la tabla
        metodos = {m['metodo_key']: m for m in ctx['desglose_metodos']}
        self.assertIn('efectivo', metodos)
        self.assertIn('tarjeta', metodos)
        self.assertEqual(metodos['efectivo']['cantidad_ventas'], 2)
        self.assertEqual(metodos['tarjeta']['cantidad_ventas'], 2)

    def test_ranking_top_5_productos_con_annotate_total_vendido(self):
        """
        Verifica el ranking de los 5 productos con mayor volumen de venta:
        DetalleVenta agrupado por producto con annotate(total_vendido=Sum('cantidad')).
        """
        self._autenticar(self.admin)
        res = self.client.get('/administrador/')
        self.assertEqual(res.status_code, 200)

        top_5 = list(res.context['top_5_productos'])
        self.assertLessEqual(len(top_5), 5)

        # Unidades vendidas:
        # p1 (Hamburguesa Gigante): 2 + 1 = 3 unidades
        # p3 (Bebida Cola): 3 unidades
        # p4 (Cerveza): 3 unidades
        # p5 (Volcán): 2 unidades
        # p2 (Papas): 1 unidad
        # p6 (Café): 1 unidad
        # Los productos en el top deben tener total_vendido >= 1
        for prod in top_5:
            self.assertIn('total_vendido', prod)
            self.assertIn('total_recaudado', prod)
            self.assertGreater(prod['total_vendido'], 0)

        # Comprobar que el orden es descendente por total_vendido
        volumenes = [p['total_vendido'] for p in top_5]
        self.assertEqual(volumenes, sorted(volumenes, reverse=True))

    def test_total_diferencias_caja_cuadraturas(self):
        """Verifica la agregación de diferencias de caja registradas (sobrantes y faltantes)."""
        self._autenticar(self.admin)
        res = self.client.get('/administrador/')
        self.assertEqual(res.status_code, 200)

        ctx = res.context
        # Caja 1: Sobrante +$2.000 | Caja 2: Faltante -$3.000 -> Neto = -$1.000
        self.assertEqual(ctx['total_diferencias_caja'], Decimal("-1000.00"))
        self.assertEqual(ctx['total_sobrantes_caja'], Decimal("2000.00"))
        self.assertEqual(ctx['total_faltantes_caja'], Decimal("-3000.00"))
        self.assertEqual(ctx['conteo_sobrantes_caja'], 1)
        self.assertEqual(ctx['conteo_faltantes_caja'], 1)
        self.assertEqual(ctx['total_cuadraturas_caja'], 2)

    def test_renderizado_en_template_administrador(self):
        """Verifica que administrador.html renderice las tarjetas métricas y tablas ordenadas."""
        self._autenticar(self.admin)
        res = self.client.get('/administrador/')
        self.assertEqual(res.status_code, 200)

        # 1. Títulos de secciones y tarjetas métricas
        self.assertContains(res, 'Reportes Estadísticos y Rendimiento Financiero')
        self.assertContains(res, 'Jornada Actual (Hoy)')
        self.assertContains(res, 'Efectivo vs. Tarjeta')
        self.assertContains(res, 'Diferencias de Cuadratura')

        # 2. Tablas ordenadas
        self.assertContains(res, 'Desglose Histórico por Fecha')
        self.assertContains(res, 'Desglose de Ingresos por Método de Pago')
        self.assertContains(res, 'Ranking: Top 5 Productos con Mayor Volumen de Venta')
        self.assertContains(res, 'Auditoría y Diferencias de Caja en Cuadraturas')

        # 3. Datos representados
        self.assertContains(res, 'Hamburguesa Gigante')
        self.assertContains(res, 'Sobrante')
        self.assertContains(res, 'Faltante')
        self.assertContains(res, 'podium-badge')
        self.assertContains(res, 'table-reports')


class PruebasResolucionErrorCriticoAdministradorTestCase(TestCase):
    """
    Pruebas unitarias de resolución del error crítico en la URL y vista de Administrador:
    - Validación del name='administrador' en urls.py y resolución inversa (reverse / resolve).
    - Verificación de redirección post-login usando el name='administrador'.
    - Validación de bloques try/except con renderizado limpio de templates en errors/ (401, 403, 500).
    - Inmunidad ante datos con valores nulos (fecha_apertura nula, relaciones sin asignar).
    """

    def setUp(self):
        self.client = Client()
        self.admin = Usuario.objects.create(
            rut="12.345.678-9",
            nombre="Super Admin",
            correo="superadmin@safari.cl",
            username="super_admin",
            password="adminpassword123",
            rol="administrador",
            estado="activo"
        )
        self.cajero = Usuario.objects.create(
            rut="14.567.890-1",
            nombre="Juan Cajero",
            correo="juan.cajero@safari.cl",
            username="juan_cajero",
            password="cajeropassword123",
            rol="cajero",
            estado="activo"
        )

    def _autenticar(self, usuario):
        s = self.client.session
        s['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'username': usuario.username,
            'rol': usuario.rol,
        }
        s.save()

    def test_resolucion_url_name_administrador(self):
        """Verifica que name='administrador' esté definido en urls.py y resuelva a /administrador/."""
        url_reversa = reverse('administrador')
        self.assertEqual(url_reversa, '/administrador/')

        resolved = resolve('/administrador/')
        self.assertEqual(resolved.url_name, 'administrador')

    def test_redireccion_post_login_administrador_apunta_al_name_de_url(self):
        """Verifica que la redirección post-login del perfil Administrador apunte exactamente al name 'administrador'."""
        response = self.client.post('/login/', {
            'username': self.admin.username,
            'password': 'adminpassword123'
        })
        self.assertRedirects(response, reverse('administrador'))
        self.assertEqual(self.client.session.get('usuario')['rol'], 'administrador')

    def test_administrador_sin_sesion_renderiza_limpiamente_401(self):
        """Verifica que ingresar a /administrador/ sin sesión renderice limpiamente errors/401.html con HTTP 401."""
        response = self.client.get(reverse('administrador'))
        self.assertEqual(response.status_code, 401)
        self.assertTemplateUsed(response, 'errors/401.html')
        self.assertContains(response, 'Error 401', status_code=401)

    def test_administrador_con_rol_no_autorizado_renderiza_limpiamente_403(self):
        """Verifica que un usuario autenticado con rol cajero reciba HTTP 403 y errors/403.html."""
        self._autenticar(self.cajero)
        response = self.client.get(reverse('administrador'))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'errors/403.html')
        self.assertContains(response, 'Error 403', status_code=403)

    def test_administrador_con_sesion_valida_renderiza_200(self):
        """Verifica que el Administrador autenticado ingrese exitosamente al módulo con HTTP 200."""
        self._autenticar(self.admin)
        response = self.client.get(reverse('administrador'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'administrador.html')

    def test_administrador_manejo_controlado_excepcion_bd_renderiza_500(self):
        """
        Verifica que ante un fallo de base de datos o error interno en las consultas,
        el bloque try/except capture el fallo y renderice limpiamente errors/500.html con HTTP 500
        en lugar de exponer una pantalla de depuración rota.
        """
        self._autenticar(self.admin)
        with patch('Safari.models.Usuario.objects.all', side_effect=Exception('Fallo crítico simulado en conexión a BD')):
            response = self.client.get(reverse('administrador'))
            self.assertEqual(response.status_code, 500)
            self.assertTemplateUsed(response, 'errors/500.html')
            self.assertContains(response, 'Error 500', status_code=500)
            self.assertContains(response, 'Fallo crítico simulado en conexión a BD', status_code=500)

    def test_administrador_caja_con_datos_nulos_no_genera_crashes(self):
        """
        Verifica que si existe un ControlCaja con cajero_responsable=None o usuario=None,
        la vista administre el cálculo con defensas y no lance TypeError ni DoesNotExist.
        """
        self._autenticar(self.admin)
        caja_huerfana = ControlCaja.objects.create(
            monto_inicial=Decimal("50000.00"),
            estado="ABIERTA",
            abierta=True
        )
        ControlCaja.objects.filter(id=caja_huerfana.id).update(cajero_responsable=None, usuario=None)

        response = self.client.get(reverse('administrador'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'administrador.html')
        self.assertContains(response, 'Sin asignar', status_code=200)

    def test_acceso_administrador_sin_slash_final_funciona(self):
        """Verifica que acceder a /administrador sin slash final sea gestionado correctamente sin error 404."""
        self._autenticar(self.admin)
        response = self.client.get('/administrador')
        self.assertIn(response.status_code, [200, 301, 302])


class PruebasValidacionEstrictaCaracteresEspecialesTestCase(TestCase):
    """
    Suite de Pruebas Unitarias e Integración para Validación Estricta de Caracteres Especiales:
    - Neutralización de Inyecciones SQL y ataques XSS (OWASP A03:2021).
    - Verificación rigurosa de la función utilitaria validar_texto_seguro(texto).
    - Rechazo inmediato de los 16 símbolos peligrosos: #, $, %, !, /, &, (, ), =, :, _, ;, ', ", --, /*.
    - Validación defensiva en Formularios (Login, Usuarios, Productos, Mesas, PDV, Menús).
    - Validación defensiva en Comandas / Notas de pedido y Motivos de re-orden.
    - Validación defensiva temprana en Búsquedas y filtros GET (Stock, Ventas, Auditoría).
    - Presencia global del script validaciones.js en todas las plantillas HTML (Inmunidad DevTools).
    - Garantía de 100% de consultas parametrizadas con el ORM de Django sin SQL en crudo.
    """

    def setUp(self):
        self.admin = Usuario.objects.create(
            nombre="Admin Defensivo",
            correo="admin_defensa@safari.cl",
            username="admin_defensa",
            password="adminpassword123",
            rol="administrador",
            estado="activo"
        )
        self.cajero = Usuario.objects.create(
            nombre="Cajero Defensivo",
            correo="cajero_defensa@safari.cl",
            username="cajero_defensa",
            password="cajeropassword123",
            rol="cajero",
            estado="activo"
        )
        self.mesero = Usuario.objects.create(
            nombre="Mesero Defensivo",
            correo="mesero_defensa@safari.cl",
            username="mesero_defensa",
            password="meseropassword123",
            rol="mesero",
            estado="activo"
        )
        self.cocinero = Usuario.objects.create(
            nombre="Cocinero Defensivo",
            correo="cocinero_defensa@safari.cl",
            username="cocinero_defensa",
            password="cocineropassword123",
            rol="cocinero",
            estado="activo"
        )
        self.punto_venta = PuntoDeVenta.objects.create(
            nombre="Caja Central Defensiva",
            ubicacion="Acceso Principal",
            estado="activo"
        )
        self.mesa = Mesa.objects.create(
            numero=15,
            nombre="Mesa Defensiva 15",
            capacidad=4,
            estado="desocupada"
        )
        self.producto = Producto.objects.create(
            nombre="Hamburguesa Protegida",
            descripcion="Carne y queso sin caracteres maliciosos",
            precio=Decimal("7500.00"),
            stock=50
        )
        self.simbolos_prohibidos = [
            '#', '$', '%', '!', '/', '&', '(', ')', '=', ':', '_', ';', "'", '"', '--', '/*'
        ]

    def _autenticar(self, usuario):
        session = self.client.session
        session['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'username': usuario.username,
            'rol': usuario.rol,
        }
        session.save()

    def test_utilitaria_validar_texto_seguro_rechaza_todos_los_16_simbolos_prohibidos(self):
        """Verifica que validar_texto_seguro rechace de inmediato los 16 símbolos peligrosos."""
        from .auth_utils import validar_texto_seguro

        for simbolo in self.simbolos_prohibidos:
            texto_malicioso = f"entrada{simbolo}peligrosa"
            resultado = validar_texto_seguro(texto_malicioso, nombre_campo="campo_prueba")

            # 1. Evaluación como booleano (if not validar_texto_seguro(...))
            self.assertFalse(bool(resultado), f"El símbolo '{simbolo}' debió ser evaluado como False.")

            # 2. Evaluación mediante desempaquetado de tupla (es_valido, mensaje)
            es_valido, mensaje = resultado
            self.assertFalse(es_valido, f"El símbolo '{simbolo}' no fue rechazado.")
            self.assertIsNotNone(mensaje)
            self.assertIn("caracteres especiales no permitidos", mensaje)

        # Texto válido estándar debe ser aceptado
        texto_seguro = "Platillo Especial Safari 2026 - Con papas rústicas"
        res_ok = validar_texto_seguro(texto_seguro, nombre_campo="campo_prueba")
        self.assertTrue(bool(res_ok))
        es_valido_ok, msg_ok = res_ok
        self.assertTrue(es_valido_ok)
        self.assertIsNone(msg_ok)

    def test_login_rechaza_inmediatamente_simbolos_prohibidos_sin_consultar_bd(self):
        """El login rechaza credenciales con caracteres prohibidos y no toca la BD."""
        for simbolo in self.simbolos_prohibidos:
            if simbolo == '_':
                continue  # Identificador de login permite guión bajo para cuentas preexistentes

            # Username malicioso
            res_user = self.client.post('/login/', {
                'username': f'admin{simbolo}inyeccion',
                'password': 'password123'
            })
            self.assertEqual(res_user.status_code, 200)
            self.assertContains(res_user, 'caracteres especiales no permitidos')
            self.assertNotIn('usuario', self.client.session)

            # Password maliciosa
            res_pass = self.client.post('/login/', {
                'username': 'admin_defensa',
                'password': f'pass{simbolo}inyeccion'
            })
            self.assertEqual(res_pass.status_code, 200)
            self.assertContains(res_pass, 'caracteres especiales no permitidos')
            self.assertNotIn('usuario', self.client.session)

    def test_admin_y_mantenedores_guardar_usuario_rechaza_simbolos_prohibidos(self):
        """Los endpoints de usuario rechazan caracteres prohibidos en nombre, correo, usuario o password."""
        self._autenticar(self.admin)

        simbolos_muestra = ['#', '$', '%', '!', '/', '&', ';', "'", '"', '--', '/*']
        for s in simbolos_muestra:
            res_admin = self.client.post('/administrador/guardar-usuario/', {
                'nombre': f'Juan{s}Perez',
                'correo': 'juan@safari.cl',
                'username': 'juanp',
                'password': 'password123',
                'rol': 'cajero'
            })
            self.assertEqual(res_admin.status_code, 400, f"admin_guardar_usuario debió rechazar símbolo: {s}")

            res_mant = self.client.post('/mantenedores/usuarios/guardar/', {
                'nombre': 'Juan Perez',
                'correo': f'juan{s}@safari.cl',
                'username': 'juanp',
                'password': 'password123',
                'rol': 'cajero'
            })
            self.assertEqual(res_mant.status_code, 400, f"mantenedor_usuario_guardar debió rechazar símbolo: {s}")

    def test_admin_y_mantenedores_guardar_producto_rechaza_simbolos_prohibidos(self):
        """Los endpoints de producto rechazan caracteres prohibidos en nombre o descripción con HTTP 400."""
        self._autenticar(self.admin)

        simbolos_muestra = ['#', '$', '%', '!', '/', '&', '(', ')', '=', ':', ';', "'", '"', '--', '/*']
        for s in simbolos_muestra:
            res_admin = self.client.post('/stock/guardar/', {
                'nombre': f'Hamburguesa{s}Especial',
                'precio': '8990',
                'stock': '20'
            })
            self.assertEqual(res_admin.status_code, 400, f"stock/guardar debió rechazar símbolo: {s}")

            res_mant = self.client.post('/mantenedores/productos/guardar/', {
                'nombre': 'Hamburguesa Normal',
                'descripcion': f'Descripción con{s}malicioso',
                'precio': '8990',
                'stock': '20'
            })
            self.assertEqual(res_mant.status_code, 400, f"mantenedor_producto_guardar debió rechazar símbolo: {s}")

    def test_mesero_y_cajero_pedidos_rechazan_notas_con_simbolos_prohibidos(self):
        """Las comandas y pedidos rechazan notas con símbolos prohibidos (#, $, %, !, /, &, =, :, ;, ', ", --, /*)."""
        self._autenticar(self.mesero)

        simbolos_muestra = ['#', '$', '%', '!', '/', '&', '=', ':', ';', "'", '"', '--', '/*']
        for s in simbolos_muestra:
            res_mesero = self.client.post(
                '/mesero/tomar-pedido/',
                data=json.dumps({
                    'mesa_id': self.mesa.id,
                    'notas': f'Cliente solicita cambio{s}sin sal',
                    'items': [{'id': self.producto.id, 'cantidad': 1}]
                }),
                content_type='application/json'
            )
            self.assertEqual(res_mesero.status_code, 400, f"mesero_tomar_pedido debió rechazar símbolo: {s}")

    def test_busquedas_get_en_stock_ventas_y_auditoria_rechazan_simbolos_prohibidos(self):
        """Las búsquedas GET en stock, ventas y auditoría rechazan parámetros con símbolos prohibidos."""
        self._autenticar(self.admin)

        simbolos_muestra = ['#', '$', '%', '!', '/', '&', ';', "'", '"', '--', '/*']
        for s in simbolos_muestra:
            res_stock = self.client.get('/stock/', {'q': f'hamburguesa{s}'})
            self.assertEqual(res_stock.status_code, 400, f"stock_view debió rechazar búsqueda con {s}")

            res_auditoria = self.client.get('/mantenedores/auditoria/', {'q': f'filtro{s}'})
            self.assertEqual(res_auditoria.status_code, 400, f"auditoria_view debió rechazar búsqueda con {s}")

    def test_todas_las_plantillas_cargan_script_validaciones_js(self):
        """Verifica que el script validaciones.js se cargue en todas las vistas principales."""
        # 1. Login
        res_login = self.client.get('/login/')
        self.assertContains(res_login, 'validaciones.js')

        # 2. Administrador
        self._autenticar(self.admin)
        res_admin = self.client.get('/administrador/')
        self.assertContains(res_admin, 'validaciones.js')

        # 3. Cajero
        self._autenticar(self.cajero)
        res_cajero = self.client.get('/cajero/')
        self.assertContains(res_cajero, 'validaciones.js')

        # 4. Cocinero
        self._autenticar(self.cocinero)
        res_cocina = self.client.get('/cocinero/')
        self.assertContains(res_cocina, 'validaciones.js')

        # 5. Mesero
        self._autenticar(self.mesero)
        res_mesero = self.client.get('/mesero/')
        self.assertContains(res_mesero, 'validaciones.js')

        # 6. Stock
        self._autenticar(self.admin)
        res_stock = self.client.get('/stock/')
        self.assertContains(res_stock, 'validaciones.js')

        # 7. Ventas
        res_ventas = self.client.get('/ventas/')
        self.assertContains(res_ventas, 'validaciones.js')

        # 8. Mantenedores Hub
        res_mant = self.client.get('/mantenedores/')
        self.assertContains(res_mant, 'validaciones.js')

    def test_confirmacion_100_por_ciento_consultas_orm_parametrizado(self):
        """Audita el código fuente de views para confirmar 100% uso de ORM parametrizado sin SQL en crudo."""
        import os
        ruta_pkg = os.path.join(os.path.dirname(__file__), 'views')
        ruta_views = os.path.join(os.path.dirname(__file__), 'views.py')
        if os.path.isdir(ruta_pkg):
            contenido = ""
            for root, _, files in sorted(os.walk(ruta_pkg)):
                for file in sorted(files):
                    if file.endswith('.py'):
                        with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                            contenido += f.read() + "\n"
        else:
            with open(ruta_views, 'r', encoding='utf-8') as f:
                contenido = f.read()

        # Prohibición de raw SQL y formateo inseguro en líneas de código ejecutables
        lineas_codigo = [l.strip() for l in contenido.splitlines() if l.strip() and not l.strip().startswith('#')]
        for l in lineas_codigo:
            self.assertNotIn("cursor.execute", l)
            self.assertNotIn(".raw(", l)
            self.assertNotIn(".extra(", l)

        self.assertIn("objects.filter(", contenido)
        self.assertTrue("objects.filter(" in contenido or "objects.get(" in contenido)


class RedisenioCocinaTabsTestCase(TestCase):
    """
    Pruebas para el rediseño de interfaz del Monitor de Cocina con pestañas estilo navegador Chrome:
    - 5 secciones de pestañas: En Espera, Preparación, Listo, Entregado, Re-Cocinando.
    - Contenedores de comandas individuales por estado con contadores numéricos.
    - Estilos distintivos de alerta para la pestaña Re-Cocinando (prioridad operativa).
    - Botones de acción ('Iniciar Preparación', 'Marcar Listo', 'Entregar', y 'Re-hacer').
    - Enlace de archivos modulares cocina.css y cocina_tabs.js bajo estándares de seguridad CSP.
    """

    def setUp(self):
        self.cocinero = Usuario.objects.create(
            nombre="Chef Safari",
            correo="chef@safari.cl",
            username="chef_safari",
            password="password123",
            rol="cocinero",
            estado="activo"
        )
        self.mesa = Mesa.objects.create(numero=12, nombre="Mesa Terraza 12", estado="ocupada")

        # Comanda 1: En Espera
        self.comanda_espera = Comanda.objects.create(
            folio="COM-101",
            mesa="Mesa 12",
            items="1x Lomo Saltado ($9500)",
            total=Decimal("9500.00"),
            estado="en_espera",
            tipo_pedido="mesa"
        )
        # Comanda 2: Preparación
        self.comanda_prep = Comanda.objects.create(
            folio="COM-102",
            mesa="Mesa 12",
            items="1x Hamburguesa Clásica ($6500)",
            total=Decimal("6500.00"),
            estado="preparacion",
            tipo_pedido="mesa"
        )
        # Comanda 3: Listo
        self.comanda_listo = Comanda.objects.create(
            folio="COM-103",
            mesa="Mesa 12",
            items="2x Jugo Natural ($5000)",
            total=Decimal("5000.00"),
            estado="listo",
            tipo_pedido="mesa"
        )
        # Comanda 4: Entregado
        self.comanda_entregado = Comanda.objects.create(
            folio="COM-104",
            mesa="Mesa 12",
            items="1x Ensalada César ($4500)",
            total=Decimal("4500.00"),
            estado="entregado",
            tipo_pedido="mesa"
        )
        # Comanda 5: Re-Cocinando (Re-orden)
        self.comanda_reorden = Comanda.objects.create(
            folio="COM-105",
            mesa="Mesa 12",
            items="1x Bife de Chorizo ($12000)",
            total=Decimal("12000.00"),
            estado="RE_ORDEN",
            es_reemision=True,
            motivo_reemision="Cliente solicita cambio de término a punto medio",
            tipo_pedido="mesa"
        )

    def _autenticar_cocinero(self):
        session = self.client.session
        session['usuario'] = {
            'id': self.cocinero.id,
            'nombre': self.cocinero.nombre,
            'username': self.cocinero.username,
            'rol': self.cocinero.rol,
        }
        session.save()

    def test_renderizado_exacto_de_las_5_pestanas_chrome(self):
        """Verifica que cocinero.html renderice la barra superior con las 5 pestañas Chrome y sus contadores."""
        self._autenticar_cocinero()
        res = self.client.get('/cocinero/')
        self.assertEqual(res.status_code, 200)

        # 1. Verificar las 5 pestañas en la barra superior
        self.assertContains(res, 'data-tab-target="en_espera"')
        self.assertContains(res, 'data-tab-target="preparacion"')
        self.assertContains(res, 'data-tab-target="listo"')
        self.assertContains(res, 'data-tab-target="entregado"')
        self.assertContains(res, 'data-tab-target="recocinando"')

        # 2. Textos visibles de las pestañas
        self.assertContains(res, 'En Espera')
        self.assertContains(res, 'Preparación')
        self.assertContains(res, 'Listo')
        self.assertContains(res, 'Entregado')
        self.assertContains(res, 'Re-Cocinando')

        # 3. Contadores numéricos
        self.assertContains(res, 'id="tab-counter-en_espera"')
        self.assertContains(res, 'id="tab-counter-preparacion"')
        self.assertContains(res, 'id="tab-counter-listo"')
        self.assertContains(res, 'id="tab-counter-entregado"')
        self.assertContains(res, 'id="tab-counter-recocinando"')

    def test_renderizado_de_los_5_paneles_de_contenido_por_estado(self):
        """Verifica que existan los 5 contenedores independientes de comandas."""
        self._autenticar_cocinero()
        res = self.client.get('/cocinero/')
        self.assertEqual(res.status_code, 200)

        self.assertContains(res, 'id="pane-en_espera"')
        self.assertContains(res, 'id="pane-preparacion"')
        self.assertContains(res, 'id="pane-listo"')
        self.assertContains(res, 'id="pane-entregado"')
        self.assertContains(res, 'id="pane-recocinando"')

    def test_pestana_recocinando_posee_estilos_y_etiquetas_distintivas(self):
        """Verifica el estilo distintivo ámbar/naranja de la pestaña y tarjetas Re-Cocinando."""
        self._autenticar_cocinero()
        res = self.client.get('/cocinero/')
        self.assertEqual(res.status_code, 200)

        self.assertContains(res, 'chrome-tab-recocinando')
        self.assertContains(res, 'card-reorden')
        self.assertContains(res, 'badge-reorden')
        self.assertContains(res, 'reorden-motivo')
        self.assertContains(res, 'Cliente solicita cambio de término a punto medio')

    def test_botones_de_transicion_de_estado_en_tarjetas(self):
        """Verifica los botones de transición: 'Iniciar Preparación', 'Marcar Listo', 'Entregar', y 'Re-hacer'."""
        self._autenticar_cocinero()
        res = self.client.get('/cocinero/')
        self.assertEqual(res.status_code, 200)

        # Botón Iniciar Preparación
        self.assertContains(res, 'Iniciar Preparación')
        self.assertContains(res, 'data-nuevo-estado="preparacion"')

        # Botón Marcar Listo
        self.assertContains(res, 'Marcar Listo')
        self.assertContains(res, 'data-nuevo-estado="listo"')

        # Botón Entregar
        self.assertContains(res, 'Entregar')
        self.assertContains(res, 'data-nuevo-estado="entregado"')

        # Botón Re-hacer en pestaña Entregado
        self.assertContains(res, 'Re-hacer / Re-orden')
        self.assertContains(res, 'data-action="abrir-modal-reorden"')

    def test_enlaces_modulares_css_y_js_en_cocinero_html(self):
        """Verifica que cocinero.html cargue cocina.css y cocina_tabs.js sin código inline."""
        self._autenticar_cocinero()
        res = self.client.get('/cocinero/')
        self.assertEqual(res.status_code, 200)

        self.assertContains(res, 'css/cocina.css')
        self.assertContains(res, 'js/cocina_tabs.js')
        self.assertContains(res, 'js/validaciones.js')


class GestionPedidosMeseroCajeroTest(TestCase):
    """
    Pruebas unitarias para la corrección de gestión de pedidos entre Mesero y Cajero:
    1. Aislamiento estricto por Mesa (mesa_id y mesa_rel sin mezclar ítems ni con barra).
    2. Soporte de filtrado estricto con .filter(mesa_id=mesa.id, pagada=False).
    3. Botón 'Finalizar Venta / Solicitar Cuenta' en Mesero (transición a LISTO_PARA_COBRO).
    4. Bloqueo de nuevos platos cuando la mesa está en estado LISTO_PARA_COBRO.
    5. Liquidación en Caja de la mesa en LISTO_PARA_COBRO y liberación a 'desocupada'.
    6. Separación visual en Cajero entre Ventas en Barra y Cuentas por Mesa.
    """

    def setUp(self):
        self.password = 'Pass1234'
        self.mesero = Usuario.objects.create(
            nombre="Mesero Carlos",
            correo="carlos@safari.cl",
            username="mesero_carlos",
            password=self.password,
            rol="mesero"
        )
        self.cajero = Usuario.objects.create(
            nombre="Cajero Laura",
            correo="laura@safari.cl",
            username="cajero_laura",
            password=self.password,
            rol="cajero"
        )
        self.cocinero = Usuario.objects.create(
            nombre="Cocinero Pedro",
            correo="pedro@safari.cl",
            username="cocinero_pedro",
            password=self.password,
            rol="cocinero"
        )

        self.punto_venta = PuntoDeVenta.objects.create(nombre="Caja Principal")
        self.caja = ControlCaja.objects.create(
            cajero_responsable=self.cajero,
            usuario=self.cajero,
            punto_de_venta=self.punto_venta,
            punto_venta=self.punto_venta,
            monto_inicial=Decimal("50000.00"),
            abierta=True,
            estado='ABIERTA'
        )

        self.mesa1 = Mesa.objects.create(numero=1, nombre="Mesa 1", capacidad=4, estado='desocupada')
        self.mesa2 = Mesa.objects.create(numero=2, nombre="Mesa 2", capacidad=4, estado='desocupada')

        self.prod_carne = Producto.objects.create(nombre="Lomo Liso", precio=Decimal("12000.00"), stock=30)
        self.prod_jugo = Producto.objects.create(nombre="Jugo Natural", precio=Decimal("3500.00"), stock=50)

    def _autenticar(self, usuario):
        session = self.client.session
        session['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'username': usuario.username,
            'correo': usuario.correo,
            'rol': usuario.rol
        }
        session.save()

    def test_aislamiento_estricto_por_mesa_no_mezcla_items(self):
        """Verifica que cada mesa mantenga sus ítems aislados sin mezclar con otra mesa ni con barra."""
        self._autenticar(self.mesero)

        # Pedido Mesa 1: 2 Lomo Liso
        res1 = self.client.post('/mesero/tomar-pedido/', data=json.dumps({
            'mesa_id': self.mesa1.id,
            'notas': 'Mesa 1 bien cocido',
            'items': [{'id': self.prod_carne.id, 'cantidad': 2}]
        }), content_type='application/json')
        self.assertEqual(res1.status_code, 200)

        # Pedido Mesa 2: 3 Jugo Natural
        res2 = self.client.post('/mesero/tomar-pedido/', data=json.dumps({
            'mesa_id': self.mesa2.id,
            'notas': 'Mesa 2 con hielo',
            'items': [{'id': self.prod_jugo.id, 'cantidad': 3}]
        }), content_type='application/json')
        self.assertEqual(res2.status_code, 200)

        # Venta Inmediata en Barra Cajero: 1 Lomo Liso
        self._autenticar(self.cajero)
        res_barra = self.client.post('/cajero/registrar-venta/', data=json.dumps({
            'tipo_venta': 'barra',
            'mesa': 'Barra Principal',
            'metodo_pago': 'efectivo',
            'items': [{'id': self.prod_carne.id, 'cantidad': 1}]
        }), content_type='application/json')
        self.assertEqual(res_barra.status_code, 200)

        # Filtrar con .filter(mesa_id=mesa.id, pagada=False)
        cmd_mesa1 = Comanda.objects.filter(mesa_id=self.mesa1.id, pagada=False)
        self.assertEqual(cmd_mesa1.count(), 1)
        comanda1 = cmd_mesa1.first()
        self.assertEqual(comanda1.mesa_rel, self.mesa1)
        self.assertEqual(comanda1.tipo_pedido, 'mesa')
        self.assertEqual(comanda1.total, Decimal("24000.00"))
        self.assertIn("Lomo Liso", comanda1.items)
        self.assertNotIn("Jugo", comanda1.items)

        cmd_mesa2 = Comanda.objects.filter(mesa_id=self.mesa2.id, pagada=False)
        self.assertEqual(cmd_mesa2.count(), 1)
        comanda2 = cmd_mesa2.first()
        self.assertEqual(comanda2.mesa_rel, self.mesa2)
        self.assertEqual(comanda2.tipo_pedido, 'mesa')
        self.assertEqual(comanda2.total, Decimal("10500.00"))
        self.assertIn("Jugo Natural", comanda2.items)
        self.assertNotIn("Lomo", comanda2.items)

        # Barra no debe tener mesa_rel
        comanda_barra = Comanda.objects.filter(tipo_pedido='barra').first()
        self.assertIsNotNone(comanda_barra)
        self.assertTrue(comanda_barra.pagada)

    def test_solicitar_cuenta_mesa_cambia_estado_a_listo_para_cobro(self):
        """Verifica que el botón de finalizar venta cambie la mesa y comanda a LISTO_PARA_COBRO."""
        self._autenticar(self.mesero)

        # Garzón toma pedido
        self.client.post('/mesero/tomar-pedido/', data=json.dumps({
            'mesa_id': self.mesa1.id,
            'items': [{'id': self.prod_carne.id, 'cantidad': 1}]
        }), content_type='application/json')

        self.mesa1.refresh_from_db()
        self.assertEqual(self.mesa1.estado, 'ocupada')

        # Mesero pulsa 'Finalizar Venta / Solicitar Cuenta'
        res_solicitar = self.client.post('/mesero/solicitar-cuenta/', data=json.dumps({
            'mesa_id': self.mesa1.id
        }), content_type='application/json')
        self.assertEqual(res_solicitar.status_code, 200)
        data = res_solicitar.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['mesa_estado'], 'LISTO_PARA_COBRO')

        # Verificar BD
        self.mesa1.refresh_from_db()
        self.assertEqual(self.mesa1.estado, 'LISTO_PARA_COBRO')

        comanda = Comanda.objects.filter(mesa_id=self.mesa1.id, pagada=False).first()
        self.assertEqual(comanda.estado, 'LISTO_PARA_COBRO')

        # Verificar bitácora de auditoría
        auditoria = HistorialAccion.objects.filter(modulo='Mesas', accion='ACTUALIZAR').first()
        self.assertIsNotNone(auditoria)
        self.assertIn('LISTO_PARA_COBRO', auditoria.detalle)

    def test_bloqueo_agregar_platos_si_mesa_en_listo_para_cobro(self):
        """Verifica que no se puedan agregar más platos por error si la mesa está en LISTO_PARA_COBRO."""
        self._autenticar(self.mesero)

        self.mesa1.estado = 'LISTO_PARA_COBRO'
        self.mesa1.save()

        res = self.client.post('/mesero/tomar-pedido/', data=json.dumps({
            'mesa_id': self.mesa1.id,
            'items': [{'id': self.prod_jugo.id, 'cantidad': 1}]
        }), content_type='application/json')

        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertFalse(data['success'])
        self.assertIn('LISTO_PARA_COBRO', data['error'])

    def test_cajero_mesa_cuenta_y_liquidacion_mesa_listo_para_cobro(self):
        """Verifica que el cajero cargue la mesa en LISTO_PARA_COBRO, liquide y desocupe la mesa."""
        # Garzón toma pedido y solicita cuenta
        self._autenticar(self.mesero)
        self.client.post('/mesero/tomar-pedido/', data=json.dumps({
            'mesa_id': self.mesa1.id,
            'items': [{'id': self.prod_carne.id, 'cantidad': 2}]
        }), content_type='application/json')
        self.client.post('/mesero/solicitar-cuenta/', data=json.dumps({
            'mesa_id': self.mesa1.id
        }), content_type='application/json')

        # Cajero consulta cuenta
        self._autenticar(self.cajero)
        res_cuenta = self.client.get(f'/cajero/mesa-cuenta/{self.mesa1.id}/')
        self.assertEqual(res_cuenta.status_code, 200)
        data_cuenta = res_cuenta.json()
        self.assertTrue(data_cuenta['success'])
        self.assertTrue(data_cuenta['listo_para_cobro'])
        self.assertEqual(data_cuenta['estado_mesa'], 'LISTO_PARA_COBRO')
        self.assertEqual(data_cuenta['total'], 24000.0)

        # Cajero liquida la mesa
        res_liq = self.client.post('/cajero/liquidar-mesa/', data=json.dumps({
            'mesa_id': self.mesa1.id,
            'metodo_pago': 'tarjeta'
        }), content_type='application/json')
        self.assertEqual(res_liq.status_code, 200)
        data_liq = res_liq.json()
        self.assertTrue(data_liq['success'])
        self.assertTrue(data_liq['folio'].startswith('BOL-'))

        # Mesa liberada
        self.mesa1.refresh_from_db()
        self.assertEqual(self.mesa1.estado, 'desocupada')

        # Comanda pagada
        comanda = Comanda.objects.filter(mesa_rel=self.mesa1).first()
        self.assertTrue(comanda.pagada)

    def test_solicitar_cuenta_requiere_post_y_permisos_mesero(self):
        """Verifica que /mesero/solicitar-cuenta/ exija POST y permisos correspondientes."""
        self._autenticar(self.mesero)

        # GET debe ser rechazado con 405
        res_get = self.client.get('/mesero/solicitar-cuenta/')
        self.assertEqual(res_get.status_code, 405)

        # Usuario sin rol adecuado (cocinero) debe ser rechazado con 403
        self._autenticar(self.cocinero)
        res_rol = self.client.post('/mesero/solicitar-cuenta/', data=json.dumps({
            'mesa_id': self.mesa1.id
        }), content_type='application/json')
        self.assertEqual(res_rol.status_code, 403)

    def test_separacion_visual_cajero_html(self):
        """Verifica que cajero.html renderice las secciones independientes para Barra y Mesas."""
        self._autenticar(self.cajero)
        res = self.client.get('/cajero/')
        self.assertEqual(res.status_code, 200)

        # Pestañas principales de navegación
        self.assertContains(res, 'id="pillsModalidadCajero"')
        self.assertContains(res, 'id="btnTabBarra"')
        self.assertContains(res, 'id="btnTabMesas"')
        self.assertContains(res, 'Ventas Directas en Barra (Inmediatas)')
        self.assertContains(res, 'Cuentas Pendientes por Mesa')

        # Contenedores visuales separados
        self.assertContains(res, 'id="contenedorSeccionBarra"')
        self.assertContains(res, 'id="contenedorSeccionMesas"')


# ==============================================================================
# SUITE DE PRUEBAS: LISTVIEW COMPACTO, BUSCADOR EN TIEMPO REAL Y BLOQUEO DE STOCK
# ==============================================================================

class PruebasListViewYBloqueoStockTestCase(TestCase):
    """
    Verifica las mejoras de usabilidad estilo ListView de Android y el bloqueo estricto de stock:
    1. Contenedores con altura fija y scroll interno (.listview-container).
    2. Buscador en tiempo real de productos por nombre o categoría y mesas pendientes.
    3. Bloqueo visual de productos agotados en mesero.html y cajero.html.
    4. Validación atómica en backend (views.py) de stock suficiente al tomar comanda, registrar venta y liquidar mesa.
    """

    def setUp(self):
        self.password = 'PassSegura123!'

        self.cajero = Usuario.objects.create(
            nombre='Cajero Test Stock',
            username='cajerostock',
            correo='cajerostock@safari.cl',
            password=self.password,
            rol='cajero'
        )
        self.mesero = Usuario.objects.create(
            nombre='Mesero Test Stock',
            username='meserostock',
            correo='meserostock@safari.cl',
            password=self.password,
            rol='mesero'
        )

        self.pdv = PuntoDeVenta.objects.create(nombre="Caja Principal Test", ubicacion="Barra")
        self.caja = ControlCaja.objects.create(
            usuario=self.cajero,
            punto_venta=self.pdv,
            monto_inicial=50000,
            estado='ABIERTA',
            abierta=True
        )

        self.menu_fondos, _ = Menu.objects.get_or_create(nombre='Fondos')
        self.prod_disponible = Producto.objects.create(
            codigo='PROD-DISP-01',
            nombre='Chorrillana Especial',
            descripcion='Papas fritas con carne y cebolla',
            precio=9500,
            stock=10,
            menu=self.menu_fondos
        )
        self.prod_escaso = Producto.objects.create(
            codigo='PROD-ESC-02',
            nombre='Pisco Sour Peruano',
            descripcion='Cóctel clásico',
            precio=4500,
            stock=2,
            menu=self.menu_fondos
        )
        self.prod_agotado = Producto.objects.create(
            codigo='PROD-AGOT-03',
            nombre='Cerveza Artesanal IPA',
            descripcion='Bebida sin stock',
            precio=3800,
            stock=0,
            menu=self.menu_fondos
        )

        self.mesa1 = Mesa.objects.create(
            nombre='Mesa 101',
            numero=101,
            capacidad=4,
            estado='desocupada'
        )

    def _autenticar(self, usuario):
        session = self.client.session
        session['usuario'] = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'username': usuario.username,
            'correo': usuario.correo,
            'rol': usuario.rol
        }
        session.save()

    def test_listview_container_renderizado_en_mesero_y_cajero(self):
        """Verifica que mesero.html y cajero.html rendericen contenedores con la clase .listview-container."""
        # En pantalla de Mesero
        self._autenticar(self.mesero)
        res_mesero = self.client.get('/mesero/')
        self.assertEqual(res_mesero.status_code, 200)
        self.assertContains(res_mesero, 'listview-container')
        self.assertContains(res_mesero, 'id="listaCatalogoPedido"')
        self.assertContains(res_mesero, 'id="filtroProductoPedido"')

        # En pantalla de Cajero
        self._autenticar(self.cajero)
        res_cajero = self.client.get('/cajero/')
        self.assertEqual(res_cajero.status_code, 200)
        self.assertContains(res_cajero, 'id="scrollContenedorProductos"')
        self.assertContains(res_cajero, 'id="contenedorCarrito"')
        self.assertContains(res_cajero, 'id="scrollGridMesasPendientes"')
        self.assertContains(res_cajero, 'id="contenedorItemsMesa"')
        self.assertContains(res_cajero, 'id="filtroBuscar"')
        self.assertContains(res_cajero, 'id="filtroMesasPendientes"')

    def test_productos_agotados_deshabilitados_en_templates(self):
        """Verifica que los productos sin stock (stock <= 0) se filtren o muestren deshabilitados."""
        # En pantalla de Mesero: la vista filtra stock__gt=0, no incluye productos agotados
        self._autenticar(self.mesero)
        res_mesero = self.client.get('/mesero/')
        self.assertEqual(res_mesero.status_code, 200)
        self.assertContains(res_mesero, self.prod_disponible.nombre)
        self.assertContains(res_mesero, self.prod_escaso.nombre)
        self.assertNotContains(res_mesero, self.prod_agotado.nombre)

        # En pantalla de Cajero: clase disabled-card y badge 'Agotado (0)' para productos con stock 0
        self._autenticar(self.cajero)
        res_cajero = self.client.get('/cajero/')
        self.assertEqual(res_cajero.status_code, 200)
        self.assertContains(res_cajero, 'disabled-card')
        self.assertContains(res_cajero, 'Agotado (0)')
        self.assertContains(res_cajero, f'data-categoria="{self.menu_fondos.nombre}"')
        self.assertContains(res_cajero, self.prod_agotado.nombre)

    def test_bloqueo_backend_stock_insuficiente_mesero_tomar_pedido(self):
        """Verifica que el mesero no pueda pedir una cantidad superior al stock disponible."""
        self._autenticar(self.mesero)

        # Pedir 5 unidades de un producto con stock 2
        payload = {
            'mesa_id': self.mesa1.id,
            'notas': 'Pedido excediendo stock',
            'items': [
                {'id': self.prod_escaso.id, 'cantidad': 5}
            ]
        }
        res = self.client.post('/mesero/tomar-pedido/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertIn('Stock insuficiente', data.get('error', ''))

        # Intentar pedir un producto con stock 0
        payload_agotado = {
            'mesa_id': self.mesa1.id,
            'notas': 'Pedido de agotado',
            'items': [
                {'id': self.prod_agotado.id, 'cantidad': 1}
            ]
        }
        res_agotado = self.client.post('/mesero/tomar-pedido/', data=json.dumps(payload_agotado), content_type='application/json')
        self.assertEqual(res_agotado.status_code, 400)
        data_agotado = res_agotado.json()
        self.assertIn('Stock insuficiente', data_agotado.get('error', ''))

        # Ninguna comanda debe haberse registrado
        self.assertEqual(Comanda.objects.filter(mesa_rel=self.mesa1).count(), 0)

    def test_bloqueo_backend_stock_insuficiente_cajero_venta_barra(self):
        """Verifica que el cajero no pueda registrar una venta en barra que exceda el stock real."""
        self._autenticar(self.cajero)

        payload = {
            'tipo_venta': 'barra',
            'metodo_pago': 'efectivo',
            'items': [
                {'id': self.prod_escaso.id, 'cantidad': 3}  # Stock es 2
            ]
        }
        res = self.client.post('/cajero/registrar-venta/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertIn('Stock insuficiente', data.get('error', ''))

        # Verificar que el stock no fue modificado
        self.prod_escaso.refresh_from_db()
        self.assertEqual(self.prod_escaso.stock, 2)
        self.assertEqual(Venta.objects.count(), 0)

    def test_bloqueo_backend_stock_insuficiente_cajero_liquidar_mesa(self):
        """Verifica que liquidar una mesa falle limpiamente si el stock del producto disminuyó antes de liquidar."""
        self._autenticar(self.mesero)

        # Mesero toma pedido válido con 2 unidades (stock actual: 2)
        payload = {
            'mesa_id': self.mesa1.id,
            'notas': 'Comanda normal',
            'items': [
                {'id': self.prod_escaso.id, 'cantidad': 2}
            ]
        }
        res_pedido = self.client.post('/mesero/tomar-pedido/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res_pedido.status_code, 200)

        # Simular que el stock bajó a 1 por otra venta simultánea antes de liquidar
        self.prod_escaso.stock = 1
        self.prod_escaso.save()

        # Cajero intenta liquidar la mesa
        self._autenticar(self.cajero)
        payload_liq = {
            'mesa_id': self.mesa1.id,
            'metodo_pago': 'tarjeta'
        }
        res_liq = self.client.post('/cajero/liquidar-mesa/', data=json.dumps(payload_liq), content_type='application/json')
        self.assertEqual(res_liq.status_code, 400)
        data_liq = res_liq.json()
        self.assertIn('Stock insuficiente para liquidar', data_liq.get('error', ''))

        # Mesa debe permanecer ocupada y la comanda no pagada
        self.mesa1.refresh_from_db()
        self.assertEqual(self.mesa1.estado, 'ocupada')
        comanda = Comanda.objects.filter(mesa_rel=self.mesa1).first()
        self.assertFalse(comanda.pagada)


# ==============================================================================
# SUITE DE PRUEBAS: BLINDAJE DE INICIO DE SESIÓN (LONGITUDES, GET VS POST Y TYPE=PASSWORD)
# ==============================================================================

class PruebasSeguridadLoginTestCase(TestCase):
    """
    Verifica las tres correcciones de seguridad en el módulo de Inicio de Sesión:
    1. Límites estrictos de longitud (usuario: 4-30, password: 6-25) y rechazo de espacios.
    2. Rechazo explícito de credenciales enviadas por GET con redirección limpia (prevención de exposición en URL).
    3. Protección del campo type="password" contra alteración en DevTools (MutationObserver) y forzado de POST.
    """

    def setUp(self):
        self.client = Client()
        self.password_valida = "clave123"  # 8 caracteres
        self.usuario = Usuario.objects.create(
            nombre="Usuario Test Seguridad",
            correo="seguro@safari.cl",
            username="user_seguro",  # 11 caracteres
            password=self.password_valida,
            rol="cajero"
        )

    def test_login_rechaza_usuario_menor_a_4_caracteres(self):
        """Rechaza usuario con menos de 4 caracteres."""
        res = self.client.post('/login/', {
            'username': 'abc',
            'password': self.password_valida
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'entre 4 y 30 caracteres')
        self.assertNotIn('usuario', self.client.session)

    def test_login_rechaza_usuario_mayor_a_30_caracteres(self):
        """Rechaza usuario con más de 30 caracteres."""
        res = self.client.post('/login/', {
            'username': 'a' * 31,
            'password': self.password_valida
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'entre 4 y 30 caracteres')
        self.assertNotIn('usuario', self.client.session)

    def test_login_rechaza_usuario_con_espacios(self):
        """Rechaza usuario que contenga espacios en blanco."""
        res = self.client.post('/login/', {
            'username': 'user test',
            'password': self.password_valida
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'espacios en blanco')
        self.assertNotIn('usuario', self.client.session)

    def test_login_rechaza_password_menor_a_6_caracteres(self):
        """Rechaza contraseña con menos de 6 caracteres."""
        res = self.client.post('/login/', {
            'username': 'user_seguro',
            'password': '12345'
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'entre 6 y 25 caracteres')
        self.assertNotIn('usuario', self.client.session)

    def test_login_rechaza_password_mayor_a_25_caracteres(self):
        """Rechaza contraseña con más de 25 caracteres."""
        res = self.client.post('/login/', {
            'username': 'user_seguro',
            'password': 'p' * 26
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'entre 6 y 25 caracteres')
        self.assertNotIn('usuario', self.client.session)

    def test_login_rechaza_password_con_espacios(self):
        """Rechaza contraseña que contenga espacios en blanco."""
        res = self.client.post('/login/', {
            'username': 'user_seguro',
            'password': 'pass word123'
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'espacios en blanco')
        self.assertNotIn('usuario', self.client.session)

    def test_login_rechaza_y_redirige_si_recibe_credenciales_por_get(self):
        """Rechaza explícitamente GET con credenciales y redirige limpio a /login/ sin procesar credenciales."""
        # Intento de enviar credenciales válidas por GET (ej: alteración method="GET" en DevTools)
        res = self.client.get('/login/', {
            'username': 'user_seguro',
            'password': self.password_valida
        })
        self.assertEqual(res.status_code, 302)
        self.assertRedirects(res, '/login/')
        self.assertNotIn('usuario', self.client.session)

        # GET con solo password en querystring
        res_pass = self.client.get('/login/', {'password': 'cualquier_clave'})
        self.assertEqual(res_pass.status_code, 302)
        self.assertRedirects(res_pass, '/login/')

        # GET con solo username en querystring
        res_user = self.client.get('/login/', {'username': 'user_seguro'})
        self.assertEqual(res_user.status_code, 302)
        self.assertRedirects(res_user, '/login/')

    def test_formulario_login_html_tiene_post_y_atributos_longitud(self):
        """Verifica que login.html declare method='POST', minlength y maxlength en los inputs."""
        res = self.client.get('/login/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'method="POST"')
        self.assertContains(res, 'id="formLogin"')
        self.assertContains(res, 'id="username"')
        self.assertContains(res, 'minlength="4"')
        self.assertContains(res, 'maxlength="30"')
        self.assertContains(res, 'id="password"')
        self.assertContains(res, 'minlength="6"')
        self.assertContains(res, 'maxlength="25"')
        self.assertContains(res, 'type="password"')

    def test_login_exitoso_dentro_de_los_limites(self):
        """Verifica que un usuario con longitud válida y sin espacios inicie sesión correctamente."""
        res = self.client.post('/login/', {
            'username': 'user_seguro',
            'password': self.password_valida
        })
        self.assertRedirects(res, '/cajero/')
        self.assertIn('usuario', self.client.session)
        self.assertEqual(self.client.session['usuario']['username'], 'user_seguro')
        self.assertEqual(self.client.session.get('usuario_id'), self.usuario.id)


class AdminMantenedoresSeguridadBackofficeTests(TestCase):
    """
    Pruebas defensivas para Backoffice de Administrador y Mantenedores:
    1. Prohibir auto-modificación y desactivación de la cuenta del Administrador en sesión.
    2. Ocultar / deshabilitar botones de 'Desactivar/Anular' y 'Editar Rol' en la plantilla para la cuenta en sesión.
    3. Validación estricta en backend que rechaza actualización o anulación de la cuenta en sesión con HTTP 400.
    4. Carga limpia de vistas de actualización en mantenedores con campos habilitados y token CSRF válido.
    5. Retorno limpio al listado del mantenedor tras modificar sin cerrar sesión del usuario ni congelar la pantalla.
    """

    def setUp(self):
        self.admin = Usuario.objects.create(
            rut="11.111.111-1",
            nombre="Administrador Sistema",
            username="admin_test",
            correo="admin_test@parquesafari.cl",
            password="AdminPassword123",
            rol="administrador",
            estado="activo"
        )
        self.otro_admin = Usuario.objects.create(
            rut="22.222.222-2",
            nombre="Segundo Administrador",
            username="admin_dos",
            correo="admin_dos@parquesafari.cl",
            password="AdminDosPassword123",
            rol="administrador",
            estado="activo"
        )
        self.cajero = Usuario.objects.create(
            rut="33.333.333-3",
            nombre="Cajero Normal",
            username="cajero_test",
            correo="cajero_test@parquesafari.cl",
            password="CajeroPassword123",
            rol="cajero",
            estado="activo"
        )
        self.menu = Menu.objects.create(
            nombre="Platos Principales",
            descripcion="Comidas de fondo",
            estado="activo"
        )
        self.mesa = Mesa.objects.create(
            numero=10,
            nombre="Mesa Terraza 10",
            capacidad=4,
            estado="disponible"
        )
        self.pdv = PuntoDeVenta.objects.create(
            nombre="Caja Principal",
            ubicacion="Acceso Central",
            estado="activo"
        )
        self.producto = Producto.objects.create(
            codigo="HAM-01",
            nombre="Hamburguesa Clásica",
            descripcion="Carne y queso",
            precio=Decimal("6500.00"),
            stock=20,
            menu=self.menu
        )

    def _autenticar_admin(self):
        session = self.client.session
        session['usuario'] = {
            'id': self.admin.id,
            'nombre': self.admin.nombre,
            'username': self.admin.username,
            'rol': self.admin.rol,
        }
        session['usuario_id'] = self.admin.id
        session.save()

    def test_admin_guardar_usuario_rechaza_auto_modificacion(self):
        """admin_guardar_usuario aborta si se intenta modificar al admin en sesión con HTTP 400 y mensaje exacto."""
        self._autenticar_admin()
        res = self.client.post('/administrador/guardar-usuario/', {
            'user_id': self.admin.id,
            'rut': self.admin.rut,
            'nombre': 'Admin Cambiado',
            'username': 'admin_test',
            'correo': 'admin_test@parquesafari.cl',
            'rol': 'administrador',
            'estado': 'inactivo'
        })
        self.assertEqual(res.status_code, 400)
        self.assertContains(res, 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión', status_code=400)

        # Confirmar que en la base de datos no se alteró
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.estado, 'activo')
        self.assertEqual(self.admin.nombre, 'Administrador Sistema')

    def test_admin_eliminar_usuario_rechaza_auto_eliminacion(self):
        """admin_eliminar_usuario aborta si el admin intenta eliminar su propia cuenta con HTTP 400."""
        self._autenticar_admin()
        res = self.client.get(f'/administrador/eliminar-usuario/{self.admin.id}/')
        self.assertEqual(res.status_code, 400)
        self.assertContains(res, 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión', status_code=400)
        self.assertTrue(Usuario.objects.filter(id=self.admin.id).exists())

    def test_mantenedor_usuario_guardar_rechaza_auto_modificacion(self):
        """mantenedor_usuario_guardar aborta si se intenta modificar la cuenta en sesión con HTTP 400."""
        self._autenticar_admin()
        res = self.client.post('/mantenedores/usuarios/guardar/', {
            'user_id': self.admin.id,
            'rut': self.admin.rut,
            'nombre': 'Admin Modificado',
            'username': 'admin_test',
            'correo': 'admin_test@parquesafari.cl',
            'rol': 'cajero',
            'estado': 'activo'
        })
        self.assertEqual(res.status_code, 400)
        self.assertContains(res, 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión', status_code=400)

        self.admin.refresh_from_db()
        self.assertEqual(self.admin.rol, 'administrador')

    def test_mantenedor_usuario_eliminar_rechaza_auto_eliminacion(self):
        """mantenedor_usuario_eliminar aborta si el admin intenta eliminar su propia cuenta con HTTP 400."""
        self._autenticar_admin()
        res = self.client.get(f'/mantenedores/usuarios/eliminar/{self.admin.id}/')
        self.assertEqual(res.status_code, 400)
        self.assertContains(res, 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión', status_code=400)
        self.assertTrue(Usuario.objects.filter(id=self.admin.id).exists())

    def test_mantenedor_usuario_actualizar_view_bloquea_cuenta_propia(self):
        """mantenedor_usuario_actualizar_view redirige al listado si se intenta abrir para la cuenta en sesión."""
        self._autenticar_admin()
        res = self.client.get(f'/mantenedores/usuarios/actualizar/{self.admin.id}/')
        self.assertEqual(res.status_code, 302)
        self.assertRedirects(res, '/mantenedores/usuarios/')

    def test_plantillas_deshabilitan_botones_desactivar_y_editar_rol_para_admin_en_sesion(self):
        """Verifica que tanto administrador.html como mantenedores/usuarios/listado.html deshabiliten botones para la cuenta en sesión."""
        self._autenticar_admin()

        # 1. En administrador.html
        res_admin = self.client.get('/administrador/')
        self.assertEqual(res_admin.status_code, 200)
        self.assertContains(res_admin, 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión')
        self.assertContains(res_admin, 'Editar Rol')
        self.assertContains(res_admin, 'Desactivar/Anular')

        # 2. En mantenedores/usuarios/listado.html
        res_mant = self.client.get('/mantenedores/usuarios/')
        self.assertEqual(res_mant.status_code, 200)
        self.assertContains(res_mant, 'No puedes desactivar ni modificar tu propia cuenta de administrador en sesión')

    def test_mantenedores_actualizar_vistas_cargan_habilitadas_con_csrf(self):
        """Verifica que las vistas de actualizar de todos los mantenedores carguen 200 con CSRF y campos habilitados."""
        self._autenticar_admin()

        rutas_actualizar = [
            f'/mantenedores/usuarios/actualizar/{self.cajero.id}/',
            f'/mantenedores/mesas/actualizar/{self.mesa.id}/',
            f'/mantenedores/puntos-de-venta/actualizar/{self.pdv.id}/',
            f'/mantenedores/menus/actualizar/{self.menu.id}/',
            f'/mantenedores/productos/actualizar/{self.producto.id}/',
        ]

        for ruta in rutas_actualizar:
            res = self.client.get(ruta)
            self.assertEqual(res.status_code, 200, f"Fallo al cargar {ruta}")
            self.assertContains(res, 'csrfmiddlewaretoken')
            self.assertContains(res, 'method="POST"')

    def test_mantenedores_modificar_retorna_limpio_y_conserva_sesion(self):
        """Verifica que modificar un registro retorne limpiamente al listado correspondiente y preserve la sesión del admin."""
        self._autenticar_admin()

        # 1. Modificar Usuario ajeno
        res_u = self.client.post('/mantenedores/usuarios/guardar/', {
            'user_id': self.cajero.id,
            'rut': self.cajero.rut,
            'nombre': 'Cajero Nombre Actualizado',
            'username': 'cajero_test',
            'correo': 'cajero_test@parquesafari.cl',
            'rol': 'cajero',
            'estado': 'activo'
        })
        self.assertEqual(res_u.status_code, 302)
        self.assertRedirects(res_u, '/mantenedores/usuarios/')
        self.assertIn('usuario', self.client.session)
        self.assertEqual(self.client.session['usuario']['username'], 'admin_test')

        # 2. Modificar Mesa
        res_m = self.client.post('/mantenedores/mesas/guardar/', {
            'mesa_id': self.mesa.id,
            'numero': 15,
            'nombre': 'Mesa Terraza Quince',
            'capacidad': 6,
            'estado': 'disponible'
        })
        self.assertEqual(res_m.status_code, 302)
        self.assertRedirects(res_m, '/mantenedores/mesas/')
        self.assertIn('usuario', self.client.session)

        # 3. Modificar Punto de Venta
        res_pdv = self.client.post('/mantenedores/puntos-de-venta/guardar/', {
            'pdv_id': self.pdv.id,
            'nombre': 'Caja Terraza Renombrada',
            'ubicacion': 'Sector Norte',
            'estado': 'activo'
        })
        self.assertEqual(res_pdv.status_code, 302)
        self.assertRedirects(res_pdv, '/mantenedores/puntos-de-venta/')
        self.assertIn('usuario', self.client.session)

        # 4. Modificar Menú
        res_mn = self.client.post('/mantenedores/menus/guardar/', {
            'menu_id': self.menu.id,
            'nombre': 'Platos Gourmet',
            'descripcion': 'Nuevos platos de cocina',
            'estado': 'activo'
        })
        self.assertEqual(res_mn.status_code, 302)
        self.assertRedirects(res_mn, '/mantenedores/menus/')
        self.assertIn('usuario', self.client.session)

        # 5. Modificar Producto
        res_p = self.client.post('/mantenedores/productos/guardar/', {
            'prod_id': self.producto.id,
            'codigo': 'HAM-01-REV',
            'nombre': 'Hamburguesa Suprema',
            'descripcion': 'Carne Angus y salsa especial',
            'precio': 7990,
            'stock': 35,
            'menu_id': self.menu.id
        })
        self.assertEqual(res_p.status_code, 302)
        self.assertRedirects(res_p, '/mantenedores/productos/')
        self.assertIn('usuario', self.client.session)
        self.assertEqual(self.client.session['usuario']['username'], 'admin_test')


class CocineroPersistenciaPestanaYRedireccionTestCase(TestCase):
    """
    Pruebas unitarias para el módulo de Cocinero:
    - Redirección en views.py al cambiar estado de una comanda (return redirect('cocinero')).
    - Persistencia de pestaña activa en sesión (tab_cocina_activa).
    - Botón 'Preparar pedido' / 'Iniciar Preparación'.
    - Uso de sessionStorage en cocina_tabs.js.
    """

    def setUp(self):
        self.password = 'Pass1234'
        self.cocinero = Usuario.objects.create(
            nombre="Cocinero Test",
            username="cocinero_pestanas",
            password=self.password,
            rol="cocinero",
            estado="activo"
        )
        self.mesa = Mesa.objects.create(
            numero=101,
            nombre="Mesa Cocina 101",
            capacidad=4,
            estado="ocupada"
        )
        self.comanda = Comanda.objects.create(
            folio="CMD-TEST-TAB-01",
            mesa="Mesa Cocina 101",
            mesa_rel=self.mesa,
            items="2x Lomito Italiano",
            estado="en_espera",
            total=12000
        )

    def _autenticar_cocinero(self):
        s = self.client.session
        s['usuario'] = {
            'id': self.cocinero.id,
            'nombre': self.cocinero.nombre,
            'username': self.cocinero.username,
            'rol': self.cocinero.rol
        }
        s['usuario_id'] = self.cocinero.id
        s['rol'] = self.cocinero.rol
        s.save()

    def test_cambio_estado_form_post_redirecciona_a_cocinero_con_persistencia_tab(self):
        """Petición POST de formulario tradicional redirige limpiamente a 'cocinero' y preserva tab."""
        self._autenticar_cocinero()
        res = self.client.post('/cocina/cambiar-estado/', {
            'comanda_id': self.comanda.id,
            'nuevo_estado': 'preparacion',
            'tab_activa': 'en_espera'
        })
        self.assertEqual(res.status_code, 302)
        self.assertRedirects(res, reverse('cocinero'))

        self.comanda.refresh_from_db()
        self.assertEqual(self.comanda.estado, 'preparacion')
        self.assertEqual(self.client.session.get('tab_cocina_activa'), 'en_espera')

    def test_cambio_estado_json_retorna_200_con_tab_activa_y_redirect_url(self):
        """Petición JSON (AJAX/Fetch) retorna 200, tab_activa y redirect_url a 'cocinero'."""
        self._autenticar_cocinero()
        res = self.client.post(
            '/cocina/cambiar-estado/',
            data=json.dumps({
                'comanda_id': self.comanda.id,
                'nuevo_estado': 'listo',
                'tab_activa': 'preparacion'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['nuevo_estado'], 'listo')
        self.assertEqual(data['tab_activa'], 'preparacion')
        self.assertEqual(data['redirect_url'], reverse('cocinero'))
        self.assertEqual(self.client.session.get('tab_cocina_activa'), 'preparacion')

    def test_cocinero_view_restaura_tab_activa_desde_sesion(self):
        """Al renderizar la vista de cocinero, restaura la pestaña activa desde la sesión."""
        self._autenticar_cocinero()
        s = self.client.session
        s['tab_cocina_activa'] = 'preparacion'
        s.save()

        res = self.client.get('/cocinero/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['tab_activa'], 'preparacion')
        # Verificar que el botón de tab preparacion esté marcado activo en el HTML
        self.assertContains(res, 'data-tab-target="preparacion" role="tab" aria-selected="true"')

    def test_boton_preparar_pedido_presente_en_pantalla_cocina(self):
        """Verifica que el botón contenga 'Preparar pedido' e 'Iniciar Preparación'."""
        self._autenticar_cocinero()
        res = self.client.get('/cocinero/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Preparar pedido')
        self.assertContains(res, 'Iniciar Preparación')
        self.assertContains(res, 'data-nuevo-estado="preparacion"')

    def test_script_cocina_tabs_usa_session_storage(self):
        """Verifica que cocina_tabs.js guarde la pestaña activa con sessionStorage.setItem('tab_cocina_activa'."""
        js_path = os.path.join(settings.BASE_DIR, 'Safari', 'static', 'js', 'cocina_tabs.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            contenido = f.read()

        self.assertIn("sessionStorage.setItem('tab_cocina_activa'", contenido)
        self.assertIn("sessionStorage.getItem('tab_cocina_activa'", contenido)


# ==============================================================================
# SUITE DE PRUEBAS: CONTROL DE STOCK, TRANSACCIONES ATÓMICAS Y LÍMITES NUMÉRICOS
# ==============================================================================

class PruebasControlStockYLimitesNumericosTestCase(TestCase):
    """
    Verifica las validaciones de límites numéricos, atomicidad con select_for_update()
    y consistencia de inventario en ventas, pedidos y mantenedores:
    - Precios enteros positivos en CLP entre 100 y 9.999.999.
    - Stock entero entre 0 y 99.999 unidades.
    - Límite máximo de 50 unidades por línea de pedido (o stock disponible si es menor).
    - Bloqueo de 0, negativos y desbordamientos.
    - Descuento de inventario una sola vez por flujo y restitución de stock al anular.
    """

    def setUp(self):
        self.client = Client()
        self.admin = Usuario.objects.create(
            nombre="Admin Stock Test",
            correo="adminstock@safari.cl",
            username="adminstock",
            password="password123",
            rol="administrador",
            estado="activo"
        )
        self.cajero = Usuario.objects.create(
            nombre="Cajero Stock Test",
            correo="cajerostock@safari.cl",
            username="cajerostock",
            password="password123",
            rol="cajero",
            estado="activo"
        )
        self.mesero = Usuario.objects.create(
            nombre="Mesero Stock Test",
            correo="meserostock@safari.cl",
            username="meserostock",
            password="password123",
            rol="mesero",
            estado="activo"
        )
        self.caja_abierta = ControlCaja.objects.create(
            cajero_responsable=self.cajero,
            monto_inicial=Decimal("50000.00"),
            abierta=True,
            estado='ABIERTA'
        )
        self.mesa = Mesa.objects.create(numero=1, nombre="Mesa 1", capacidad=4, estado="desocupada")
        self.producto = Producto.objects.create(
            nombre="Plato Prueba Stock",
            descripcion="Plato de prueba para límites",
            precio=Decimal("5000.00"),
            stock=40
        )

    def _autenticar(self, usuario):
        s = self.client.session
        s['usuario_id'] = usuario.id
        s['usuario'] = {'id': usuario.id, 'nombre': usuario.nombre, 'rol': usuario.rol}
        s['rol'] = usuario.rol
        s.save()

    def test_limites_precio_y_stock_mantenedor_productos(self):
        """Verifica que el precio esté entre 100 y 9.999.999 CLP y stock entre 0 y 99.999."""
        self._autenticar(self.admin)

        # Precio inferior a 100 CLP debe ser rechazado con 400
        res_bajo = self.client.post('/stock/guardar/', {
            'nombre': 'Producto Precio Bajo',
            'descripcion': 'Test',
            'precio': '99',
            'stock': '10'
        })
        self.assertEqual(res_bajo.status_code, 400)

        # Precio superior a 9.999.999 CLP debe ser rechazado con 400
        res_alto = self.client.post('/stock/guardar/', {
            'nombre': 'Producto Precio Excesivo',
            'descripcion': 'Test',
            'precio': '10000000',
            'stock': '10'
        })
        self.assertEqual(res_alto.status_code, 400)

        # Stock superior a 99.999 unidades debe ser rechazado con 400
        res_stock_excesivo = self.client.post('/stock/guardar/', {
            'nombre': 'Producto Stock Excesivo',
            'descripcion': 'Test',
            'precio': '2500',
            'stock': '100000'
        })
        self.assertEqual(res_stock_excesivo.status_code, 400)

        # Valores válidos dentro del rango deben guardarse correctamente
        res_valido = self.client.post('/stock/guardar/', {
            'nombre': 'Producto Rango Valido',
            'descripcion': 'Test',
            'precio': '4990',
            'stock': '500'
        })
        self.assertEqual(res_valido.status_code, 302)
        prod = Producto.objects.filter(nombre='Producto Rango Valido').first()
        self.assertIsNotNone(prod)
        self.assertEqual(prod.precio, 4990)
        self.assertEqual(prod.stock, 500)

    def test_limite_maximo_50_unidades_por_linea_de_pedido(self):
        """Verifica que no se permitan pedidos que superen 50 unidades por ítem."""
        self._autenticar(self.mesero)
        # Producto con stock abundante
        self.producto.stock = 100
        self.producto.save()

        # Mesero intenta pedir 51 unidades
        payload = {
            'mesa_id': self.mesa.id,
            'items': [{'id': self.producto.id, 'cantidad': 51}]
        }
        res = self.client.post('/mesero/tomar-pedido/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertIn('máxima permitida por producto es de 50', data.get('error', ''))

        # Venta en caja intentando vender 51 unidades
        self._autenticar(self.cajero)
        payload_caja = {
            'tipo_venta': 'barra',
            'metodo_pago': 'efectivo',
            'items': [{'id': self.producto.id, 'cantidad': 51}]
        }
        res_caja = self.client.post('/cajero/registrar-venta/', data=json.dumps(payload_caja), content_type='application/json')
        self.assertEqual(res_caja.status_code, 400)
        self.assertIn('máxima permitida por producto es de 50', res_caja.json().get('error', ''))

    def test_bloqueo_cantidades_cero_y_negativas_venta(self):
        """Verifica que se rechacen valores 0, negativos o no numéricos en cantidades."""
        self._autenticar(self.cajero)
        casos_invalidos = [0, -1, -10, "0", "-5", "abc", 2.5]
        for c in casos_invalidos:
            payload = {
                'tipo_venta': 'barra',
                'metodo_pago': 'efectivo',
                'items': [{'id': self.producto.id, 'cantidad': c}]
            }
            res = self.client.post('/cajero/registrar-venta/', data=json.dumps(payload), content_type='application/json')
            self.assertEqual(res.status_code, 400, f"Debió rechazar cantidad inválida: {c}")

    def test_restitucion_de_stock_al_anular_venta(self):
        """Verifica que anular una venta restituya exactamente el stock de los productos."""
        self._autenticar(self.cajero)
        stock_inicial = self.producto.stock  # 40

        # Registrar venta de 5 unidades en barra
        payload_venta = {
            'tipo_venta': 'barra',
            'metodo_pago': 'efectivo',
            'items': [{'id': self.producto.id, 'cantidad': 5}]
        }
        res_venta = self.client.post('/cajero/registrar-venta/', data=json.dumps(payload_venta), content_type='application/json')
        self.assertEqual(res_venta.status_code, 200)

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, stock_inicial - 5)  # 35

        # Obtener la venta creada
        venta = Venta.objects.latest('id')

        # Anular la venta
        res_anular = self.client.post('/cajero/anular-venta/', data=json.dumps({'venta_id': venta.id}), content_type='application/json')
        self.assertEqual(res_anular.status_code, 200)

        # Stock debe haberse restaurado a 40
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, stock_inicial)

    def test_admin_agregar_stock_limites(self):
        """Verifica que admin_agregar_stock valide límites coherentes (máx 99.999)."""
        self._autenticar(self.admin)

        # Reposición válida de 15 unidades
        stock_prev = self.producto.stock
        res_ok = self.client.post('/stock/agregar/', data=json.dumps({
            'producto_id': self.producto.id,
            'cantidad_agregar': 15
        }), content_type='application/json')
        self.assertEqual(res_ok.status_code, 200)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, stock_prev + 15)

        # Intento de agregar cantidad negativa
        res_neg = self.client.post('/stock/agregar/', data=json.dumps({
            'producto_id': self.producto.id,
            'cantidad_agregar': -5
        }), content_type='application/json')
        self.assertEqual(res_neg.status_code, 400)

        # Intento de desbordar el stock más allá de 99.999
        res_over = self.client.post('/stock/agregar/', data=json.dumps({
            'producto_id': self.producto.id,
            'cantidad_agregar': 100000
        }), content_type='application/json')
        self.assertEqual(res_over.status_code, 400)


# ==============================================================================
# SUITE DE PRUEBAS: ASIGNACIÓN DE MESAS DISPONIBLES EN TERMINAL DE CAJA
# ==============================================================================

class AsignacionMesaCajeroTestCase(TestCase):
    """
    Verifica la asignación de mesas disponibles al registrar una venta o pedido en caja:
    - Contexto de cajero.html incluye 'mesas_disponibles' y 'mesas_disponibles_json'.
    - Endpoint api_mesas_disponibles retorna únicamente mesas con estado 'disponible'.
    - Registro de venta en caja con mesa asignada ocupa la mesa de forma atómica y vincula Venta y Comanda.
    - Bloqueo de asignación si la mesa ya no está disponible (estado != 'disponible').
    - Venta en mostrador / para llevar sin mesa funciona sin alterar estado de mesas.
    """

    def setUp(self):
        self.client = Client()
        self.cajero = Usuario.objects.create(
            nombre="Cajero Mesas Test",
            correo="cajeromesas@safari.cl",
            username="cajeromesas",
            password="password123",
            rol="cajero",
            estado="activo"
        )
        self.caja_abierta = ControlCaja.objects.create(
            cajero_responsable=self.cajero,
            monto_inicial=Decimal("50000.00"),
            abierta=True,
            estado='ABIERTA'
        )
        self.mesa_disp1 = Mesa.objects.create(numero=10, nombre="Mesa 10", capacidad=4, estado="disponible")
        self.mesa_disp2 = Mesa.objects.create(numero=11, nombre="Mesa 11", capacidad=2, estado="disponible")
        self.mesa_ocupada = Mesa.objects.create(numero=12, nombre="Mesa 12", capacidad=6, estado="ocupada")
        self.producto = Producto.objects.create(
            nombre="Hamburguesa Safari",
            descripcion="Hamburguesa artesanal",
            precio=Decimal("6500.00"),
            stock=25
        )

    def _autenticar(self, usuario):
        s = self.client.session
        s['usuario_id'] = usuario.id
        s['usuario'] = {'id': usuario.id, 'nombre': usuario.nombre, 'rol': usuario.rol}
        s['rol'] = usuario.rol
        s.save()

    def test_cajero_view_contexto_mesas_disponibles(self):
        """Verifica que la vista cajero_view incluya mesas disponibles en el contexto."""
        self._autenticar(self.cajero)
        res = self.client.get('/cajero/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('mesas_disponibles', res.context)
        self.assertIn('mesas_disponibles_json', res.context)

        mesas_ctx = res.context['mesas_disponibles']
        mesas_ids = [m.id for m in mesas_ctx]
        self.assertIn(self.mesa_disp1.id, mesas_ids)
        self.assertIn(self.mesa_disp2.id, mesas_ids)
        self.assertNotIn(self.mesa_ocupada.id, mesas_ids)

    def test_api_mesas_disponibles_endpoint(self):
        """Verifica que /api/mesas-disponibles/ retorne en JSON solo las mesas disponibles."""
        self._autenticar(self.cajero)
        res = self.client.get('/api/mesas-disponibles/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))
        mesas_ids = [m['id'] for m in data.get('mesas_disponibles', [])]
        self.assertIn(self.mesa_disp1.id, mesas_ids)
        self.assertIn(self.mesa_disp2.id, mesas_ids)
        self.assertNotIn(self.mesa_ocupada.id, mesas_ids)

    def test_cajero_registrar_venta_con_mesa_disponible_exitosa(self):
        """Registrar venta asignando mesa disponible debe cambiar su estado a ocupada y asociar venta y comanda."""
        self._autenticar(self.cajero)
        payload = {
            'tipo_venta': 'mesa',
            'mesa_id': self.mesa_disp1.id,
            'metodo_pago': 'efectivo',
            'notas': 'Sin cebolla',
            'items': [{'id': self.producto.id, 'cantidad': 2}]
        }
        res = self.client.post('/cajero/registrar-venta/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('tipo_venta'), 'mesa')
        self.assertEqual(data.get('mesa_id'), self.mesa_disp1.id)

        # La mesa debe haber pasado a 'ocupada'
        self.mesa_disp1.refresh_from_db()
        self.assertEqual(self.mesa_disp1.estado, 'ocupada')

        # Venta y Comanda deben estar asociadas a la mesa
        venta = Venta.objects.latest('id')
        self.assertEqual(venta.mesa_id, self.mesa_disp1.id)
        self.assertEqual(venta.tipo_venta, 'mesa')

        comanda = Comanda.objects.latest('id')
        self.assertEqual(comanda.mesa_rel_id, self.mesa_disp1.id)
        self.assertEqual(comanda.tipo_pedido, 'mesa')

    def test_cajero_registrar_venta_bloqueo_mesa_no_disponible(self):
        """Si la mesa seleccionada ya está ocupada o no disponible, debe rechazar la venta con error 400."""
        self._autenticar(self.cajero)
        payload = {
            'tipo_venta': 'mesa',
            'mesa_id': self.mesa_ocupada.id,
            'metodo_pago': 'efectivo',
            'items': [{'id': self.producto.id, 'cantidad': 1}]
        }
        res = self.client.post('/cajero/registrar-venta/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertFalse(data.get('success'))
        self.assertIn('no está disponible', data.get('error', ''))

    def test_cajero_registrar_venta_sin_mesa_mostrador(self):
        """Si no se selecciona mesa, debe registrar como venta en barra / para llevar."""
        self._autenticar(self.cajero)
        payload = {
            'tipo_venta': 'barra',
            'mesa_id': None,
            'mesa': 'Para Llevar',
            'metodo_pago': 'tarjeta',
            'items': [{'id': self.producto.id, 'cantidad': 1}]
        }
        res = self.client.post('/cajero/registrar-venta/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('tipo_venta'), 'barra')

        venta = Venta.objects.latest('id')
        self.assertIsNone(venta.mesa)
        self.assertEqual(venta.tipo_venta, 'barra')


# ==============================================================================
# SUITE DE PRUEBAS: MÓDULO DE MESERO CON NAVEGACIÓN POR TABS Y POLLING
# ==============================================================================

class ModuloMeseroTabsTestCase(TestCase):
    """
    Verifica el rediseño y lógica modular del módulo de Mesero:
    - Navegación por 4 pestañas (Listos para Servir, Mesas Disponibles, Mesas Ocupadas, Mesas Servidas/Cobro).
    - Conteo dinámico de pedidos y mesas por fase.
    - Endpoint JSON api_mesero_estado para polling en tiempo real.
    - Acción de marcar comanda como servida/entregada (actualiza comanda a 'entregado' y mesa.comida_entregada = True).
    - Restricción estricta de rol para Mesero (bloqueo a cocina, caja y stock).
    - Bloqueo de usuarios no autorizados en los endpoints de mesero.
    """

    def setUp(self):
        self.client = Client()
        self.mesero = Usuario.objects.create(
            nombre="Mesero Tabs Test",
            correo="meserotabs@safari.cl",
            username="meserotabs",
            password="password123",
            rol="mesero",
            estado="activo"
        )
        self.cocinero = Usuario.objects.create(
            nombre="Cocinero Test",
            correo="cocinerotabs@safari.cl",
            username="cocinerotabs",
            password="password123",
            rol="cocinero",
            estado="activo"
        )
        self.cajero = Usuario.objects.create(
            nombre="Cajero Test",
            correo="cajerotabs@safari.cl",
            username="cajerotabs",
            password="password123",
            rol="cajero",
            estado="activo"
        )
        self.mesa_disp = Mesa.objects.create(numero=20, nombre="Mesa 20", capacidad=4, estado="disponible")
        self.mesa_ocup = Mesa.objects.create(numero=21, nombre="Mesa 21", capacidad=2, estado="ocupada", comida_entregada=False)
        self.mesa_serv = Mesa.objects.create(numero=22, nombre="Mesa 22", capacidad=6, estado="ocupada", comida_entregada=True)
        self.mesa_cobro = Mesa.objects.create(numero=23, nombre="Mesa 23", capacidad=4, estado="LISTO_PARA_COBRO", comida_entregada=True)

        self.producto = Producto.objects.create(
            nombre="Pizza Safari",
            descripcion="Pizza con jamón y queso",
            precio=Decimal("7990.00"),
            stock=15
        )

        # Comanda lista para servir en Mesa 21
        self.comanda_lista = Comanda.objects.create(
            folio="COM-9901",
            mesa=self.mesa_ocup.nombre,
            mesa_rel=self.mesa_ocup,
            mesero=self.mesero,
            items="1x Pizza Safari ($7,990)",
            items_json=json.dumps([{'id': self.producto.id, 'nombre': self.producto.nombre, 'cantidad': 1, 'precio': 7990.0}]),
            tipo_pedido='mesa',
            pagada=False,
            total=Decimal("7990.00"),
            estado='listo'
        )

    def _autenticar(self, usuario):
        s = self.client.session
        s['usuario_id'] = usuario.id
        s['usuario'] = {'id': usuario.id, 'nombre': usuario.nombre, 'rol': usuario.rol}
        s['rol'] = usuario.rol
        s.save()

    def test_mesero_view_contexto_tabs_y_contadores(self):
        """Verifica que mesero_view entregue los 4 conjuntos de datos y contadores en su contexto."""
        self._autenticar(self.mesero)
        res = self.client.get('/mesero/')
        self.assertEqual(res.status_code, 200)

        # Verificar presencia de variables clave de las 4 pestañas
        self.assertIn('tab_activa', res.context)
        self.assertIn('comandas_listas', res.context)
        self.assertIn('mesas_disponibles', res.context)
        self.assertIn('mesas_ocupadas', res.context)
        self.assertIn('mesas_servidas', res.context)

        # Validar contadores
        self.assertEqual(res.context['count_listos_servir'], 1)
        self.assertEqual(res.context['count_disponibles'], 1)
        self.assertEqual(res.context['count_ocupadas'], 1)
        self.assertEqual(res.context['count_servidas'], 2)  # mesa_serv + mesa_cobro

        # Validar membresía en cada tab
        listos_ids = [c.id for c in res.context['comandas_listas']]
        self.assertIn(self.comanda_lista.id, listos_ids)

        disp_ids = [m.id for m in res.context['mesas_disponibles']]
        self.assertIn(self.mesa_disp.id, disp_ids)

        ocup_ids = [m.id for m in res.context['mesas_ocupadas']]
        self.assertIn(self.mesa_ocup.id, ocup_ids)

        serv_ids = [m.id for m in res.context['mesas_servidas']]
        self.assertIn(self.mesa_serv.id, serv_ids)
        self.assertIn(self.mesa_cobro.id, serv_ids)

    def test_api_mesero_estado_polling_json(self):
        """Verifica que el endpoint JSON /api/mesero/estado/ entregue la estructura requerida para polling."""
        self._autenticar(self.mesero)
        res = self.client.get('/api/mesero/estado/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))

        contadores = data.get('contadores', {})
        self.assertEqual(contadores.get('listos_servir'), 1)
        self.assertEqual(contadores.get('disponibles'), 1)
        self.assertEqual(contadores.get('ocupadas'), 1)
        self.assertEqual(contadores.get('servidas'), 2)

        comandas_listas = data.get('comandas_listas', [])
        self.assertEqual(len(comandas_listas), 1)
        self.assertEqual(comandas_listas[0]['id'], self.comanda_lista.id)
        self.assertEqual(comandas_listas[0]['folio'], self.comanda_lista.folio)
        self.assertEqual(comandas_listas[0]['mesa'], self.mesa_ocup.nombre)

    def test_mesero_marcar_entregado_actualiza_comanda_y_mesa(self):
        """Verifica que marcar como servido cambie el estado de la comanda a 'entregado' y mesa.comida_entregada a True."""
        self._autenticar(self.mesero)
        payload = {'comanda_id': self.comanda_lista.id, 'mesa_id': self.mesa_ocup.id}
        res = self.client.post('/mesero/marcar-entregado/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('estado'), 'entregado')
        self.assertTrue(data.get('comida_entregada'))

        # Comprobar en base de datos
        self.comanda_lista.refresh_from_db()
        self.assertEqual(self.comanda_lista.estado, 'entregado')

        self.mesa_ocup.refresh_from_db()
        self.assertTrue(self.mesa_ocup.comida_entregada)

    def test_bloqueo_acceso_mesero_a_cocina_caja_y_stock(self):
        """Verifica que el rol mesero tenga denegado el acceso a cocina, caja y stock."""
        self._autenticar(self.mesero)

        # Acceso a cocina denegado
        res_cocina = self.client.get('/cocinero/')
        self.assertEqual(res_cocina.status_code, 403)

        # Acceso a caja denegado
        res_caja = self.client.get('/cajero/')
        self.assertEqual(res_caja.status_code, 403)

        # Acceso a stock denegado
        res_stock = self.client.get('/stock/')
        self.assertEqual(res_stock.status_code, 403)

    def test_bloqueo_usuarios_no_autorizados_a_mesero(self):
        """Verifica que un rol no autorizado (ej. cocinero o anónimo) no pueda acceder a las acciones de mesero."""
        # Usuario no autenticado
        res_anon = self.client.post('/mesero/marcar-entregado/', data=json.dumps({'comanda_id': self.comanda_lista.id}), content_type='application/json')
        self.assertEqual(res_anon.status_code, 403)

        res_anon_api = self.client.get('/api/mesero/estado/')
        self.assertEqual(res_anon_api.status_code, 403)

        # Cocinero intentando marcar comanda servida
        self._autenticar(self.cocinero)
        res_cocinero = self.client.post('/mesero/marcar-entregado/', data=json.dumps({'comanda_id': self.comanda_lista.id}), content_type='application/json')
        self.assertEqual(res_cocinero.status_code, 403)







