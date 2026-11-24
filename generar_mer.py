import os
import tempfile

os.environ['MPLCONFIGDIR'] = tempfile.mkdtemp()

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def generar_mer_profesional():
    # Canvas amplio y de ultra alta resolución (42 x 28 pulgadas a 150 DPI => 6300 x 4200 px)
    fig_w, fig_h = 42, 28
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=150)
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis('off')

    # Color de fondo: gris azulado muy suave y moderno
    bg_color = '#f8fafc'
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    # -------------------------------------------------------------------------
    # 1. ENCABEZADO PRINCIPAL (BANNER INSTITUCIONAL)
    # -------------------------------------------------------------------------
    banner = patches.FancyBboxPatch(
        (0.8, fig_h - 2.6), fig_w - 1.6, 1.9,
        boxstyle="round,pad=0.25,rounding_size=0.35",
        facecolor='#1b4332', edgecolor='#081c15', linewidth=2.5, zorder=2
    )
    ax.add_patch(banner)

    # Acento dorado inferior
    gold_bar = patches.Rectangle(
        (1.0, fig_h - 2.65), fig_w - 2.0, 0.12,
        facecolor='#d4a373', edgecolor='none', zorder=3
    )
    ax.add_patch(gold_bar)

    ax.text(
        fig_w / 2, fig_h - 1.35,
        "PARQUE SAFARI CHILE — MODELO ENTIDAD-RELACIÓN (MER / DER)",
        fontsize=24, fontweight='bold', color='#ffffff', ha='center', va='center', zorder=4
    )
    ax.text(
        fig_w / 2, fig_h - 1.95,
        "Diagrama Físico y Relacional 1:1 con Django ORM (Safari/models.py) y MySQL Workbench (`proyecto`) — Motor InnoDB / UTF-8 MB4",
        fontsize=13.5, color='#e2e8f0', ha='center', va='center', zorder=4
    )

    # -------------------------------------------------------------------------
    # 2. DEFINICIÓN ESTRUCTURAL DE ENTIDADES (LAYOUT EN 4 COLUMNAS SIN COLISIONES)
    # -------------------------------------------------------------------------
    tablas = {
        # --- COLUMNA 1 (x = 2.0): Seguridad, Auditoría y Menús ---
        'Usuario': {
            'x': 2.0, 'y': 24.2, 'w': 7.0, 'h': 6.6,
            'color': '#1d3557', 'cat': 'Módulo de Usuarios y Seguridad',
            'fields': [
                ('PK', 'id', 'BIGINT AUTO_INCREMENT'),
                ('  ', 'rut', 'VARCHAR(20)'),
                ('  ', 'nombre', 'VARCHAR(100)'),
                ('UK', 'correo', 'VARCHAR(254) UNIQUE'),
                ('UK', 'username', 'VARCHAR(50) UNIQUE'),
                ('  ', 'password', 'VARCHAR(128) (Hash)'),
                ('  ', 'rol', 'VARCHAR(50)'),
                ('  ', 'estado', "VARCHAR(20) DEFAULT 'activo'"),
            ]
        },
        'HistorialAccion': {
            'x': 2.0, 'y': 15.8, 'w': 7.0, 'h': 5.4,
            'color': '#4338ca', 'cat': 'Auditoría y Trazabilidad',
            'fields': [
                ('PK', 'id', 'BIGINT AUTO_INCREMENT'),
                ('FK', 'usuario_id', 'BIGINT -> Usuario(id)'),
                ('  ', 'accion', 'VARCHAR(50)'),
                ('  ', 'modulo', 'VARCHAR(50)'),
                ('  ', 'detalle', 'LONGTEXT'),
                ('  ', 'fecha', 'DATETIME(6)'),
            ]
        },
        'Menu': {
            'x': 2.0, 'y': 8.6, 'w': 7.0, 'h': 4.8,
            'color': '#bc6c25', 'cat': 'Categorías y Menú',
            'fields': [
                ('PK', 'id', 'BIGINT AUTO_INCREMENT'),
                ('  ', 'nombre', 'VARCHAR(100)'),
                ('  ', 'descripcion', 'VARCHAR(255)'),
                ('  ', 'estado', "VARCHAR(20) DEFAULT 'activo'"),
            ]
        },

        # --- COLUMNA 2 (x = 11.5): Puntos de Venta, Cajas y Productos ---
        'PuntoDeVenta': {
            'x': 11.5, 'y': 24.2, 'w': 7.4, 'h': 4.8,
            'color': '#0284c7', 'cat': 'Terminales de Venta Físicos',
            'fields': [
                ('PK', 'id', 'BIGINT AUTO_INCREMENT'),
                ('  ', 'nombre', 'VARCHAR(100)'),
                ('  ', 'ubicacion', 'VARCHAR(100)'),
                ('  ', 'estado', "VARCHAR(20) DEFAULT 'activo'"),
            ]
        },
        'ControlCaja': {
            'x': 11.5, 'y': 17.6, 'w': 7.6, 'h': 8.6,
            'color': '#0d9488', 'cat': 'Control y Arqueo de Cajas',
            'fields': [
                ('PK', 'id', 'BIGINT AUTO_INCREMENT'),
                ('  ', 'abierta', 'TINYINT(1) (BOOLEAN)'),
                ('  ', 'fecha_apertura', 'DATETIME(6)'),
                ('  ', 'fecha_cierre', 'DATETIME(6) NULL'),
                ('FK', 'cajero_responsable_id', 'BIGINT -> Usuario(id)'),
                ('FK', 'cerrada_por_id', 'BIGINT -> Usuario(id)'),
                ('FK', 'punto_de_venta_id', 'BIGINT -> PuntoDeVenta(id)'),
                ('  ', 'monto_inicial', 'DECIMAL(10,2)'),
                ('  ', 'total_ventas', 'DECIMAL(10,2)'),
                ('  ', 'total_efectivo', 'DECIMAL(10,2)'),
                ('  ', 'total_tarjeta', 'DECIMAL(10,2)'),
                ('  ', 'total_transferencia', 'DECIMAL(10,2)'),
                ('  ', 'monto_real', 'DECIMAL(10,2) (Arqueo)'),
                ('  ', 'diferencia', 'DECIMAL(10,2) (Sobr/Falt)'),
            ]
        },
        'Producto': {
            'x': 11.5, 'y': 7.2, 'w': 7.6, 'h': 5.8,
            'color': '#9a3412', 'cat': 'Catálogo Gastronómico',
            'fields': [
                ('PK', 'id', 'BIGINT AUTO_INCREMENT'),
                ('  ', 'codigo', 'VARCHAR(50) (SKU)'),
                ('  ', 'nombre', 'VARCHAR(100)'),
                ('  ', 'descripcion', 'VARCHAR(255)'),
                ('  ', 'precio', 'DECIMAL(10,2) CLP'),
                ('  ', 'stock', 'INT DEFAULT 0'),
                ('FK', 'menu_id', 'BIGINT -> Menu(id) [SET NULL]'),
            ]
        },

        # --- COLUMNA 3 (x = 21.8): Ventas y Detalles de Venta ---
        'Venta': {
            'x': 21.8, 'y': 18.2, 'w': 7.6, 'h': 6.8,
            'color': '#1e3a8a', 'cat': 'Transacciones y Boletas',
            'fields': [
                ('PK', 'id', 'BIGINT AUTO_INCREMENT'),
                ('  ', 'fecha', 'DATETIME(6)'),
                ('  ', 'total', 'DECIMAL(10,2) CLP'),
                ('  ', 'metodo_pago', "VARCHAR(20) ('efectivo'...)"),
                ('FK', 'usuario_id', 'BIGINT -> Usuario(id) (Cajero)'),
                ('FK', 'mesero_id', 'BIGINT -> Usuario(id) (Mesero)'),
                ('FK', 'control_caja_id', 'BIGINT -> ControlCaja(id)'),
            ]
        },
        'DetalleVenta': {
            'x': 21.8, 'y': 9.6, 'w': 7.6, 'h': 5.4,
            'color': '#ea580c', 'cat': 'Ítems y Líneas de Boleta',
            'fields': [
                ('PK', 'id', 'BIGINT AUTO_INCREMENT'),
                ('  ', 'cantidad', 'INT DEFAULT 1'),
                ('  ', 'subtotal', 'DECIMAL(10,2) CLP'),
                ('FK', 'venta_id', 'BIGINT -> Venta(id) [CASCADE]'),
                ('FK', 'producto_id', 'BIGINT -> Producto(id) [CASCADE]'),
            ]
        },

        # --- COLUMNA 4 (x = 32.2): Mesas, Cocina y Correlativos ---
        'Mesa': {
            'x': 32.2, 'y': 24.2, 'w': 7.2, 'h': 5.2,
            'color': '#15803d', 'cat': 'Salón y Comensales',
            'fields': [
                ('PK', 'id', 'BIGINT AUTO_INCREMENT'),
                ('UK', 'numero', 'INT UNIQUE'),
                ('  ', 'nombre', 'VARCHAR(50)'),
                ('  ', 'capacidad', 'INT DEFAULT 4'),
                ('  ', 'estado', "VARCHAR(20) ('disponible'...)"),
                ('  ', 'comida_entregada', 'TINYINT(1) (BOOLEAN)'),
            ]
        },
        'Comanda': {
            'x': 32.2, 'y': 17.2, 'w': 7.2, 'h': 5.8,
            'color': '#b91c1c', 'cat': 'Monitor de Cocina y Despacho',
            'fields': [
                ('PK', 'id', 'BIGINT AUTO_INCREMENT'),
                ('  ', 'folio', 'VARCHAR(50) (BOL-XXXX)'),
                ('  ', 'mesa', "VARCHAR(50) DEFAULT 'Mesa 1'"),
                ('  ', 'items', 'LONGTEXT (Detalle platos)'),
                ('  ', 'total', 'DECIMAL(10,2) CLP'),
                ('  ', 'estado', "VARCHAR(20) ('preparacion'...)"),
                ('  ', 'fecha', 'DATETIME(6)'),
            ]
        },
        'SecuenciaFolio': {
            'x': 32.2, 'y': 9.6, 'w': 7.2, 'h': 4.4,
            'color': '#475569', 'cat': 'Control Correlativo Oficial',
            'fields': [
                ('PK', 'id', 'BIGINT AUTO_INCREMENT'),
                ('UK', 'tipo', "VARCHAR(20) ('venta'/'comanda')"),
                ('  ', 'ultimo_numero', 'INT UNSIGNED DEFAULT 0'),
            ]
        }
    }

    # -------------------------------------------------------------------------
    # 3. RENDERIZADO DE LAS TARJETAS DE ENTIDADES
    # -------------------------------------------------------------------------
    for t_name, data in tablas.items():
        x = data['x']
        y = data['y']
        w = data['w']
        h = data['h']
        color = data['color']
        fields = data['fields']
        cat = data['cat']

        # Sombra sutil de la tarjeta
        shadow = patches.FancyBboxPatch(
            (x + 0.12, y - h - 0.12), w, h,
            boxstyle="round,pad=0.1,rounding_size=0.3",
            facecolor='#0f172a', alpha=0.08, edgecolor='none', zorder=2
        )
        ax.add_patch(shadow)

        # Cuerpo blanco de la tarjeta
        body = patches.FancyBboxPatch(
            (x, y - h), w, h,
            boxstyle="round,pad=0.1,rounding_size=0.3",
            facecolor='#ffffff', edgecolor='#cbd5e1', linewidth=1.8, zorder=3
        )
        ax.add_patch(body)

        # Cabecera coloreada
        header_h = 1.15
        header = patches.FancyBboxPatch(
            (x, y - header_h), w, header_h,
            boxstyle="round,pad=0.08,rounding_size=0.3",
            facecolor=color, edgecolor=color, linewidth=1, zorder=4
        )
        ax.add_patch(header)

        # Relleno inferior para cuadrar cabecera
        header_bottom = patches.Rectangle(
            (x, y - header_h), w, 0.3,
            facecolor=color, edgecolor='none', zorder=5
        )
        ax.add_patch(header_bottom)

        # Texto de cabecera
        ax.text(
            x + w / 2, y - 0.45,
            f"Safari_{t_name.lower()}",
            fontsize=13, fontweight='bold', color='#ffffff', ha='center', va='center', zorder=6
        )
        ax.text(
            x + w / 2, y - 0.82,
            f"class {t_name} • {cat}",
            fontsize=9.2, color='#f1f5f9', ha='center', va='center', zorder=6
        )

        # Línea separadora de cabecera
        ax.plot([x, x + w], [y - header_h, y - header_h], color='#94a3b8', linewidth=0.8, zorder=6)

        # Renderizar atributos
        row_count = len(fields)
        row_space = (h - header_h - 0.35) / max(row_count, 1)

        for i, (key_type, f_name, f_type) in enumerate(fields):
            row_y = y - header_h - 0.3 - (i * row_space)

            # Fondo alternado para lectura cómoda
            if i % 2 == 1:
                bg_row = patches.Rectangle(
                    (x + 0.05, row_y - row_space + 0.12), w - 0.1, row_space,
                    facecolor='#f8fafc', edgecolor='none', zorder=4
                )
                ax.add_patch(bg_row)

            # Badges de claves
            if key_type == 'PK':
                pk_badge = patches.FancyBboxPatch(
                    (x + 0.28, row_y - 0.2), 0.72, 0.36,
                    boxstyle="round,pad=0.02,rounding_size=0.08",
                    facecolor='#eab308', edgecolor='#ca8a04', linewidth=0.9, zorder=6
                )
                ax.add_patch(pk_badge)
                ax.text(x + 0.64, row_y - 0.02, "PK", fontsize=8, fontweight='bold', color='#713f12', ha='center', va='center', zorder=7)
            elif key_type == 'FK':
                fk_badge = patches.FancyBboxPatch(
                    (x + 0.28, row_y - 0.2), 0.72, 0.36,
                    boxstyle="round,pad=0.02,rounding_size=0.08",
                    facecolor='#0284c7', edgecolor='#0369a1', linewidth=0.9, zorder=6
                )
                ax.add_patch(fk_badge)
                ax.text(x + 0.64, row_y - 0.02, "FK", fontsize=8, fontweight='bold', color='#ffffff', ha='center', va='center', zorder=7)
            elif key_type == 'UK':
                uk_badge = patches.FancyBboxPatch(
                    (x + 0.28, row_y - 0.2), 0.72, 0.36,
                    boxstyle="round,pad=0.02,rounding_size=0.08",
                    facecolor='#10b981', edgecolor='#059669', linewidth=0.9, zorder=6
                )
                ax.add_patch(uk_badge)
                ax.text(x + 0.64, row_y - 0.02, "UK", fontsize=8, fontweight='bold', color='#ffffff', ha='center', va='center', zorder=7)

            # Nombre de atributo
            font_weight = 'bold' if key_type in ['PK', 'FK', 'UK'] else 'normal'
            font_color = '#0f172a' if key_type in ['PK', 'FK', 'UK'] else '#334155'
            ax.text(x + 1.18, row_y - 0.02, f_name, fontsize=9.2, fontweight=font_weight, color=font_color, va='center', zorder=7)

            # Tipo de dato
            ax.text(x + w - 0.28, row_y - 0.02, f_type, fontsize=8.2, color='#64748b', ha='right', va='center', zorder=7)

    # -------------------------------------------------------------------------
    # 4. CONECTORES Y RELACIONES ORTOGONALES SIN COLISIÓN
    # -------------------------------------------------------------------------
    relaciones = [
        # 1. Usuario (1) -> (N) HistorialAccion (Ambos en Col 1, línea recta vertical)
        {
            'pts': [(5.5, 24.2 - 6.6), (5.5, 15.8)],
            'card_orig': '1', 'pos_orig': (5.8, 17.3),
            'card_dest': 'N', 'pos_dest': (5.8, 16.1),
            'label': 'registra auditoría', 'lbl_pos': (5.5, 16.7),
            'color': '#4338ca'
        },
        # 2. PuntoDeVenta (1) -> (N) ControlCaja (Ambos en Col 2, línea recta vertical)
        {
            'pts': [(15.2, 24.2 - 4.8), (15.2, 17.6)],
            'card_orig': '1', 'pos_orig': (15.5, 19.1),
            'card_dest': 'N', 'pos_dest': (15.5, 17.9),
            'label': 'asigna caja', 'lbl_pos': (15.2, 18.5),
            'color': '#0284c7'
        },
        # 3. Usuario (1) -> (N) ControlCaja (Corredor entre Col 1 y Col 2)
        {
            'pts': [(9.0, 20.0), (10.2, 20.0), (10.2, 14.5), (11.5, 14.5)],
            'card_orig': '1', 'pos_orig': (9.3, 20.3),
            'card_dest': 'N', 'pos_dest': (11.1, 14.8),
            'label': 'opera turno', 'lbl_pos': (10.2, 17.2),
            'color': '#0d9488'
        },
        # 4. Menu (1) -> (N) Producto (Línea recta horizontal en piso inferior)
        {
            'pts': [(9.0, 6.2), (11.5, 6.2)],
            'card_orig': '1', 'pos_orig': (9.3, 6.5),
            'card_dest': 'N', 'pos_dest': (11.1, 6.5),
            'label': 'clasifica', 'lbl_pos': (10.25, 6.2),
            'color': '#bc6c25'
        },
        # 5. ControlCaja (1) -> (N) Venta (Horizontal directa entre Col 2 y Col 3)
        {
            'pts': [(19.1, 14.8), (21.8, 14.8)],
            'card_orig': '1', 'pos_orig': (19.4, 15.1),
            'card_dest': 'N', 'pos_dest': (21.4, 15.1),
            'label': 'acumula turno', 'lbl_pos': (20.45, 14.8),
            'color': '#0d9488'
        },
        # 6. Usuario (1) -> (N) Venta (Corredor aéreo superior libre)
        {
            'pts': [(5.5, 24.2), (5.5, 25.1), (25.6, 25.1), (25.6, 18.2)],
            'card_orig': '1', 'pos_orig': (5.8, 24.5),
            'card_dest': 'N', 'pos_dest': (25.9, 18.5),
            'label': 'emite / cobra venta', 'lbl_pos': (15.5, 25.1),
            'color': '#1d3557'
        },
        # 7. Venta (1) -> (N) DetalleVenta (Vertical directa en Col 3)
        {
            'pts': [(25.6, 18.2 - 6.8), (25.6, 9.6)],
            'card_orig': '1', 'pos_orig': (25.9, 11.1),
            'card_dest': 'N', 'pos_dest': (25.9, 9.9),
            'label': 'desglosa ítems', 'lbl_pos': (25.6, 10.5),
            'color': '#ea580c'
        },
        # 8. Producto (1) -> (N) DetalleVenta (Corredor horizontal entre Col 2 y Col 3)
        {
            'pts': [(19.1, 4.3), (20.5, 4.3), (20.5, 7.0), (21.8, 7.0)],
            'card_orig': '1', 'pos_orig': (19.4, 4.6),
            'card_dest': 'N', 'pos_dest': (21.4, 7.3),
            'label': 'vendido en', 'lbl_pos': (20.5, 5.65),
            'color': '#9a3412'
        },
        # 9. Venta (1) -> (1) Comanda (Horizontal directa entre Col 3 y Col 4)
        {
            'pts': [(29.4, 14.3), (32.2, 14.3)],
            'card_orig': '1', 'pos_orig': (29.7, 14.6),
            'card_dest': '1', 'pos_dest': (31.8, 14.6),
            'label': 'despacha a cocina', 'lbl_pos': (30.8, 14.3),
            'color': '#b91c1c'
        },
        # 10. Mesa (1) -> (N) Comanda (Vertical directa en Col 4)
        {
            'pts': [(35.8, 24.2 - 5.2), (35.8, 17.2)],
            'card_orig': '1', 'pos_orig': (36.1, 18.7),
            'card_dest': 'N', 'pos_dest': (36.1, 17.5),
            'label': 'recibe pedido', 'lbl_pos': (35.8, 18.1),
            'color': '#15803d'
        }
    ]

    for rel in relaciones:
        pts = rel['pts']
        c = rel['color']
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]

        # Trazar línea de relación
        ax.plot(xs, ys, color=c, linewidth=2.4, linestyle='-', zorder=4, alpha=0.92)

        # Marcador circular en lado '1'
        ax.scatter([xs[0]], [ys[0]], color=c, s=42, zorder=5)

        # Flecha indicadora en destino
        last_dx = xs[-1] - xs[-2]
        last_dy = ys[-1] - ys[-2]
        dist = (last_dx**2 + last_dy**2)**0.5
        if dist > 0:
            ndx = (last_dx / dist) * 0.35
            ndy = (last_dy / dist) * 0.35
            ax.annotate(
                '', xy=(xs[-1], ys[-1]), xytext=(xs[-1] - ndx, ys[-1] - ndy),
                arrowprops=dict(arrowstyle="-|>", color=c, lw=2.4, mutation_scale=16),
                zorder=6
            )

        # Cardinalidades (1 y N)
        ax.text(rel['pos_orig'][0], rel['pos_orig'][1], rel['card_orig'], fontsize=11.5, fontweight='bold', color=c, zorder=7)
        ax.text(rel['pos_dest'][0], rel['pos_dest'][1], rel['card_dest'], fontsize=11.5, fontweight='bold', color=c, zorder=7)

        # Etiqueta con fondo blanco en el punto medio
        lbl_x, lbl_y = rel['lbl_pos']
        lbl_box = patches.FancyBboxPatch(
            (lbl_x - 0.95, lbl_y - 0.25), 1.9, 0.5,
            boxstyle="round,pad=0.03,rounding_size=0.12",
            facecolor='#ffffff', edgecolor=c, linewidth=1.1, zorder=5
        )
        ax.add_patch(lbl_box)
        ax.text(lbl_x, lbl_y, rel['label'], fontsize=8.2, fontweight='bold', color=c, ha='center', va='center', zorder=6)

    # -------------------------------------------------------------------------
    # 5. PANEL DE LEYENDA Y METADATOS TÉCNICOS (PIE DE PÁGINA)
    # -------------------------------------------------------------------------
    pie_y = 0.8
    pie_h = 2.4
    panel_pie = patches.FancyBboxPatch(
        (0.8, pie_y), fig_w - 1.6, pie_h,
        boxstyle="round,pad=0.2,rounding_size=0.3",
        facecolor='#ffffff', edgecolor='#cbd5e1', linewidth=1.6, zorder=2
    )
    ax.add_patch(panel_pie)

    # Título de Leyenda
    ax.text(1.2, pie_y + pie_h - 0.45, "CONVENCIONES DEL MODELO Y LEYENDA TÉCNICA:", fontsize=11.5, fontweight='bold', color='#0f172a', va='center')

    # Badges explicativos
    ax.add_patch(patches.FancyBboxPatch((1.2, pie_y + 0.95), 0.75, 0.38, boxstyle="round,pad=0.02,rounding_size=0.08", facecolor='#eab308', edgecolor='#ca8a04', zorder=3))
    ax.text(1.57, pie_y + 1.14, "PK", fontsize=8.5, fontweight='bold', color='#713f12', ha='center', va='center')
    ax.text(2.15, pie_y + 1.14, "Primary Key (Clave Primaria Autoincremental)", fontsize=9.5, color='#334155', va='center')

    ax.add_patch(patches.FancyBboxPatch((8.2, pie_y + 0.95), 0.75, 0.38, boxstyle="round,pad=0.02,rounding_size=0.08", facecolor='#0284c7', edgecolor='#0369a1', zorder=3))
    ax.text(8.57, pie_y + 1.14, "FK", fontsize=8.5, fontweight='bold', color='#ffffff', ha='center', va='center')
    ax.text(9.15, pie_y + 1.14, "Foreign Key (Clave Foránea con Integridad Referencial)", fontsize=9.5, color='#334155', va='center')

    ax.add_patch(patches.FancyBboxPatch((16.8, pie_y + 0.95), 0.75, 0.38, boxstyle="round,pad=0.02,rounding_size=0.08", facecolor='#10b981', edgecolor='#059669', zorder=3))
    ax.text(17.17, pie_y + 1.14, "UK", fontsize=8.5, fontweight='bold', color='#ffffff', ha='center', va='center')
    ax.text(17.75, pie_y + 1.14, "Unique Key (Restricción de Unicidad)", fontsize=9.5, color='#334155', va='center')

    ax.text(25.5, pie_y + 1.14, "Cardinalidades: [ 1 ] = Uno  |  [ N ] = Muchos (Relaciones 1:N y 1:1)", fontsize=9.5, fontweight='bold', color='#0f172a', va='center')

    # Fila inferior de especificaciones técnicas
    spec_text = (
        "• Base de Datos: MySQL 8.0+ / MariaDB 10.4+  |  Charset: utf8mb4_unicode_ci  |  Motor de Almacenamiento: InnoDB (Transacciones ACID y Claves Foráneas ON DELETE CASCADE / SET NULL)\n"
        "• Implementación ORM: Django 6.x en Safari/models.py  |  Paridad Estricta 1:1 con DDL proyecto_mysql_workbench.sql  |  Total: 11 Entidades Oficiales del Sistema"
    )
    ax.text(1.2, pie_y + 0.45, spec_text, fontsize=9.0, color='#64748b', va='center')

    # Guardar en rutas del proyecto
    ruta_1 = os.path.abspath("modelo_entidad_relacion.png")
    ruta_2 = os.path.abspath("proyecto_safari/modelo_entidad_relacion.png")

    plt.tight_layout()
    plt.savefig(ruta_1, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    if os.path.exists("proyecto_safari"):
        plt.savefig(ruta_2, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')

    ruta_artifacts = os.environ.get('ARTIFACTS_DIR', '')
    if ruta_artifacts and os.path.exists(ruta_artifacts):
        plt.savefig(os.path.join(ruta_artifacts, "modelo_entidad_relacion.png"), dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

    print(f"MER profesional generado exitosamente en:\n1. {ruta_1}\n2. {ruta_2}")

if __name__ == '__main__':
    generar_mer_profesional()
