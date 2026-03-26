from flask import Flask, redirect, url_for, render_template
from flask_login import LoginManager
from flask_migrate import Migrate
from exchange import db, init_exchange_rate
from models import User, Table, PaymentMethod, Product, create_initial_products
from sqlalchemy.engine import Engine
from sqlalchemy import event
import os
import sys

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# --- Blueprints ---
from routes.auth import auth_bp
from routes.inventory import inventory_bp
from routes.sales import sales_bp

def get_base_path():
    """Determine base path for templates and static files (PyInstaller support)."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.abspath(os.path.dirname(__file__))

def get_data_path():
    """Determine path for persistent data (SQLite database)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.dirname(__file__))

base_path = get_base_path()
data_path = get_data_path()

app = Flask(__name__, 
            template_folder=os.path.join(base_path, 'templates'),
            static_folder=os.path.join(base_path, 'static'))

db_path = os.path.join(data_path, 'bar.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SECRET_KEY'] = 'mysecretkey'
db.init_app(app)

# Initialize Flask-Migrate
migrate = Migrate(app, db)

# Login Configuration
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login."""
    return db.session.get(User, int(user_id))

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(inventory_bp)
app.register_blueprint(sales_bp)

def setup_database(app):
    """Ensure database is initialized and seeded."""
    with app.app_context():
        db.create_all()
        
        # Safe schema update for inventory_movement
        try:
            result = db.session.execute("PRAGMA table_info('inventory_movement')").fetchall()
            cols = [r[1] for r in result]
            if 'closure_id' not in cols:
                db.session.execute('ALTER TABLE inventory_movement ADD COLUMN closure_id INTEGER')
                db.session.commit()
        except Exception:
            db.session.rollback()

        # Seed initial data if missing
        try:
            create_initial_products()
            
            if not PaymentMethod.query.first():
                db.session.add_all([
                    PaymentMethod(name='Efectivo USD', currency='usd'),
                    PaymentMethod(name='Efectivo BS', currency='bs'),
                    PaymentMethod(name='Pago Móvil', currency='bs'),
                    PaymentMethod(name='Punto de Venta', currency='bs'),
                    PaymentMethod(name='Transferencia', currency='bs')
                ])
            
            if not User.query.first():
                admin = User(username='admin', role='admin')
                admin.set_password('admin123')
                db.session.add(admin)
                
                # Default tables
                for i in range(1, 6):
                    db.session.add(Table(number=str(i)))
            
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Warning: Database seeding failed: {e}")

        # Initialize exchange rate logic
        init_exchange_rate(app)

# Initialize database
setup_database(app)

# Root redirect to sales dashboard
@app.route('/')
def home():
    """Redirect root to the main sales dashboard."""
    return redirect(url_for('sales.index'))

@app.errorhandler(403)
def forbidden_error(error):
    """Render custom 403 Forbidden page."""
    return render_template('403.html'), 403

if __name__ == '__main__':
    is_dev = not getattr(sys, 'frozen', False)
    app.run(debug=is_dev)