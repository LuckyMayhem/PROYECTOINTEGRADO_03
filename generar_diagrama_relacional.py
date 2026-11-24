import os
import tempfile

os.environ['MPLCONFIGDIR'] = tempfile.mkdtemp()

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def generar_diagrama_relacional():
    # Dimensiones en ultra alta definición (Canvas 44 x 28 pulgadas a 150 DPI => 6600 x 4200 px)
    fig_w, fig_h = 44, 28
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=150)
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis('off')

    # Fondo general
    bg_color = '#f1f5f9'
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    # -------------------------------------------------------------------------
    # 1. ENCABEZADO SUPERIOR DEL DIAGRAMA RELACIONAL
    # -------------------------------------------------------------------------
    banner = patches.FancyBboxPatch(
        (0.8, fig_h - 2.65), fig_w - 1.6, 1.95,
        boxstyle="round,pad=0.25,rounding_size=0.35",
        facecolor='#0f172a', edgecolor='#020617', linewidth=2.5, zorder=2
    )
    ax.add_patch(banner)

    # Acento cian/azul moderno
    blue_bar = patches.Rectangle(
        (1.0, fig_h - 2.70), fig_w - 2.0, 0.12,
        facecolor='#38bdf8', edgecolor='none', zorder=3
    )
    ax.add_patch(blue_bar)

    ax.text(
        fig_w / 2, fig_h - 1.4,
        "DIAGRAMA DEL MODELO RELACIONAL — SISTEMA SAFARI POS",
        fontsize=24, fontweight='bold', color='#ffffff', ha='center', va='center', zorder=4
    )
    ax.text(
        fig_w / 2, fig_h - 2.0,
        "Esquema Físico y Relacional Normalizado en 3FN | Base de Datos: `proyecto` | Motor: MySQL 8.0+ InnoDB | Charset: utf8mb4_unicode_ci",
        fontsize=13.5, color='#94a3b8', ha='center', va='center', zorder=4
    )

    # -------------------------------------------------------------------------
    # 2. DEFINICIÓN DE TABLAS CON POSICIONES Y FILAS EXACTAS
    # -------------------------------------------------------------------------
    # Estructura en 4 columnas perfectamente distribuidas
    tablas = {
        # --- COLUMNA 1 (x = 2.0): Usuarios, Auditoría y Categorías ---
        'Usuario': {
            'x': 2.0, 'y': 24.0, 'w': 7.4, 'h': 6.6,
            'color': '#1e293b', 'header_accent': '#38bdf8',
            'sub': 'Entidad de Colaboradores y Autenticación',
            'fields': [
                ('PK', 'id', 'BIGINT', 'NOT NULL AUTO_INCREMENT'),
                ('  ', 'rut', 'VARCHAR(20)', "NOT NULL DEFAULT ''"),
                ('  ', 'nombre', 'VARCHAR(100)', 'NOT NULL'),
                ('UK', 'correo', 'VARCHAR(254)', 'NOT NULL UNIQUE'),
                ('UK', 'username', 'VARCHAR(50)', 'NOT NULL UNIQUE'),
                ('  ', 'password', 'VARCHAR(128)', 'NOT NULL (Hash)'),
                ('  ', 'rol', 'VARCHAR(50)', "NOT NULL DEFAULT 'cajero'"),
                ('  ', 'estado', 'VARCHAR(20)', "NOT NULL DEFAULT 'activo'"),
            ]
        },
        'HistorialAccion': {
            'x': 2.0, 'y': 15.6, 'w': 7.4, 'h': 5.4,
            'color': '#312e81', 'header_accent': '#818cf8',
            'sub': 'Bitácora de Auditoría del Sistema',
            'fields': [
                ('PK', 'id', 'BIGINT', 'NOT NULL AUTO_INCREMENT'),
                ('FK', 'usuario_id', 'BIGINT', 'NULL -> Safari_usuario(id)'),
                ('  ', 'accion', 'VARCHAR(50)', 'NOT NULL (CREAR/ACT...)'),
                ('  ', 'modulo', 'VARCHAR(50)', 'NOT NULL'),
                ('  ', 'detalle', 'LONGTEXT', "NOT NULL DEFAULT ''"),
                ('  ', 'fecha', 'DATETIME(6)', 'NOT NULL (Timestamp)'),
            ]
        },
        'Menu': {
            'x': 2.0, 'y': 8.6, 'w': 7.4, 'h': 4.8,
            'color': '#78350f', 'header_accent': '#fbbf24',
            'sub': 'Secciones de Carta Gastronómica',
            'fields': [
                ('PK', 'id', 'BIGINT', 'NOT NULL AUTO_INCREMENT'),
                ('  ', 'nombre', 'VARCHAR(100)', 'NOT NULL'),
                ('  ', 'descripcion', 'VARCHAR(255)', "NOT NULL DEFAULT ''"),
                ('  ', 'estado', 'VARCHAR(20)', "NOT NULL DEFAULT 'activo'"),
            ]
        },

        # --- COLUMNA 2 (x = 12.0): Puntos de Venta, Control de Caja y Productos ---
        'PuntoDeVenta': {
            'x': 12.0, 'y': 24.0, 'w': 7.6, 'h': 4.8,
            'color': '#0369a1', 'header_accent': '#38bdf8',
            'sub': 'Terminales de Cobro / Cajas Físicas',
            'fields': [
                ('PK', 'id', 'BIGINT', 'NOT NULL AUTO_INCREMENT'),
                ('  ', 'nombre', 'VARCHAR(100)', 'NOT NULL'),
                ('  ', 'ubicacion', 'VARCHAR(100)', "NOT NULL DEFAULT ''"),
                ('  ', 'estado', 'VARCHAR(20)', "NOT NULL DEFAULT 'activo'"),
            ]
        },
        'ControlCaja': {
            'x': 12.0, 'y': 17.5, 'w': 7.8, 'h': 8.8,
            'color': '#065f46', 'header_accent': '#34d399',
            'sub': 'Apertura, Cierre y Arqueo de Turnos',
            'fields': [
                ('PK', 'id', 'BIGINT', 'NOT NULL AUTO_INCREMENT'),
                ('  ', 'abierta', 'TINYINT(1)', 'NOT NULL DEFAULT 1'),
                ('  ', 'fecha_apertura', 'DATETIME(6)', 'NOT NULL'),
                ('  ', 'fecha_cierre', 'DATETIME(6)', 'NULL'),
                ('FK', 'cajero_responsable_id', 'BIGINT', 'NULL -> Safari_usuario(id)'),
                ('FK', 'cerrada_por_id', 'BIGINT', 'NULL -> Safari_usuario(id)'),
                ('FK', 'punto_de_venta_id', 'BIGINT', 'NULL -> Safari_puntodeventa(id)'),
                ('  ', 'monto_inicial', 'DECIMAL(10,2)', 'NOT NULL DEFAULT 0.00'),
                ('  ', 'total_ventas', 'DECIMAL(10,2)', 'NOT NULL DEFAULT 0.00'),
                ('  ', 'total_efectivo', 'DECIMAL(10,2)', 'NOT NULL DEFAULT 0.00'),
                ('  ', 'total_tarjeta', 'DECIMAL(10,2)', 'NOT NULL DEFAULT 0.00'),
                ('  ', 'total_transferencia', 'DECIMAL(10,2)', 'NOT NULL DEFAULT 0.00'),
                ('  ', 'monto_real', 'DECIMAL(10,2)', 'NULL (Conteo físico)'),
                ('  ', 'diferencia', 'DECIMAL(10,2)', 'NULL (Sobrante/Faltante)'),
            ]
        },
        'Producto': {
            'x': 12.0, 'y': 7.0, 'w': 7.8, 'h': 5.8,
            'color': '#831843', 'header_accent': '#f472b6',
            'sub': 'Catálogo de Platos y Bebestibles',
            'fields': [
                ('PK', 'id', 'BIGINT', 'NOT NULL AUTO_INCREMENT'),
                ('  ', 'codigo', 'VARCHAR(50)', "NOT NULL DEFAULT '' (SKU)"),
                ('  ', 'nombre', 'VARCHAR(100)', 'NOT NULL'),
                ('  ', 'descripcion', 'VARCHAR(255)', "NOT NULL DEFAULT ''"),
                ('  ', 'precio', 'DECIMAL(10,2)', 'NOT NULL (Precio CLP)'),
                ('  ', 'stock', 'INT(11)', 'NOT NULL DEFAULT 0'),
                ('FK', 'menu_id', 'BIGINT', 'NULL -> Safari_menu(id)'),
            ]
        },

        # --- COLUMNA 3 (x = 22.6): Ventas y Detalle de Venta ---
        'Venta': {
            'x': 22.6, 'y': 18.2, 'w': 8.0, 'h': 6.8,
            'color': '#1e3a8a', 'header_accent': '#60a5fa',
            'sub': 'Cabecera de Boletas Transaccionales',
            'fields': [
                ('PK', 'id', 'BIGINT', 'NOT NULL AUTO_INCREMENT'),
                ('  ', 'fecha', 'DATETIME(6)', 'NOT NULL (Timestamp)'),
                ('  ', 'total', 'DECIMAL(10,2)', 'NOT NULL DEFAULT 0.00'),
                ('  ', 'metodo_pago', 'VARCHAR(20)', "NOT NULL DEFAULT 'efectivo'"),
                ('FK', 'usuario_id', 'BIGINT', 'NULL -> Safari_usuario(id) [Cajero]'),
                ('FK', 'mesero_id', 'BIGINT', 'NULL -> Safari_usuario(id) [Mesero]'),
                ('FK', 'control_caja_id', 'BIGINT', 'NULL -> Safari_controlcaja(id)'),
            ]
        },
        'DetalleVenta': {
            'x': 22.6, 'y': 9.6, 'w': 8.0, 'h': 5.4,
            'color': '#c2410c', 'header_accent': '#fb923c',
            'sub': 'Líneas de Detalle / Ítems Vendidos',
            'fields': [
                ('PK', 'id', 'BIGINT', 'NOT NULL AUTO_INCREMENT'),
                ('  ', 'cantidad', 'INT(11)', 'NOT NULL DEFAULT 1'),
                ('  ', 'subtotal', 'DECIMAL(10,2)', 'NOT NULL DEFAULT 0.00'),
                ('FK', 'venta_id', 'BIGINT', 'NOT NULL -> Safari_venta(id)'),
                ('FK', 'producto_id', 'BIGINT', 'NULL -> Safari_producto(id)'),
            ]
        },

        # --- COLUMNA 4 (x = 33.4): Mesas, Comandas y Correlativos ---
        'Mesa': {
            'x': 33.4, 'y': 24.0, 'w': 7.6, 'h': 5.2,
            'color': '#166534', 'header_accent': '#4ade80',
            'sub': 'Mesas del Salón y Comensales',
            'fields': [
                ('PK', 'id', 'BIGINT', 'NOT NULL AUTO_INCREMENT'),
                ('UK', 'numero', 'INT(11)', 'NOT NULL UNIQUE'),
                ('  ', 'nombre', 'VARCHAR(50)', 'NOT NULL'),
                ('  ', 'capacidad', 'INT(11)', 'NOT NULL DEFAULT 4'),
                ('  ', 'estado', 'VARCHAR(20)', "NOT NULL DEFAULT 'disponible'"),
                ('  ', 'comida_entregada', 'TINYINT(1)', 'NOT NULL DEFAULT 0'),
            ]
        },
        'Comanda': {
            'x': 33.4, 'y': 17.2, 'w': 7.6, 'h': 5.8,
            'color': '#991b1b', 'header_accent': '#f87171',
            'sub': 'Monitor de Cocina y Despacho',
            'fields': [
                ('PK', 'id', 'BIGINT', 'NOT NULL AUTO_INCREMENT'),
                ('  ', 'folio', 'VARCHAR(50)', 'NOT NULL (BOL-XXXX)'),
                ('  ', 'mesa', 'VARCHAR(50)', "NOT NULL DEFAULT 'Mesa 1'"),
                ('  ', 'items', 'LONGTEXT', 'NOT NULL (Detalle)'),
                ('  ', 'total', 'DECIMAL(10,2)', 'NOT NULL DEFAULT 0.00'),
                ('  ', 'estado', 'VARCHAR(20)', "NOT NULL DEFAULT 'preparacion'"),
                ('  ', 'fecha', 'DATETIME(6)', 'NOT NULL (Timestamp)'),
            ]
        },
        'SecuenciaFolio': {
            'x': 33.4, 'y': 9.6, 'w': 7.6, 'h': 4.4,
            'color': '#334155', 'header_accent': '#94a3b8',
            'sub': 'Control Atómico de Correlativos',
            'fields': [
                ('PK', 'id', 'BIGINT', 'NOT NULL AUTO_INCREMENT'),
                ('UK', 'tipo', 'VARCHAR(20)', "NOT NULL UNIQUE ('venta'/'comanda')"),
                ('  ', 'ultimo_numero', 'INT UNSIGNED', 'NOT NULL DEFAULT 0'),
            ]
        }
    }

    # -------------------------------------------------------------------------
    # 3. RENDERIZADO VISUAL DE TABLAS RELACIONALES
    # -------------------------------------------------------------------------
    for t_name, data in tablas.items():
        x = data['x']
        y = data['y']
        w = data['w']
        h = data['h']
        color = data['color']
        fields = data['fields']
        sub = data['sub']
        accent = data['header_accent']

        # Sombra sutil exterior
        shadow = patches.FancyBboxPatch(
            (x + 0.12, y - h - 0.12), w, h,
            boxstyle="round,pad=0.1,rounding_size=0.25",
            facecolor='#0f172a', alpha=0.08, edgecolor='none', zorder=2
        )
        ax.add_patch(shadow)

        # Contenedor principal de la tabla
        body = patches.FancyBboxPatch(
            (x, y - h), w, h,
            boxstyle="round,pad=0.1,rounding_size=0.25",
            facecolor='#ffffff', edgecolor='#cbd5e1', linewidth=1.8, zorder=3
        )
        ax.add_patch(body)

        # Cabecera de la tabla
        header_h = 1.2
        header = patches.FancyBboxPatch(
            (x, y - header_h), w, header_h,
            boxstyle="round,pad=0.08,rounding_size=0.25",
            facecolor=color, edgecolor=color, linewidth=1, zorder=4
        )
        ax.add_patch(header)

        # Nivelación inferior de la cabecera
        header_bottom = patches.Rectangle(
            (x, y - header_h), w, 0.3,
            facecolor=color, edgecolor='none', zorder=5
        )
        ax.add_patch(header_bottom)

        # Barra decorativa de color en el borde de la cabecera
        bar_accent = patches.Rectangle(
            (x + 0.15, y - header_h + 0.05), w - 0.3, 0.06,
            facecolor=accent, edgecolor='none', zorder=6
        )
        ax.add_patch(bar_accent)

        # Nombre de la tabla en base de datos
        ax.text(
            x + w / 2, y - 0.45,
            f"TABLE `Safari_{t_name.lower()}`",
            fontsize=12.5, fontweight='bold', color='#ffffff', ha='center', va='center', zorder=7
        )
        ax.text(
            x + w / 2, y - 0.85,
            sub,
            fontsize=9.0, color='#cbd5e1', ha='center', va='center', zorder=7
        )

        # Renderizar filas con formato de columnas de BD
        row_count = len(fields)
        row_space = (h - header_h - 0.35) / max(row_count, 1)

        for i, (key_type, f_name, f_type, f_extra) in enumerate(fields):
            row_y = y - header_h - 0.28 - (i * row_space)

            # Fondo alternado para legibilidad
            if i % 2 == 1:
                bg_row = patches.Rectangle(
                    (x + 0.05, row_y - row_space + 0.12), w - 0.1, row_space,
                    facecolor='#f8fafc', edgecolor='none', zorder=4
                )
                ax.add_patch(bg_row)

            # Badges de Claves
            if key_type == 'PK':
                badge = patches.FancyBboxPatch(
                    (x + 0.22, row_y - 0.18), 0.72, 0.36,
                    boxstyle="round,pad=0.02,rounding_size=0.08",
                    facecolor='#f59e0b', edgecolor='#d97706', linewidth=0.9, zorder=6
                )
                ax.add_patch(badge)
                ax.text(x + 0.58, row_y, "PK", fontsize=8, fontweight='bold', color='#78350f', ha='center', va='center', zorder=7)
            elif key_type == 'FK':
                badge = patches.FancyBboxPatch(
                    (x + 0.22, row_y - 0.18), 0.72, 0.36,
                    boxstyle="round,pad=0.02,rounding_size=0.08",
                    facecolor='#0284c7', edgecolor='#0369a1', linewidth=0.9, zorder=6
                )
                ax.add_patch(badge)
                ax.text(x + 0.58, row_y, "FK", fontsize=8, fontweight='bold', color='#ffffff', ha='center', va='center', zorder=7)
            elif key_type == 'UK':
                badge = patches.FancyBboxPatch(
                    (x + 0.22, row_y - 0.18), 0.72, 0.36,
                    boxstyle="round,pad=0.02,rounding_size=0.08",
                    facecolor='#10b981', edgecolor='#059669', linewidth=0.9, zorder=6
                )
                ax.add_patch(badge)
                ax.text(x + 0.58, row_y, "UK", fontsize=8, fontweight='bold', color='#ffffff', ha='center', va='center', zorder=7)

            # Nombre de la columna
            font_weight = 'bold' if key_type in ['PK', 'FK', 'UK'] else 'normal'
            font_color = '#0f172a' if key_type in ['PK', 'FK', 'UK'] else '#334155'
            ax.text(x + 1.1, row_y, f_name, fontsize=9.2, fontweight=font_weight, color=font_color, va='center', zorder=7)

            # Tipo SQL y constraints a la derecha
            tipo_sql = f"{f_type}  {f_extra}"
            ax.text(x + w - 0.25, row_y, tipo_sql, fontsize=7.8, color='#64748b', ha='right', va='center', zorder=7)

    # -------------------------------------------------------------------------
    # 4. CONECTORES RELACIONALES (INTEGRIDAD REFERENCIAL FK -> PK)
    # -------------------------------------------------------------------------
    # Conectores limpios sin colisión entre entidades
    relaciones_relacionales = [
        # 1. Safari_historialaccion(usuario_id) -> Safari_usuario(id)
        {
            'pts': [(5.7, 24.0 - 6.6), (5.7, 15.6)],
            'card_pk': '1 (PK)', 'pos_pk': (6.0, 17.2),
            'card_fk': 'N (FK)', 'pos_fk': (6.0, 15.8),
            'label': 'FK: usuario_id -> PK: id', 'lbl_pos': (5.7, 16.5),
            'color': '#4338ca'
        },
        # 2. Safari_controlcaja(punto_de_venta_id) -> Safari_puntodeventa(id)
        {
            'pts': [(15.8, 24.0 - 4.8), (15.8, 17.5)],
            'card_pk': '1 (PK)', 'pos_pk': (16.1, 19.0),
            'card_fk': 'N (FK)', 'pos_fk': (16.1, 17.7),
            'label': 'FK: punto_de_venta_id -> PK: id', 'lbl_pos': (15.8, 18.35),
            'color': '#0284c7'
        },
        # 3. Safari_controlcaja(cajero_responsable_id) -> Safari_usuario(id)
        {
            'pts': [(9.4, 20.0), (10.7, 20.0), (10.7, 14.5), (12.0, 14.5)],
            'card_pk': '1 (PK)', 'pos_pk': (9.7, 20.3),
            'card_fk': 'N (FK)', 'pos_fk': (11.6, 14.8),
            'label': 'FK: cajero_id -> PK: id', 'lbl_pos': (10.7, 17.2),
            'color': '#0d9488'
        },
        # 4. Safari_producto(menu_id) -> Safari_menu(id)
        {
            'pts': [(9.4, 6.0), (12.0, 6.0)],
            'card_pk': '1 (PK)', 'pos_pk': (9.7, 6.3),
            'card_fk': 'N (FK)', 'pos_fk': (11.6, 6.3),
            'label': 'FK: menu_id -> PK: id', 'lbl_pos': (10.7, 6.0),
            'color': '#b45309'
        },
        # 5. Safari_venta(control_caja_id) -> Safari_controlcaja(id)
        {
            'pts': [(19.8, 14.8), (22.6, 14.8)],
            'card_pk': '1 (PK)', 'pos_pk': (20.1, 15.1),
            'card_fk': 'N (FK)', 'pos_fk': (22.2, 15.1),
            'label': 'FK: control_caja_id -> PK: id', 'lbl_pos': (21.2, 14.8),
            'color': '#0d9488'
        },
        # 6. Safari_venta(usuario_id) -> Safari_usuario(id) [Corredor superior]
        {
            'pts': [(5.7, 24.0), (5.7, 25.0), (26.6, 25.0), (26.6, 18.2)],
            'card_pk': '1 (PK)', 'pos_pk': (6.0, 24.3),
            'card_fk': 'N (FK)', 'pos_fk': (26.9, 18.5),
            'label': 'FK: usuario_id / mesero_id -> PK: id', 'lbl_pos': (16.2, 25.0),
            'color': '#1e3a8a'
        },
        # 7. Safari_detalleventa(venta_id) -> Safari_venta(id)
        {
            'pts': [(26.6, 18.2 - 6.8), (26.6, 9.6)],
            'card_pk': '1 (PK)', 'pos_pk': (26.9, 11.2),
            'card_fk': 'N (FK)', 'pos_fk': (26.9, 9.8),
            'label': 'FK: venta_id -> PK: id [CASCADE]', 'lbl_pos': (26.6, 10.5),
            'color': '#c2410c'
        },
        # 8. Safari_detalleventa(producto_id) -> Safari_producto(id)
        {
            'pts': [(19.8, 4.3), (21.2, 4.3), (21.2, 7.0), (22.6, 7.0)],
            'card_pk': '1 (PK)', 'pos_pk': (20.1, 4.6),
            'card_fk': 'N (FK)', 'pos_fk': (22.2, 7.3),
            'label': 'FK: producto_id -> PK: id', 'lbl_pos': (21.2, 5.65),
            'color': '#831843'
        },
        # 9. Flujo Relacional Operativo: Safari_venta -> Safari_comanda
        {
            'pts': [(30.6, 14.3), (33.4, 14.3)],
            'card_pk': '1', 'pos_pk': (30.9, 14.6),
            'card_fk': '1', 'pos_fk': (33.0, 14.6),
            'label': 'Genera Comanda (Folio)', 'lbl_pos': (32.0, 14.3),
            'color': '#991b1b'
        },
        # 10. Flujo Relacional Operativo: Safari_mesa -> Safari_comanda
        {
            'pts': [(37.2, 24.0 - 5.2), (37.2, 17.2)],
            'card_pk': '1', 'pos_pk': (37.5, 18.6),
            'card_fk': 'N', 'pos_fk': (37.5, 17.4),
            'label': 'Asocia Mesa Salón', 'lbl_pos': (37.2, 18.0),
            'color': '#166534'
        }
    ]

    for rel in relaciones_relacionales:
        pts = rel['pts']
        c = rel['color']
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]

        # Trazo de la línea de relación
        ax.plot(xs, ys, color=c, linewidth=2.4, linestyle='-', zorder=4, alpha=0.92)

        # Punto circular en la tabla referenciada (PK)
        ax.scatter([xs[0]], [ys[0]], color=c, s=44, zorder=5)

        # Flecha indicadora en la clave foránea (FK)
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

        # Etiquetas cardinales
        ax.text(rel['pos_pk'][0], rel['pos_pk'][1], rel['card_pk'], fontsize=10.5, fontweight='bold', color=c, zorder=7)
        ax.text(rel['pos_fk'][0], rel['pos_fk'][1], rel['card_fk'], fontsize=10.5, fontweight='bold', color=c, zorder=7)

        # Etiqueta descriptiva centrada
        lbl_x, lbl_y = rel['lbl_pos']
        lbl_box = patches.FancyBboxPatch(
            (lbl_x - 1.25, lbl_y - 0.26), 2.5, 0.52,
            boxstyle="round,pad=0.03,rounding_size=0.12",
            facecolor='#ffffff', edgecolor=c, linewidth=1.1, zorder=5
        )
        ax.add_patch(lbl_box)
        ax.text(lbl_x, lbl_y, rel['label'], fontsize=8.0, fontweight='bold', color=c, ha='center', va='center', zorder=6)

    # -------------------------------------------------------------------------
    # 5. PANEL DE LEYENDA TÉCNICA Y NORMALIZACIÓN (PIE DE PÁGINA)
    # -------------------------------------------------------------------------
    pie_y = 0.8
    pie_h = 2.4
    panel_pie = patches.FancyBboxPatch(
        (0.8, pie_y), fig_w - 1.6, pie_h,
        boxstyle="round,pad=0.2,rounding_size=0.3",
        facecolor='#ffffff', edgecolor='#cbd5e1', linewidth=1.6, zorder=2
    )
    ax.add_patch(panel_pie)

    # Encabezado de la leyenda
    ax.text(1.2, pie_y + pie_h - 0.45, "CONVENCIONES TÉCNICAS DEL MODELO RELACIONAL:", fontsize=11.5, fontweight='bold', color='#0f172a', va='center')

    # Badges explicativos
    ax.add_patch(patches.FancyBboxPatch((1.2, pie_y + 0.95), 0.75, 0.38, boxstyle="round,pad=0.02,rounding_size=0.08", facecolor='#f59e0b', edgecolor='#d97706', zorder=3))
    ax.text(1.57, pie_y + 1.14, "PK", fontsize=8.5, fontweight='bold', color='#78350f', ha='center', va='center')
    ax.text(2.15, pie_y + 1.14, "Primary Key (Clave Primaria Autoincremental)", fontsize=9.5, color='#334155', va='center')

    ax.add_patch(patches.FancyBboxPatch((8.8, pie_y + 0.95), 0.75, 0.38, boxstyle="round,pad=0.02,rounding_size=0.08", facecolor='#0284c7', edgecolor='#0369a1', zorder=3))
    ax.text(9.17, pie_y + 1.14, "FK", fontsize=8.5, fontweight='bold', color='#ffffff', ha='center', va='center')
    ax.text(9.75, pie_y + 1.14, "Foreign Key (Integridad Referencial con Restricciones ON DELETE / ON UPDATE)", fontsize=9.5, color='#334155', va='center')

    ax.add_patch(patches.FancyBboxPatch((19.5, pie_y + 0.95), 0.75, 0.38, boxstyle="round,pad=0.02,rounding_size=0.08", facecolor='#10b981', edgecolor='#059669', zorder=3))
    ax.text(19.87, pie_y + 1.14, "UK", fontsize=8.5, fontweight='bold', color='#ffffff', ha='center', va='center')
    ax.text(20.45, pie_y + 1.14, "Unique Key (Restricción de Valor Único en Tabla)", fontsize=9.5, color='#334155', va='center')

    ax.text(29.0, pie_y + 1.14, "Normalización: 1FN (Atomicidad) | 2FN (Dependencia Total) | 3FN (Sin Transitividad)", fontsize=9.5, fontweight='bold', color='#0f172a', va='center')

    # Especificaciones técnicas
    spec_text = (
        "• Arquitectura Relacional: Motor MySQL 8.0+ / MariaDB 10.4+  |  Motor de Almacenamiento: InnoDB (Transaccional ACID, Soporte Foráneo Físico)\n"
        "• Paridad Código-Datos: 1:1 con Django ORM (Safari/models.py) y DDL (proyecto_mysql_workbench.sql)  |  Total: 11 Tablas Físicas"
    )
    ax.text(1.2, pie_y + 0.45, spec_text, fontsize=9.0, color='#64748b', va='center')

    # Guardado de archivos
    ruta_1 = os.path.abspath("diagrama_modelo_relacional.png")
    ruta_2 = os.path.abspath("proyecto_safari/diagrama_modelo_relacional.png")

    plt.tight_layout()
    plt.savefig(ruta_1, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    if os.path.exists("proyecto_safari"):
        plt.savefig(ruta_2, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')

    ruta_artifacts = os.environ.get('ARTIFACTS_DIR', '')
    if ruta_artifacts and os.path.exists(ruta_artifacts):
        plt.savefig(os.path.join(ruta_artifacts, "diagrama_modelo_relacional.png"), dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

    print(f"Diagrama del Modelo Relacional exportado exitosamente en:\n1. {ruta_1}\n2. {ruta_2}")

if __name__ == '__main__':
    generar_diagrama_relacional()
