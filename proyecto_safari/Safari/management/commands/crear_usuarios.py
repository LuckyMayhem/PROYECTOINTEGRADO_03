from django.core.management.base import BaseCommand
from Safari.models import Usuario, Mesa, Menu, PuntoDeVenta, SecuenciaFolio


class Command(BaseCommand):
    help = "Crea los usuarios iniciales del sistema Safari POS (Admin, Cajero, Mesero, Cocinero) y datos base"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Creando o actualizando usuarios base de Safari POS..."))

        usuarios = [
            {
                'rut': '12.345.678-9',
                'nombre': 'Administrador General',
                'correo': 'admin@parquesafari.cl',
                'username': 'admin',
                'password': 'adminpassword123',
                'rol': 'administrador',
                'estado': 'activo',
            },
            {
                'rut': '14.567.890-1',
                'nombre': 'Javier Soto (Cajero)',
                'correo': 'caja@parquesafari.cl',
                'username': 'cajero',
                'password': 'cajeropassword123',
                'rol': 'cajero',
                'estado': 'activo',
            },
            {
                'rut': '16.789.012-3',
                'nombre': 'Lucía Morales (Mesera)',
                'correo': 'mesas@parquesafari.cl',
                'username': 'mesero',
                'password': 'meseropassword123',
                'rol': 'mesero',
                'estado': 'activo',
            },
            {
                'rut': '18.901.234-5',
                'nombre': 'Roberto García (Chef)',
                'correo': 'cocina@parquesafari.cl',
                'username': 'cocinero',
                'password': 'cocineropassword123',
                'rol': 'cocinero',
                'estado': 'activo',
            },
        ]

        for u_data in usuarios:
            username = u_data['username']
            usuario, creado = Usuario.objects.update_or_create(
                username=username,
                defaults=u_data
            )
            accion = "Creado" if creado else "Actualizado"
            self.stdout.write(self.style.SUCCESS(
                f"  [{accion}] {usuario.rol.capitalize()}: {usuario.nombre} | Usuario: {usuario.username} | Password: {usuario.password}"
            ))

        # Secuencias de folios
        SecuenciaFolio.objects.get_or_create(tipo='venta', defaults={'ultimo_numero': 0})
        SecuenciaFolio.objects.get_or_create(tipo='comanda', defaults={'ultimo_numero': 0})

        # Puntos de Venta básicos
        PuntoDeVenta.objects.get_or_create(
            nombre='Caja Principal Salón',
            defaults={'ubicacion': 'Acceso Principal Salón', 'estado': 'activo'}
        )

        # Menús básicos
        Menu.objects.get_or_create(nombre='Platos de Fondo', defaults={'descripcion': 'Platos principales y carnes', 'estado': 'activo'})
        Menu.objects.get_or_create(nombre='Bebestibles', defaults={'descripcion': 'Bebidas y jugos', 'estado': 'activo'})
        Menu.objects.get_or_create(nombre='Postres', defaults={'descripcion': 'Postres y helados', 'estado': 'activo'})

        # Mesas 1 a 10
        for i in range(1, 11):
            Mesa.objects.get_or_create(
                numero=i,
                defaults={'nombre': f'Mesa {i}', 'capacidad': 4, 'estado': 'disponible', 'comida_entregada': False}
            )

        self.stdout.write(self.style.SUCCESS("\n¡Datos y usuarios iniciales creados exitosamente!"))
