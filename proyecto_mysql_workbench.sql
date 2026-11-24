-- =============================================================================
-- SAFARI POS - SCRIPT DDL Y DML PARA MYSQL WORKBENCH
-- Base de Datos: proyecto
-- Motor: MySQL 8.0+ / MariaDB 10.4+ | Charset: utf8mb4 | Collate: utf8mb4_unicode_ci
-- Coincidencia 1:1 con Django ORM (Safari/models.py) y Modelo Entidad-Relación (E-R)
-- =============================================================================

SET NAMES utf8mb4;
SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO';

-- -----------------------------------------------------------------------------
-- 1. CREACIÓN Y SELECCIÓN DE LA BASE DE DATOS
-- -----------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS `proyecto`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `proyecto`;

-- =============================================================================
-- DEFINICIÓN DEL MODELO RELACIONAL (DDL - 1:1 CON Safari/models.py)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- ENTIDAD 1: Safari_usuario
-- Mapea: class Usuario(models.Model)
-- Cardinalidad: 
--   - 1 Usuario -> N Ventas (como Cajero o Mesero)
--   - 1 Usuario -> N Arqueos de Caja (Apertura o Cierre)
--   - 1 Usuario -> N Registros en HistorialAccion (Auditoría)
-- Atributos clave: rut/cédula, nombre, correo, username, password, rol, estado
-- Roles soportados: 'administrador', 'cajero', 'mesero', 'cocinero'
-- Estados: 'activo', 'inactivo'
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `Safari_usuario`;
CREATE TABLE `Safari_usuario` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Clave primaria autoincremental de la entidad Usuario',
  `rut` varchar(20) NOT NULL DEFAULT '' COMMENT 'RUT o cédula de identidad del trabajador',
  `nombre` varchar(100) NOT NULL COMMENT 'Nombre completo del trabajador/usuario',
  `correo` varchar(254) NOT NULL COMMENT 'Correo electrónico corporativo único',
  `username` varchar(50) NOT NULL COMMENT 'Nombre de usuario único para autenticación',
  `password` varchar(128) NOT NULL COMMENT 'Credencial de acceso del usuario',
  `rol` varchar(50) NOT NULL DEFAULT 'cajero' COMMENT 'Rol asignado: administrador, cajero, mesero, cocinero',
  `estado` varchar(20) NOT NULL DEFAULT 'activo' COMMENT 'Estado de la cuenta: activo o inactivo',
  PRIMARY KEY (`id`),
  UNIQUE KEY `correo` (`correo`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Entidad de usuarios del sistema POS Safari';

-- -----------------------------------------------------------------------------
-- ENTIDAD 2: Safari_puntodeventa
-- Mapea: class PuntoDeVenta(models.Model)
-- Cardinalidad: 
--   - 1 PuntoDeVenta -> N Controles de Caja (Turnos asignados a esta caja)
-- Atributos: nombre/identificador de caja, ubicación, estado
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `Safari_puntodeventa`;
CREATE TABLE `Safari_puntodeventa` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Clave primaria del punto de venta',
  `nombre` varchar(100) NOT NULL COMMENT 'Nombre o identificador de caja (ej: Caja Principal, Caja Terraza)',
  `ubicacion` varchar(100) NOT NULL DEFAULT '' COMMENT 'Ubicación física dentro del restaurante',
  `estado` varchar(20) NOT NULL DEFAULT 'activo' COMMENT 'Estado del punto de venta: activo o inactivo',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Puntos de venta físicos o terminales POS';

-- -----------------------------------------------------------------------------
-- ENTIDAD 3: Safari_menu
-- Mapea: class Menu(models.Model)
-- Cardinalidad:
--   - 1 Menu -> N Productos (Categoría a la que pertenece el producto)
-- Atributos: nombre de sección (platos de fondo, bebestibles, postres), descripción, estado
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `Safari_menu`;
CREATE TABLE `Safari_menu` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Clave primaria autoincremental de la categoría/menú',
  `nombre` varchar(100) NOT NULL COMMENT 'Nombre de sección (Platos de fondo, Bebestibles, Postres, etc.)',
  `descripcion` varchar(255) NOT NULL DEFAULT '' COMMENT 'Descripción breve de la categoría gastronómica',
  `estado` varchar(20) NOT NULL DEFAULT 'activo' COMMENT 'Estado de la sección: activo o inactivo',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Menús y categorías gastronómicas de la carta';

-- -----------------------------------------------------------------------------
-- ENTIDAD 4: Safari_producto
-- Mapea: class Producto(models.Model)
-- Cardinalidad:
--   - N Productos -> 1 Menu (Categoría gastronómica) [SET NULL]
--   - 1 Producto -> N DetalleVenta [CASCADE]
-- Atributos: código, nombre, descripción, precio, stock, relación FK a Menu
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `Safari_producto`;
CREATE TABLE `Safari_producto` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Clave primaria autoincremental del producto',
  `codigo` varchar(50) NOT NULL DEFAULT '' COMMENT 'Código SKU o identificador del producto',
  `nombre` varchar(100) NOT NULL COMMENT 'Nombre comercial del producto gastronómico',
  `descripcion` varchar(255) NOT NULL DEFAULT '' COMMENT 'Descripción adicional del ítem',
  `precio` decimal(10,2) NOT NULL COMMENT 'Precio unitario de venta al público en CLP',
  `stock` int(11) NOT NULL DEFAULT 0 COMMENT 'Existencias actuales disponibles en cocina/bodega',
  `menu_id` bigint(20) DEFAULT NULL COMMENT 'Clave foránea hacia Safari_menu',
  PRIMARY KEY (`id`),
  KEY `Safari_producto_menu_id_fk` (`menu_id`),
  CONSTRAINT `Safari_producto_menu_id_fk`
    FOREIGN KEY (`menu_id`) REFERENCES `Safari_menu` (`id`)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Catálogo oficial de productos e inventario';

-- -----------------------------------------------------------------------------
-- ENTIDAD 5: Safari_mesa
-- Mapea: class Mesa(models.Model)
-- Cardinalidad: Entidad independiente de salón, referenciada en comandas
-- Atributos: número de mesa, nombre, capacidad de comensales, estado, comida_entregada
-- Estados posibles: 'disponible', 'ocupada', 'reservada' (compatible con 'desocupada')
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `Safari_mesa`;
CREATE TABLE `Safari_mesa` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Clave primaria autoincremental de la mesa',
  `numero` int(11) NOT NULL COMMENT 'Número identificador físico único de la mesa',
  `nombre` varchar(50) NOT NULL COMMENT 'Nombre descriptivo de la mesa (ej. Mesa 1, Terraza 4)',
  `capacidad` int(11) NOT NULL DEFAULT 4 COMMENT 'Capacidad máxima de comensales sentados',
  `estado` varchar(20) NOT NULL DEFAULT 'disponible' COMMENT 'Estado actual: disponible, ocupada, reservada',
  `comida_entregada` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Bandera booleana de confirmación de entrega al comensal',
  PRIMARY KEY (`id`),
  UNIQUE KEY `numero` (`numero`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Salón de mesas, capacidad y estado de ocupación';

-- -----------------------------------------------------------------------------
-- ENTIDAD 6: Safari_historialaccion
-- Mapea: class HistorialAccion(models.Model)
-- Cardinalidad:
--   - N HistorialAccion -> 1 Usuario (Usuario que ejecuta la acción) [SET NULL]
-- Atributos: usuario, acción (CREAR, ACTUALIZAR, ELIMINAR, LOGIN, CIERRE_CAJA),
--            módulo/tabla afectada, detalle breve y fecha/hora
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `Safari_historialaccion`;
CREATE TABLE `Safari_historialaccion` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Clave primaria del registro de auditoría',
  `usuario_id` bigint(20) DEFAULT NULL COMMENT 'Usuario que ejecutó la acción auditada',
  `accion` varchar(50) NOT NULL COMMENT 'Acción: CREAR, ACTUALIZAR, ELIMINAR, LOGIN, CIERRE_CAJA',
  `modulo` varchar(50) NOT NULL COMMENT 'Módulo o tabla afectada (Usuarios, Mesas, Menús, etc.)',
  `detalle` longtext NOT NULL COMMENT 'Detalle descriptivo de la operación',
  `fecha` datetime(6) NOT NULL COMMENT 'Timestamp exacto de la acción',
  PRIMARY KEY (`id`),
  KEY `Safari_historialaccion_usuario_id_fk` (`usuario_id`),
  CONSTRAINT `Safari_historialaccion_usuario_id_fk`
    FOREIGN KEY (`usuario_id`) REFERENCES `Safari_usuario` (`id`)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Registro de auditoría y bitácora de acciones del sistema';

-- -----------------------------------------------------------------------------
-- ENTIDAD 7: Safari_controlcaja
-- Mapea: class ControlCaja(models.Model)
-- Cardinalidad:
--   - N ControlCaja -> 1 Usuario (Cajero responsable de la apertura) [SET NULL]
--   - N ControlCaja -> 1 Usuario (Usuario que efectúa el cierre de caja) [SET NULL]
--   - N ControlCaja -> 1 PuntoDeVenta (Caja asignada) [SET NULL]
--   - 1 ControlCaja -> N Ventas (Ventas realizadas durante el turno) [SET NULL]
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `Safari_controlcaja`;
CREATE TABLE `Safari_controlcaja` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Clave primaria autoincremental del arqueo de caja',
  `abierta` tinyint(1) NOT NULL DEFAULT 1 COMMENT 'Estado del turno: 1=Abierta, 0=Cerrada',
  `fecha_apertura` datetime(6) NOT NULL COMMENT 'Timestamp de inicio de operaciones de caja',
  `fecha_cierre` datetime(6) DEFAULT NULL COMMENT 'Timestamp de cierre y arqueo de caja',
  `cajero_responsable_id` bigint(20) DEFAULT NULL COMMENT 'Cajero responsable que abrió el turno de caja',
  `cerrada_por_id` bigint(20) DEFAULT NULL COMMENT 'Usuario que ejecutó el cierre del turno',
  `punto_de_venta_id` bigint(20) DEFAULT NULL COMMENT 'Punto de venta físico asociado al turno',
  `monto_inicial` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Fondo inicial de caja (efectivo base)',
  `total_ventas` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Suma total de ventas del turno',
  `total_efectivo` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Subtotal recaudado en Efectivo',
  `total_tarjeta` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Subtotal recaudado con Tarjeta Débito/Crédito',
  `total_transferencia` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Subtotal recaudado vía Transferencia',
  `monto_real` decimal(10,2) DEFAULT NULL COMMENT 'Monto físico en efectivo contado por el cajero al cierre',
  `diferencia` decimal(10,2) DEFAULT NULL COMMENT 'Diferencia contable: monto_real - (monto_inicial + total_efectivo)',
  PRIMARY KEY (`id`),
  KEY `Safari_controlcaja_cajero_responsable_id_fk` (`cajero_responsable_id`),
  KEY `Safari_controlcaja_cerrada_por_id_fk` (`cerrada_por_id`),
  KEY `Safari_controlcaja_punto_de_venta_id_fk` (`punto_de_venta_id`),
  CONSTRAINT `Safari_controlcaja_cajero_responsable_id_fk` 
    FOREIGN KEY (`cajero_responsable_id`) REFERENCES `Safari_usuario` (`id`) 
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `Safari_controlcaja_cerrada_por_id_fk` 
    FOREIGN KEY (`cerrada_por_id`) REFERENCES `Safari_usuario` (`id`) 
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `Safari_controlcaja_punto_de_venta_id_fk` 
    FOREIGN KEY (`punto_de_venta_id`) REFERENCES `Safari_puntodeventa` (`id`) 
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Control de turnos, fondo inicial y arqueo de caja';

-- -----------------------------------------------------------------------------
-- ENTIDAD 8: Safari_venta
-- Mapea: class Venta(models.Model)
-- Cardinalidad:
--   - N Ventas -> 1 Usuario (Cajero responsable) [CASCADE]
--   - N Ventas -> 1 Usuario (Mesero asignado) [SET NULL]
--   - N Ventas -> 1 ControlCaja (Turno en que se emitió) [SET NULL]
--   - 1 Venta -> N DetalleVenta [CASCADE]
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `Safari_venta`;
CREATE TABLE `Safari_venta` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Clave primaria autoincremental de la venta',
  `fecha` datetime(6) NOT NULL COMMENT 'Timestamp exacto de la transacción de venta',
  `total` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Monto total pagado de la venta en CLP',
  `usuario_id` bigint(20) DEFAULT NULL COMMENT 'Clave foránea hacia Safari_usuario (cajero)',
  `mesero_id` bigint(20) DEFAULT NULL COMMENT 'Clave foránea hacia Safari_usuario (mesero)',
  `control_caja_id` bigint(20) DEFAULT NULL COMMENT 'Clave foránea hacia Safari_controlcaja (turno activo)',
  `metodo_pago` varchar(20) NOT NULL DEFAULT 'efectivo' COMMENT 'Método de pago: efectivo, tarjeta, transferencia',
  PRIMARY KEY (`id`),
  KEY `Safari_venta_usuario_id_fk_Safari_usuario_id` (`usuario_id`),
  KEY `Safari_venta_mesero_id_fk_Safari_usuario_id` (`mesero_id`),
  KEY `Safari_venta_control_caja_id_fk_Safari_controlcaja_id` (`control_caja_id`),
  CONSTRAINT `Safari_venta_usuario_id_fk_Safari_usuario_id` 
    FOREIGN KEY (`usuario_id`) REFERENCES `Safari_usuario` (`id`) 
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `Safari_venta_mesero_id_fk_Safari_usuario_id` 
    FOREIGN KEY (`mesero_id`) REFERENCES `Safari_usuario` (`id`) 
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `Safari_venta_control_caja_id_fk_Safari_controlcaja_id` 
    FOREIGN KEY (`control_caja_id`) REFERENCES `Safari_controlcaja` (`id`) 
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Registro de transacciones de venta y boletas';

-- -----------------------------------------------------------------------------
-- ENTIDAD 9: Safari_detalleventa
-- Mapea: class DetalleVenta(models.Model)
-- Cardinalidad:
--   - N DetalleVenta -> 1 Venta (Cabecera obligatoria) [CASCADE]
--   - N DetalleVenta -> 1 Producto (Ítem vendido opcional) [CASCADE]
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `Safari_detalleventa`;
CREATE TABLE `Safari_detalleventa` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Clave primaria autoincremental del detalle de venta',
  `cantidad` int(11) NOT NULL DEFAULT 1 COMMENT 'Cantidad de unidades del producto adquiridas',
  `subtotal` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Subtotal calculado (cantidad * precio unitario)',
  `producto_id` bigint(20) DEFAULT NULL COMMENT 'Clave foránea hacia Safari_producto',
  `venta_id` bigint(20) NOT NULL COMMENT 'Clave foránea hacia Safari_venta',
  PRIMARY KEY (`id`),
  KEY `Safari_detalleventa_producto_id_fk_Safari_producto_id` (`producto_id`),
  KEY `Safari_detalleventa_venta_id_fk_Safari_venta_id` (`venta_id`),
  CONSTRAINT `Safari_detalleventa_producto_id_fk_Safari_producto_id` 
    FOREIGN KEY (`producto_id`) REFERENCES `Safari_producto` (`id`) 
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `Safari_detalleventa_venta_id_fk_Safari_venta_id` 
    FOREIGN KEY (`venta_id`) REFERENCES `Safari_venta` (`id`) 
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Líneas de detalle de ítems por venta';

-- -----------------------------------------------------------------------------
-- ENTIDAD 10: Safari_comanda
-- Mapea: class Comanda(models.Model)
-- Cardinalidad: Generada automáticamente al confirmar una venta o pedido de garzón para Cocina
-- Estados posibles: 'en_espera', 'preparacion', 'PREPARANDO', 'listo', 'LISTO', 'entregado', 'ENTREGADO', 'RE_ORDEN'
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `Safari_comanda`;
CREATE TABLE `Safari_comanda` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Clave primaria autoincremental de la comanda',
  `folio` varchar(50) NOT NULL COMMENT 'Folio correlativo visible para cocina (ej. COM-0001 o BOL-0001)',
  `mesa` varchar(50) NOT NULL DEFAULT 'Mesa 1' COMMENT 'Mesa o destino del pedido a despachar',
  `mesa_rel_id` bigint(20) DEFAULT NULL COMMENT 'Clave foránea hacia Safari_mesa',
  `mesero_id` bigint(20) DEFAULT NULL COMMENT 'Clave foránea hacia Safari_usuario (garzón)',
  `venta_id` bigint(20) DEFAULT NULL COMMENT 'Clave foránea hacia Safari_venta (boleta asociada)',
  `items` longtext NOT NULL COMMENT 'Detalle consolidado de productos y cantidades en texto plano',
  `items_json` longtext NOT NULL COMMENT 'Detalle estructurado de ítems en JSON',
  `notas` longtext NOT NULL COMMENT 'Comentarios y especificaciones para cocina',
  `tipo_pedido` varchar(20) NOT NULL DEFAULT 'barra' COMMENT 'Tipo de pedido: barra o mesa',
  `pagada` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Indica si la comanda fue pagada en caja',
  `total` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Monto total de la comanda en CLP',
  `estado` varchar(20) NOT NULL DEFAULT 'preparacion' COMMENT 'Estado: en_espera, preparacion, PREPARANDO, listo, LISTO, entregado, ENTREGADO, RE_ORDEN',
  `es_reemision` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Indica si la comanda fue re-emitida para cambios o recalentados',
  `motivo_reemision` varchar(150) DEFAULT NULL COMMENT 'Motivo del re-hecho o re-emisión',
  `fecha` datetime(6) NOT NULL COMMENT 'Timestamp de creación del pedido en cocina',
  PRIMARY KEY (`id`),
  KEY `Safari_comanda_mesa_rel_id_fk_Safari_mesa_id` (`mesa_rel_id`),
  KEY `Safari_comanda_mesero_id_fk_Safari_usuario_id` (`mesero_id`),
  KEY `Safari_comanda_venta_id_fk_Safari_venta_id` (`venta_id`),
  CONSTRAINT `Safari_comanda_mesa_rel_id_fk_Safari_mesa_id`
    FOREIGN KEY (`mesa_rel_id`) REFERENCES `Safari_mesa` (`id`)
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `Safari_comanda_mesero_id_fk_Safari_usuario_id`
    FOREIGN KEY (`mesero_id`) REFERENCES `Safari_usuario` (`id`)
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `Safari_comanda_venta_id_fk_Safari_venta_id`
    FOREIGN KEY (`venta_id`) REFERENCES `Safari_venta` (`id`)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Monitor de comandas, pedidos y re-órdenes de cocina';

-- -----------------------------------------------------------------------------
-- ENTIDAD 11: Safari_secuenciafolio
-- Mapea: class SecuenciaFolio(models.Model)
-- Descripción: Control atómico concurrente de correlativos para ventas y comandas
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `Safari_secuenciafolio`;
CREATE TABLE `Safari_secuenciafolio` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Clave primaria autoincremental de la secuencia',
  `tipo` varchar(20) NOT NULL COMMENT 'Tipo de comprobante o secuencia (ej. venta, comanda)',
  `ultimo_numero` int(10) unsigned NOT NULL DEFAULT 0 COMMENT 'Último número correlativo entregado',
  PRIMARY KEY (`id`),
  UNIQUE KEY `tipo` (`tipo`),
  CONSTRAINT `chk_secuencia_ultimo_numero` CHECK (`ultimo_numero` >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Generador atómico de secuencias y correlativos';

-- -----------------------------------------------------------------------------
-- TABLA AUXILIAR: django_session
-- Motor de sesiones de Django para persistencia de autenticación HTTP
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `django_session`;
CREATE TABLE `django_session` (
  `session_key` varchar(40) NOT NULL,
  `session_data` longtext NOT NULL,
  `expire_date` datetime(6) NOT NULL,
  PRIMARY KEY (`session_key`),
  KEY `django_session_expire_date_idx` (`expire_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Sesiones de usuario gestionadas por Django';

SET FOREIGN_KEY_CHECKS = 1;

-- =============================================================================
-- INSERCIÓN DE DATOS INICIALES (SEMILLAS DEMO COMPATIBLES)
-- =============================================================================

-- 1. Inserción de Usuarios del Sistema (con RUT y Estado)
INSERT INTO `Safari_usuario` (`id`, `rut`, `nombre`, `correo`, `username`, `password`, `rol`, `estado`) VALUES
(1, '12.345.678-9', 'Administrador General', 'admin@parquesafari.cl', 'admin', 'admin123', 'administrador', 'activo'),
(2, '14.567.890-1', 'Javier Soto (Cajero)', 'caja@parquesafari.cl', 'cajero', 'cajero123', 'cajero', 'activo'),
(3, '16.789.012-3', 'Lucía Morales (Mesera)', 'mesas@parquesafari.cl', 'mesero', 'mesero123', 'mesero', 'activo'),
(4, '18.901.234-5', 'Roberto García (Chef)', 'cocina@parquesafari.cl', 'cocinero', 'cocinero123', 'cocinero', 'activo')
ON DUPLICATE KEY UPDATE 
  `rut`=VALUES(`rut`),
  `nombre`=VALUES(`nombre`),
  `correo`=VALUES(`correo`),
  `password`=VALUES(`password`),
  `rol`=VALUES(`rol`),
  `estado`=VALUES(`estado`);

-- 2. Puntos de Venta (Cajas POS)
INSERT INTO `Safari_puntodeventa` (`id`, `nombre`, `ubicacion`, `estado`) VALUES
(1, 'Caja Principal Salón', 'Acceso Principal Salón Central', 'activo'),
(2, 'Caja Terraza', 'Sector Terraza al Aire Libre', 'activo'),
(3, 'Caja Rápida / Cafetería', 'Barra Lateral de Autoservicio', 'activo')
ON DUPLICATE KEY UPDATE
  `nombre`=VALUES(`nombre`),
  `ubicacion`=VALUES(`ubicacion`),
  `estado`=VALUES(`estado`);

-- 3. Menús y Secciones de la Carta
INSERT INTO `Safari_menu` (`id`, `nombre`, `descripcion`, `estado`) VALUES
(1, 'Platos de Fondo', 'Hamburguesas artesanales, pizzas a la piedra y carnes safari', 'activo'),
(2, 'Bebestibles', 'Refrescos, jugos naturales exprimidos, aguas y cafetería', 'activo'),
(3, 'Postres', 'Helados artesanales, repostería casera y tortas premium', 'activo'),
(4, 'Entradas y Acompañamientos', 'Papas rústicas, aros de cebolla y ensaladas frescas', 'activo')
ON DUPLICATE KEY UPDATE
  `nombre`=VALUES(`nombre`),
  `descripcion`=VALUES(`descripcion`),
  `estado`=VALUES(`estado`);

-- 4. Catálogo Oficial de Productos Gastronómicos (Pesos Chilenos - CLP)
INSERT INTO `Safari_producto` (`id`, `codigo`, `nombre`, `descripcion`, `precio`, `stock`, `menu_id`) VALUES
(1, 'HAM-001', 'Hamburguesa Safari Completa', 'Alimentos', 8500.00, 34, 1),
(2, 'PIZ-002', 'Pizza Mozzarella Personal', 'Alimentos', 7900.00, 25, 1),
(3, 'SAN-003', 'Sándwich de Pollo Especial', 'Alimentos', 6500.00, 30, 1),
(4, 'ENS-004', 'Ensalada César con Pollo', 'Alimentos', 5900.00, 19, 4),
(5, 'PAP-005', 'Papas Fritas Rústicas', 'Alimentos', 3500.00, 50, 4),
(6, 'HOT-006', 'Hot Dog Safari Especial', 'Alimentos', 3900.00, 34, 1),
(7, 'BEB-007', 'Refresco de Cola 600ml', 'Bebidas', 1800.00, 80, 2),
(8, 'BEB-008', 'Jugo Natural de Naranja', 'Bebidas', 2500.00, 40, 2),
(9, 'CAF-009', 'Café Americano Grano', 'Bebidas', 2200.00, 60, 2),
(10, 'BEB-010', 'Agua Mineral 500ml', 'Bebidas', 1500.00, 91, 2),
(11, 'POS-011', 'Croissant con Mantequilla', 'Postres', 2800.00, 18, 3),
(12, 'POS-012', 'Helado Artesanal Safari', 'Postres', 3200.00, 30, 3),
(13, 'POS-013', 'Torta Selva Negra XL', 'Postres Premium', 4800.00, 22, 3)
ON DUPLICATE KEY UPDATE 
  `codigo`=VALUES(`codigo`),
  `descripcion`=VALUES(`descripcion`),
  `precio`=VALUES(`precio`),
  `stock`=VALUES(`stock`),
  `menu_id`=VALUES(`menu_id`);

-- 5. Mesas del Salón Gastronómico (Mesas 1 a 10 con Capacidad)
INSERT INTO `Safari_mesa` (`id`, `numero`, `nombre`, `capacidad`, `estado`, `comida_entregada`) VALUES
(1, 1, 'Mesa 1', 4, 'disponible', 0),
(2, 2, 'Mesa 2', 4, 'disponible', 0),
(3, 3, 'Mesa 3', 2, 'disponible', 0),
(4, 4, 'Mesa 4', 6, 'disponible', 0),
(5, 5, 'Mesa 5', 4, 'disponible', 0),
(6, 6, 'Mesa 6', 8, 'disponible', 0),
(7, 7, 'Mesa 7', 2, 'disponible', 0),
(8, 8, 'Mesa 8', 4, 'disponible', 0),
(9, 9, 'Mesa 9', 6, 'disponible', 0),
(10, 10, 'Mesa 10', 4, 'disponible', 0)
ON DUPLICATE KEY UPDATE 
  `nombre`=VALUES(`nombre`),
  `capacidad`=VALUES(`capacidad`),
  `estado`=VALUES(`estado`),
  `comida_entregada`=VALUES(`comida_entregada`);

-- 6. Secuencias Correlativas de Folios (Venta y Comanda)
INSERT INTO `Safari_secuenciafolio` (`id`, `tipo`, `ultimo_numero`) VALUES
(1, 'venta', 0),
(2, 'comanda', 0)
ON DUPLICATE KEY UPDATE 
  `ultimo_numero`=VALUES(`ultimo_numero`);

-- 7. Control de Caja Inicial (Jornada abierta con cajero, punto de venta y fondo inicial)
INSERT INTO `Safari_controlcaja` (`id`, `abierta`, `fecha_apertura`, `fecha_cierre`, `cajero_responsable_id`, `cerrada_por_id`, `punto_de_venta_id`, `monto_inicial`, `total_ventas`, `total_efectivo`, `total_tarjeta`, `total_transferencia`, `monto_real`, `diferencia`) VALUES
(1, 1, NOW(6), NULL, 2, NULL, 1, 50000.00, 0.00, 0.00, 0.00, 0.00, NULL, NULL)
ON DUPLICATE KEY UPDATE 
  `abierta`=VALUES(`abierta`),
  `punto_de_venta_id`=VALUES(`punto_de_venta_id`),
  `monto_inicial`=VALUES(`monto_inicial`);

-- 8. Auditoría Inicial (Semilla de registro)
INSERT INTO `Safari_historialaccion` (`id`, `usuario_id`, `accion`, `modulo`, `detalle`, `fecha`) VALUES
(1, 1, 'CREAR', 'Sistema', 'Inicialización de módulos y mantenedores del sistema Safari POS', NOW(6))
ON DUPLICATE KEY UPDATE
  `detalle`=VALUES(`detalle`);

-- =============================================================================
-- FIN DEL SCRIPT SQL PARA MYSQL WORKBENCH
-- =============================================================================
