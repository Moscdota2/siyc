import sqlite3
import os

def migrate():
    db_path = 'bar.db'
    
    if not os.path.exists(db_path):
        print(f"Base de datos no encontrada en {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check current payment table structure
    cursor.execute("PRAGMA table_info(payment)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    print(f"Columnas actuales en 'payment': {existing_columns}")

    # Add missing columns to payment table
    if 'currency' not in existing_columns:
        try:
            print("Intentando agregar columna 'currency' a 'payment'...")
            cursor.execute("ALTER TABLE payment ADD COLUMN currency VARCHAR(3) DEFAULT 'usd'")
            print("✅ Columna 'currency' agregada exitosamente.")
        except sqlite3.OperationalError as e:
            print(f"❌ Error al migrar currency: {e}")

    if 'exchange_rate' not in existing_columns:
        try:
            print("Intentando agregar columna 'exchange_rate' a 'payment'...")
            cursor.execute("ALTER TABLE payment ADD COLUMN exchange_rate REAL")
            print("✅ Columna 'exchange_rate' agregada exitosamente.")
        except sqlite3.OperationalError as e:
            print(f"❌ Error al migrar exchange_rate: {e}")

    if 'registered_by' not in existing_columns:
        try:
            print("Intentando agregar columna 'registered_by' a 'payment'...")
            cursor.execute("ALTER TABLE payment ADD COLUMN registered_by INTEGER REFERENCES user(id)")
            print("✅ Columna 'registered_by' agregada exitosamente.")
        except sqlite3.OperationalError as e:
            print(f"❌ Error al migrar registered_by: {e}")

    if 'notes' not in existing_columns:
        try:
            print("Intentando agregar columna 'notes' a 'payment'...")
            cursor.execute("ALTER TABLE payment ADD COLUMN notes VARCHAR(200)")
            print("✅ Columna 'notes' agregada exitosamente.")
        except sqlite3.OperationalError as e:
            print(f"❌ Error al migrar notes: {e}")

    if 'closure_id' not in existing_columns:
        try:
            print("Intentando agregar columna 'closure_id' a 'payment'...")
            cursor.execute("ALTER TABLE payment ADD COLUMN closure_id INTEGER REFERENCES daily_closure(id)")
            print("✅ Columna 'closure_id' agregada exitosamente.")
        except sqlite3.OperationalError as e:
            print(f"❌ Error al migrar closure_id: {e}")

    # Add total_paid fields to Order table
    cursor.execute("PRAGMA table_info('order')")
    order_columns = [row[1] for row in cursor.fetchall()]
    
    if 'total_paid_usd' not in order_columns:
        try:
            print("Intentando agregar columna 'total_paid_usd' a 'order'...")
            cursor.execute("ALTER TABLE 'order' ADD COLUMN total_paid_usd REAL DEFAULT 0.0")
            print("✅ Columna 'total_paid_usd' agregada exitosamente.")
        except sqlite3.OperationalError as e:
            print(f"❌ Error al migrar total_paid_usd: {e}")

    if 'total_paid_bs' not in order_columns:
        try:
            print("Intentando agregar columna 'total_paid_bs' a 'order'...")
            cursor.execute("ALTER TABLE 'order' ADD COLUMN total_paid_bs REAL DEFAULT 0.0")
            print("✅ Columna 'total_paid_bs' agregada exitosamente.")
        except sqlite3.OperationalError as e:
            print(f"❌ Error al migrar total_paid_bs: {e}")

    conn.commit()
    conn.close()
    print("\n✅ Migración completada.")

if __name__ == "__main__":
    migrate()
