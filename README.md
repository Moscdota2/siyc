# SIYC - Sistema de Inventario Y Control

SIYC es una aplicación web profesional de gestión de inventario y ventas diseñada para licorerías y bares. Está optimizada para trabajar de forma robusta en entornos con conectividad limitada, ofreciendo gestión bimonetaria (USD/BS) y generación de ejecutables portátiles para Windows.

## 🚀 Características Principales

- **Gestión Bimonetaria:** Manejo automático de precios en Dólares (USD) y Bolívares (BS) con integración a la tasa oficial del BCV y opción manual.
- **Módulo de Ventas:** Control de mesas, órdenes de barra y gestión de combos dinámicos.
- **Inventario Total:** Seguimiento detallado de entradas, salidas manuales y movimientos históricos.
- **Resiliencia API:** Capacidad de funcionamiento 100% offline con fallbacks automáticos para la tasa de cambio.
- **Portabilidad:** Generación de un solo archivo `.exe` que incluye todas las dependencias (Python + Librerías).
- **Arquitectura Modular:** Código limpio organizado mediante Flask Blueprints para fácil mantenimiento.

## 🛠️ Requisitos del Sistema

- **Desarrollo:** Python 3.10+
- **Producción:** Windows 10/11 (utilizando el ejecutable generado).

## 📥 Instalación (Desarrollo)

1. Clonar el repositorio:
   ```bash
   git clone https://github.com/usuario/siyc.git
   cd siyc
   ```
2. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
3. Ejecutar la aplicación:
   ```bash
   python py_app.py
   ```

## 🏗️ Generar Ejecutable para Windows

Para crear la versión portátil sin dependencias externas:

1. Asegúrate de estar en Windows.
2. Ejecuta el script de construcción:
   ```bash
   python build_exe.py
   ```
3. El archivo final se encontrará en la carpeta `dist/SIYC.exe`.

## 📂 Estructura del Proyecto

- `py_app.py`: Punto de entrada de la aplicación.
- `routes/`: Módulos de rutas (Auth, Inventario, Ventas).
- `templates/`: Plantillas HTML dinámicas.
- `static/`: Recursos CSS, JS e imágenes.
- `py_models.py`: Definición de la base de datos y lógica de negocio.
- `py_exchange.py`: Lógica de tasa de cambio y base de datos compartida.

## 🔒 Seguridad

- Autenticación segura con Roles (Admin, Manager, Staff).
- Encriptación de contraseñas mediante Werkzeug.
- Persistencia de datos en SQLite local.

---
© 2026 SIYC Team
