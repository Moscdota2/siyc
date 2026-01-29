import PyInstaller.__main__
import os
import shutil

# Este script genera un .exe TOTALMENTE PORTÁTIL.
# El archivo resultante NO necesita que la PC de destino tenga Python ni Pip.
# Todo (Python, librerías, HTML, CSS) se mete dentro del .exe.

def build():
    print("Iniciando proceso de empaquetado para Windows (Portable Mode)...")
    
    # Nombre del ejecutable
    app_name = "SIYC_Inventario"
    
    # Script principal
    main_script = "py_app.py"
    
    # Carpetas a incluir
    # Formato: ('ruta_origen', 'ruta_destino_en_exe')
    added_data = [
        ('templates', 'templates'),
        ('static', 'static'),
        ('instance', 'instance'),
    ]
    
    # Construir el comando de PyInstaller
    params = [
        main_script,
        '--name=%s' % app_name,
        '--onefile',       # Un solo archivo .exe
        '--windowed',      # No abrir consola negra de fondo
        '--clean',
    ]
    
    # PyInstaller on Windows expects ';' as path separator for --add-data,
    # on *nix it's ':'. Use the appropriate sep for the current platform.
    sep = ';' if os.name == 'nt' else ':'
    for src, dest in added_data:
        params.append(f"--add-data={src}{sep}{dest}")

    # Ensure the current directory is on the import path
    params.append('--paths=.')
    
    # Ejecutar PyInstaller
    try:
        PyInstaller.__main__.run(params)
    except Exception as e:
        print('Error al ejecutar PyInstaller:', e)
        raise
    
    print("\n" + "="*50)
    print(f"¡Listo! El ejecutable se encuentra en la carpeta 'dist/{app_name}.exe'")
    print("Recuerda que la base de datos 'bar.db' se creará automáticamente en la misma carpeta.")
    print("="*50)

if __name__ == "__main__":
    build()
