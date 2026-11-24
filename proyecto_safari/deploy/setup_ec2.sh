#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE APROVISIONAMIENTO Y DESPLIEGUE EN AWS EC2 (UBUNTU 22.04 / 24.04 LTS)
# ==============================================================================
set -e

echo "=== [1/7] Actualizando repositorios y paquetes de Ubuntu ==="
sudo apt update && sudo apt upgrade -y

echo "=== [2/7] Instalando paquetes del sistema (Python, drivers MySQL, Nginx) ==="
sudo apt install -y python3-pip python3-venv python3-dev default-libmysqlclient-dev build-essential pkg-config nginx libssl-dev

echo "=== [3/7] Creando entorno virtual de Python ==="
cd "$(dirname "$0")/.."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

echo "=== [4/7] Instalando dependencias desde requirements.txt ==="
pip install --upgrade pip
pip install -r requirements.txt

echo "=== [5/7] Configuración de .env de producción ==="
cd proyecto_safari
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "¡ATENCIÓN! Se creó el archivo .env a partir de .env.example. Por favor configure sus credenciales de base de datos y clave secreta."
fi

echo "=== [6/7] Recopilando archivos estáticos con collectstatic ==="
python manage.py collectstatic --noinput

echo "=== [7/7] Aplicando migraciones de base de datos ==="
python manage.py migrate

echo "=============================================================================="
echo " Safari POS se encuentra listo para iniciar con Gunicorn y Nginx."
echo " Inicie el servicio con: sudo systemctl start gunicorn"
echo "=============================================================================="
