from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from py_bcv import precio_bcv_actual

db = SQLAlchemy()

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
    brand = db.Column(db.String(50), nullable=False)  # Polar, Zulia, etc.
    presentation = db.Column(db.String(50), nullable=False)  # Botella 222ml, Lata 350ml
    category = db.Column(db.String(50), nullable=False)  # Cerveza, Ron, Whisky
    quantity = db.Column(db.Integer, nullable=False, default=0)
    box_quantity = db.Column(db.Float, nullable=False, default=0.0)  # Cajas completas
    price_usd = db.Column(db.Float, nullable=False)
    price_bs = db.Column(db.Float, nullable=False)
    is_alcoholic = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_modified_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    modifier = db.relationship('User', backref='modified_products')
    cost_per_unit_usd = db.Column(db.Float)  # Nuevo: Costo por unidad en USD
    last_purchase_price = db.Column(db.Float)  # Nuevo: Último precio de compra por caja en USD

class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="disponible")
    orders = db.relationship('Order', backref='table', lazy=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey('table.id'), nullable=False)
    total_price = db.Column(db.Float, nullable=False, default=0.0)
    status = db.Column(db.String(20), nullable=False, default="pendiente")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    products = db.relationship('OrderDetail', backref='order', lazy=True)

class OrderDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    subtotal = db.Column(db.Float, nullable=False)
    exit_type = db.Column(db.String(20))

class InventoryMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    movement_type = db.Column(db.String(20), nullable=False)  # entrada/salida
    quantity = db.Column(db.Integer, nullable=False)
    exit_type = db.Column(db.String(20))  # individual/tobo/media_caja/caja
    movement_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.String(200))
    is_locked = db.Column(db.Boolean, default=False)
    
    # Nuevos campos para gestión financiera del inventario
    currency = db.Column(db.String(3))  # USD o BS
    purchase_price = db.Column(db.Float)  # Precio pagado en la moneda original
    usd_price_per_box = db.Column(db.Float)  # Precio por caja en USD
    total_usd_investment = db.Column(db.Float)  # Inversión total en USD
    distributor = db.Column(db.String(20))  # Polar, Regional, etc.
    exchange_rate = db.Column(db.Float)  # Tasa de cambio al momento de la compra
    locked_by_admin = db.Column(db.Boolean, default=False)
    
    product = db.relationship('Product', backref='movements')
    user = db.relationship('User', backref='inventory_actions')

def create_initial_products():
    products = [
        # Cervezas Polar
        {
            'name': 'Solera Azul',
            'brand': 'Polar',
            'category': 'Cerveza',
            'presentation': 'Botella 222ml',
            'price_usd': 1.5,
            'cost_per_unit_usd': 17.0/36  # Precio por unidad en USD (caja de 36)
        },
        {
            'name': 'Polarcita Negra',
            'brand': 'Polar',
            'category': 'Cerveza',
            'presentation': 'Botella 222ml',
            'price_usd': 1.3,
            'cost_per_unit_usd': 17.0/36
        },
        {
            'name': 'Polar Light',
            'brand': 'Polar',
            'category': 'Cerveza',
            'presentation': 'Lata 350ml',
            'price_usd': 1.8,
            'cost_per_unit_usd': 17.0/36
        },
        
        # Cervezas Zulia
        {
            'name': 'Zulia Lager',
            'brand': 'Zulia',
            'category': 'Cerveza',
            'presentation': 'Botella 330ml',
            'price_usd': 1.2,
            'cost_per_unit_usd': 19.0/36
        },
        
        # Rones
        {
            'name': 'Pampero Aniversario',
            'brand': 'Pampero',
            'category': 'Ron',
            'presentation': 'Botella 750ml',
            'price_usd': 12.0,
            'cost_per_unit_usd': 12.0  # Asumiendo que se compra individual
        }
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
                price_usd=prod_data['price_usd'],
                price_bs=prod_data['price_usd'] * precio_bcv_actual,
                is_alcoholic=True,
                cost_per_unit_usd=prod_data.get('cost_per_unit_usd', prod_data['price_usd']*0.7)  # Default 70% del precio venta
            )
            db.session.add(product)
    
    db.session.commit()