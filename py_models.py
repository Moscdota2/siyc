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
    payment_currency = db.Column(db.String(3))  # 'USD' o 'BS'
    exchange_rate = db.Column(db.Float)  # Tasa usada en el pago
    payment_amount_bs = db.Column(db.Float)  # Monto pagado en BS
    payment_amount_usd = db.Column(db.Float)  # Monto pagado en USD
    payment_method_id = db.Column(db.Integer, db.ForeignKey('payment_method.id'))
    payment_method = db.relationship('PaymentMethod')

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
    total_usd_investment = db.Column(db.Float)  # Inversión total en USD


class PaymentMethod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    currency = db.Column(db.String(3), nullable=False)  # 'USD' o 'BS'
    is_active = db.Column(db.Boolean, default=True)

def create_initial_products():

    from py_exchange import get_current_rate  # Importamos aquí para evitar circularidad
    current_rate = get_current_rate()
    
    products = [
        # Cervezas (existente)
        {
            'name': 'Solera Azul',
            'brand': 'Polar',
            'category': 'Cerveza',
            'presentation': 'Botella 222ml',
            'price_usd': 1.0,  # Asegúrate de incluir price_usd en todos los productos
            'price_unit_usd': 1.0,
            'price_half_tobo_usd': 5.0,
            'price_tobo_usd': 10.0,
            'price_half_box_usd': 12.5,
            'price_box_usd': 25.0,
            'price_unit_bs': 1.0 * current_rate * 1.2,
            'price_half_tobo_bs': 5.0 * current_rate * 1.2,
            'price_tobo_bs': 10.0 * current_rate * 1.2,
            'price_half_box_bs': 15.0,
            'price_box_bs': 30.0,
            'cost_per_unit_usd': 17.0/36
        },
        # Rones
        {
            'name': 'Cacique 500',
            'brand': 'Cacique',
            'category': 'Ron',
            'presentation': 'Botella 500ml',
            'price_usd': 3.0,  # Añadido price_usd
            'price_unit_usd': 3.0,
            'price_half_tobo_usd': 15.0,  # 6 unidades
            'price_tobo_usd': 30.0,        # 12 unidades (2 cajas)
            'price_unit_bs': 3.0 * current_rate,
            'price_half_tobo_bs': 15.0 * current_rate,
            'price_tobo_bs': 30.0 * current_rate,
            'cost_per_unit_usd': 15.0/6    # $15 por caja de 6
        },
        # Anís
        {
            'name': 'Anís Cartujo',
            'brand': 'Cartujo',
            'category': 'Anís',
            'presentation': 'Botella 750ml',
            'price_usd': 4.0,  # Añadido price_usd
            'price_unit_usd': 4.0,
            'price_unit_bs': 4.0 * current_rate,
            'cost_per_unit_usd': 2.5
        },
        # Whisky
        {
            'name': 'Black Label',
            'brand': 'Johnnie Walker',
            'category': 'Whisky',
            'presentation': 'Botella 750ml',
            'price_usd': 8.0,  # Añadido price_usd
            'price_unit_usd': 8.0,
            'price_unit_bs': 8.0 * current_rate,
            'cost_per_unit_usd': 5.0
        }
    ]
    
    for prod_data in products:
        if not Product.query.filter_by(name=prod_data['name'], brand=prod_data['brand']).first():
            # Asegurémonos de que price_usd esté definido
            if 'price_usd' not in prod_data:
                prod_data['price_usd'] = prod_data.get('price_unit_usd', 0)
                
            product = Product(
                name=prod_data['name'],
                brand=prod_data['brand'],
                category=prod_data['category'],
                presentation=prod_data['presentation'],
                quantity=0,
                box_quantity=0,
                price_usd=prod_data['price_usd'],
                price_bs=prod_data.get('price_unit_bs', prod_data['price_usd'] * current_rate),
                # Precios especiales
                price_unit_usd=prod_data.get('price_unit_usd', prod_data['price_usd']),
                price_half_tobo_usd=prod_data.get('price_half_tobo_usd', 0),
                price_tobo_usd=prod_data.get('price_tobo_usd', 0),
                price_half_box_usd=prod_data.get('price_half_box_usd', 0),
                price_box_usd=prod_data.get('price_box_usd', 0),
                price_unit_bs=prod_data.get('price_unit_bs', prod_data['price_usd'] * current_rate),
                price_half_tobo_bs=prod_data.get('price_half_tobo_bs', 0),
                price_tobo_bs=prod_data.get('price_tobo_bs', 0),
                price_half_box_bs=prod_data.get('price_half_box_bs', 0),
                price_box_bs=prod_data.get('price_box_bs', 0),
                is_alcoholic=True,
                cost_per_unit_usd=prod_data.get('cost_per_unit_usd', prod_data['price_usd']*0.7)
            )
            db.session.add(product)
    
    db.session.commit()
