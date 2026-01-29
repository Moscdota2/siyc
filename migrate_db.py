import sqlite3
import os

def migrate():
    # Caminos posibles (local y empaquetado)
    db_path = 'bar.db'
    
    if not os.path.exists(db_path):
        print(f"Base de datos no encontrada en {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Intentar agregar la columna closure_id a inventory_movement
        print("Intentando agregar columna 'closure_id' a 'inventory_movement'...")
        cursor.execute("ALTER TABLE inventory_movement ADD COLUMN closure_id INTEGER REFERENCES daily_closure(id)")
        print("✅ Columna 'closure_id' agregada exitosamente.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("ℹ️ La columna 'closure_id' ya existe.")
        else:
            print(f"❌ Error al migrar closure_id: {e}")

    try:
        # Intentar agregar la columna order_type a orders
        print("Intentando agregar columna 'order_type' a 'order'...")
        cursor.execute("ALTER TABLE 'order' ADD COLUMN order_type VARCHAR(20) DEFAULT 'venta'")
        print("✅ Columna 'order_type' agregada exitosamente.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("ℹ️ La columna 'order_type' ya existe.")
        else:
            print(f"❌ Error al migrar order_type: {e}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
