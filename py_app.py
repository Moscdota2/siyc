from flask import Flask, redirect, url_for, render_template
from flask_login import LoginManager
from py_exchange import db, init_exchange_rate
from py_models import User, Table, PaymentMethod, Product, create_initial_products
import os
import sys

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

# Ensure DB and seed products at app creation so products are present
with app.app_context():
    db.create_all()
    try:
        # Always attempt to seed initial products (function is idempotent
        # and will only add missing entries). This ensures that deleting
        # individual product rows does not permanently remove the default
        # catalog.
        create_initial_products()
        db.session.commit()
    except Exception:
        # If seeding fails, don't crash app import; will attempt on run
        pass

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
    with app.app_context():
        # Ensure database tables exist
        db.create_all()

        # Ensure initial products are seeded (idempotent)
        try:
            create_initial_products()
            db.session.commit()
        except Exception:
            pass

        # Create initial data if the database is empty
        if not PaymentMethod.query.first():
            payment_methods = [
                PaymentMethod(name='Efectivo USD', currency='usd'),
                PaymentMethod(name='Efectivo BS', currency='bs'),
                PaymentMethod(name='Pago Móvil', currency='bs'),
                PaymentMethod(name='Punto de Venta', currency='bs'),
                PaymentMethod(name='Transferencia', currency='bs')
            ]
            db.session.add_all(payment_methods)
        
        if not User.query.first():
            users = [
                User(username='admin', role='admin'),
                User(username='encargado', role='manager'),
                User(username='personal', role='staff')
            ]
            for user in users:
                user.set_password(user.username + '123')
                db.session.add(user)
            
            for i in range(1, 6):
                db.session.add(Table(number=i))
            
            create_initial_products()
            db.session.commit()
            
        # Initialize exchange rate logic
        init_exchange_rate(app)
    
    # Run the application
    is_dev = not getattr(sys, 'frozen', False)
    app.run(debug=is_dev)