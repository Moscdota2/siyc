from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from py_bcv import precio_bcv_actual
import pytz
from py_exchange import db

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(50), nullable=False)
    presentation = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    box_quantity = db.Column(db.Float, nullable=False, default=0.0)
    price_usd = db.Column(db.Float, nullable=False)
    price_bs = db.Column(db.Float, nullable=False)
    is_alcoholic = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_modified_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    modifier = db.relationship('User', backref='modified_products')
    cost_per_unit_usd = db.Column(db.Float)
    last_purchase_price = db.Column(db.Float)
    # Precios especiales para cervezas
    price_unit_usd = db.Column(db.Float)  # Precio por unidad (1 cerveza)
    price_half_tobo_usd = db.Column(db.Float)  # Medio tobo (6 cervezas)
    price_tobo_usd = db.Column(db.Float)  # Tobo completo (12 cervezas)
    price_half_box_usd = db.Column(db.Float)  # Media caja (18 cervezas)
    price_box_usd = db.Column(db.Float)  # Caja completa (36 cervezas)
    
    # Precios en bolívares
    price_unit_bs = db.Column(db.Float)
    price_half_tobo_bs = db.Column(db.Float)
    price_tobo_bs = db.Column(db.Float)
    price_half_box_bs = db.Column(db.Float)
    price_box_bs = db.Column(db.Float)

class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="disponible")
    orders = db.relationship('Order', backref='table', lazy=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey('table.id'), nullable=True)
    total_price = db.Column(db.Float, nullable=False, default=0.0)
    status = db.Column(db.String(20), nullable=False, default="pendiente")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)
    products = db.relationship('OrderDetail', backref='order', lazy=True)
    customer_name = db.Column(db.String(100), nullable=True)
    waiter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    waiter = db.relationship('User', backref='orders')
    payment_method = db.Column(db.String(20), nullable=True)

class OrderDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    subtotal = db.Column(db.Float, nullable=False)
    exit_type = db.Column(db.String(20))
    
    # Relación con Product
    product = db.relationship('Product', backref='order_details')

class InventoryMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    movement_type = db.Column(db.String(20), nullable=False)  # 'entrada' o 'salida'
    quantity = db.Column(db.Integer, nullable=False)
    movement_date = db.Column(db.DateTime, default=datetime.now(pytz.timezone('America/Caracas')))
    notes = db.Column(db.String(200))
    
    # Campos para entradas
    boxes = db.Column(db.Float)  # Cantidad de cajas (para entradas)
    units_per_box = db.Column(db.Integer)  # Unidades por caja
    purchase_price = db.Column(db.Float)  # Precio total de compra
    currency = db.Column(db.String(3))  # 'USD' o 'BS'
    distributor = db.Column(db.String(50))
    
    # Campos para salidas
    exit_type = db.Column(db.String(20))  # 'individual', 'caja', etc.
    
    # Relaciones
    product = db.relationship('Product', backref='movements')
    user = db.relationship('User', backref='inventory_actions')

    is_locked = db.Column(db.Boolean, default=False)
    locked_by_admin = db.Column(db.Boolean, default=False)

def create_initial_products():

    from py_exchange import get_current_rate  # Importamos aquí para evitar circularidad
    current_rate = get_current_rate()
    
    products = [
        {
            'name': 'Solera Azul',
            'brand': 'Polar',
            'category': 'Cerveza',
            'presentation': 'Botella 222ml',
            'price_unit_usd': 1.0,
            'price_half_tobo_usd': 5.0,
            'price_tobo_usd': 10.0,
            'price_half_box_usd': 12.5,
            'price_box_usd': 25.0,
            # Precios en bolívares
            'price_unit_bs': 1.0 * current_rate * 1.2,  # +20%
            'price_half_tobo_bs': 5.0 * current_rate * 1.2,
            'price_tobo_bs': 10.0 * current_rate * 1.2,
            'price_half_box_bs': 15.0,  # Fijo en $15 equivalente
            'price_box_bs': 30.0,      # Fijo en $30 equivalente
            'cost_per_unit_usd': 17.0/36
        },
        # ... otros productos con estructura similar
    ]
    
    for prod_data in products:
        if not Product.query.filter_by(name=prod_data['name'], brand=prod_data['brand']).first():
            product = Product(
                name=prod_data['name'],
                brand=prod_data['brand'],
                category=prod_data['category'],
                presentation=prod_data['presentation'],
                quantity=0,
                box_quantity=0,
                price_usd=prod_data['price_unit_usd'],  # Precio unitario por defecto
                price_bs=prod_data['price_unit_bs'],
                # Precios especiales
                price_unit_usd=prod_data['price_unit_usd'],
                price_half_tobo_usd=prod_data['price_half_tobo_usd'],
                price_tobo_usd=prod_data['price_tobo_usd'],
                price_half_box_usd=prod_data['price_half_box_usd'],
                price_box_usd=prod_data['price_box_usd'],
                price_unit_bs=prod_data['price_unit_bs'],
                price_half_tobo_bs=prod_data['price_half_tobo_bs'],
                price_tobo_bs=prod_data['price_tobo_bs'],
                price_half_box_bs=prod_data['price_half_box_bs'],
                price_box_bs=prod_data['price_box_bs'],
                is_alcoholic=True,
                cost_per_unit_usd=prod_data.get('cost_per_unit_usd', prod_data['price_unit_usd']*0.7)
            )
            db.session.add(product)
    
    db.session.commit()