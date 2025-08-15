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
    price_unit_usd = db.Column(db.Float)
    price_half_tobo_usd = db.Column(db.Float)
    price_tobo_usd = db.Column(db.Float)
    price_half_box_usd = db.Column(db.Float)
    price_box_usd = db.Column(db.Float)
    price_unit_bs = db.Column(db.Float)
    price_half_tobo_bs = db.Column(db.Float)
    price_tobo_bs = db.Column(db.Float)
    price_half_box_bs = db.Column(db.Float)
    price_box_bs = db.Column(db.Float)
    is_combo = db.Column(db.Boolean, default=False)
    combo_items = db.Column(db.JSON)

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
    payment_currency = db.Column(db.String(3))
    exchange_rate = db.Column(db.Float)
    payment_amount_bs = db.Column(db.Float)
    payment_amount_usd = db.Column(db.Float)
    payment_method_id = db.Column(db.Integer, db.ForeignKey('payment_method.id'))
    payment_method = db.relationship('PaymentMethod')

class OrderDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    subtotal = db.Column(db.Float, nullable=False)
    exit_type = db.Column(db.String(20))
    product = db.relationship('Product', backref='order_details')

class InventoryMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    movement_type = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    movement_date = db.Column(db.DateTime, default=datetime.now(pytz.timezone('America/Caracas')))
    notes = db.Column(db.String(200))
    boxes = db.Column(db.Float)
    units_per_box = db.Column(db.Integer)
    purchase_price = db.Column(db.Float)
    currency = db.Column(db.String(3))
    distributor = db.Column(db.String(50))
    exit_type = db.Column(db.String(20))
    product = db.relationship('Product', backref='movements')
    user = db.relationship('User', backref='inventory_actions')
    is_locked = db.Column(db.Boolean, default=False)
    locked_by_admin = db.Column(db.Boolean, default=False)
    total_usd_investment = db.Column(db.Float)

class PaymentMethod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

def create_initial_products():
    from py_exchange import get_current_rate
    current_rate = get_current_rate()
    
    # Definimos la estructura de precios estándar para cervezas
    beer_pricing = {
        'price_unit_usd': 1.0,
        'price_half_tobo_usd': 5.0,    # 6 unidades
        'price_tobo_usd': 10.0,        # 12 unidades
        'price_half_box_usd': 15.0,    # 18 unidades
        'price_box_usd': 30.0,         # 36 unidades
        'price_unit_bs': 1.0 * current_rate * 1.2,
        'price_half_tobo_bs': 5.0 * current_rate * 1.2,
        'price_tobo_bs': 10.0 * current_rate * 1.2,
        'price_half_box_bs': 15.0 * current_rate * 1.2,
        'price_box_bs': 30.0 * current_rate * 1.2,
    }

    # Primero creamos todos los productos individuales
    individual_products = [
        # Cervezas (todas con la misma estructura de precios)
        {
            'name': 'Solera Azul',
            'brand': 'Polar',
            'category': 'Cerveza',
            'presentation': 'Botella 222ml',
            'price_usd': 1.0,
            'cost_per_unit_usd': 17.0/36,
            **beer_pricing
        },
        {
            'name': 'Polarcita Negra',
            'brand': 'Polar',
            'category': 'Cerveza',
            'presentation': 'Botella 222ml',
            'price_usd': 1.0,
            'cost_per_unit_usd': 17.0/36,
            **beer_pricing
        },
        {
            'name': 'Polar Light',
            'brand': 'Polar',
            'category': 'Cerveza',
            'presentation': 'Lata 350ml',
            'price_usd': 1.0,
            'cost_per_unit_usd': 17.0/36,
            **beer_pricing
        },
        {
            'name': 'Zulia Lager',
            'brand': 'Zulia',
            'category': 'Cerveza',
            'presentation': 'Botella 330ml',
            'price_usd': 1.0,
            'cost_per_unit_usd': 19.0/36,
            **beer_pricing
        },
        # Resto de tus productos individuales (rones, anís, etc.)
        {
            'name': 'Superior',
            'brand': 'Polar',
            'category': 'Ron',
            'presentation': 'Botella 1L',
            'price_usd': 3.58,
            'price_unit_usd': 3.58,
            'price_unit_bs': 3.58 * current_rate,
            'cost_per_unit_usd': 2.5
        },
        # Rones
        {
            'name': 'Superior',
            'brand': 'Polar',
            'category': 'Ron',
            'presentation': 'Botella 1L',
            'price_usd': 3.58,
            'price_unit_usd': 3.58,
            'price_unit_bs': 3.58 * current_rate,
            'cost_per_unit_usd': 2.5
        },
        {
            'name': 'Carta Roja',
            'brand': 'Polar',
            'category': 'Ron',
            'presentation': 'Botella 1L',
            'price_usd': 4.33,
            'price_unit_usd': 4.33,
            'price_unit_bs': 4.33 * current_rate,
            'cost_per_unit_usd': 3.0
        },
        {
            'name': 'Santa Teresa',
            'brand': 'Santa Teresa',
            'category': 'Ron',
            'presentation': 'Botella 750ml',
            'price_usd': 8.0,
            'price_unit_usd': 8.0,
            'price_unit_bs': 8.0 * current_rate,
            'cost_per_unit_usd': 5.0
        },
        # Anís
        {
            'name': 'Cartujo',
            'brand': 'Cartujo',
            'category': 'Anís',
            'presentation': 'Botella 1L',
            'price_usd': 5.41,
            'price_unit_usd': 5.41,
            'price_unit_bs': 5.41 * current_rate,
            'cost_per_unit_usd': 3.5
        },
        # Misceláneos
        {
            'name': 'Soda',
            'brand': 'Polar',
            'category': 'Misceláneo',
            'presentation': 'Botella 355ml',
            'price_usd': 0.53,
            'price_unit_usd': 0.53,
            'price_unit_bs': 0.53 * current_rate,
            'cost_per_unit_usd': 0.3,
            'is_alcoholic': False
        },
        {
            'name': 'Coca Cola',
            'brand': 'Coca Cola',
            'category': 'Misceláneo',
            'presentation': 'Botella 1L',
            'price_usd': 1.1,
            'price_unit_usd': 1.1,
            'price_unit_bs': 1.1 * current_rate,
            'cost_per_unit_usd': 0.7,
            'is_alcoholic': False
        },
        {
            'name': 'Agua 1.5L',
            'brand': 'Minalba',
            'category': 'Misceláneo',
            'presentation': 'Botella 1.5L',
            'price_usd': 0.38,
            'price_unit_usd': 0.38,
            'price_unit_bs': 0.38 * current_rate,
            'cost_per_unit_usd': 0.2,
            'is_alcoholic': False
        },
        {
            'name': 'Agua 400ml',
            'brand': 'Minalba',
            'category': 'Misceláneo',
            'presentation': 'Botella 400ml',
            'price_usd': 0.15,
            'price_unit_usd': 0.15,
            'price_unit_bs': 0.15 * current_rate,
            'cost_per_unit_usd': 0.08,
            'is_alcoholic': False
        },
        {
            'name': 'Gatorade',
            'brand': 'Gatorade',
            'category': 'Misceláneo',
            'presentation': 'Botella 500ml',
            'price_usd': 0.75,
            'price_unit_usd': 0.75,
            'price_unit_bs': 0.75 * current_rate,
            'cost_per_unit_usd': 0.45,
            'is_alcoholic': False
        },
        # Whisky
        {
            'name': 'Black Label',
            'brand': 'Johnnie Walker',
            'category': 'Whisky',
            'presentation': 'Botella 750ml',
            'price_usd': 8.0,
            'price_unit_usd': 8.0,
            'price_unit_bs': 8.0 * current_rate,
            'cost_per_unit_usd': 5.0
        }
    ]

    # Crear productos individuales primero
    for prod_data in individual_products:
        if not Product.query.filter_by(name=prod_data['name'], brand=prod_data['brand']).first():
            product = Product(
                name=prod_data['name'],
                brand=prod_data['brand'],
                category=prod_data['category'],
                presentation=prod_data['presentation'],
                quantity=0,
                box_quantity=0,
                price_usd=prod_data['price_usd'],
                price_bs=prod_data.get('price_unit_bs', prod_data['price_usd'] * current_rate),
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
                is_alcoholic=prod_data.get('is_alcoholic', True),
                cost_per_unit_usd=prod_data.get('cost_per_unit_usd', prod_data['price_usd']*0.7)
            )
            db.session.add(product)
    
    db.session.commit()

    # Ahora creamos los combos, buscando los productos por nombre exacto
    combos = [
        {
            'name': 'Superior + Coca Cola',
            'brand': 'Combo',
            'category': 'Combo',
            'presentation': '1L Ron + 1L Refresco',
            'price_usd': 20.0,
            'is_combo': True,
            'combo_items': [
                {'product_id': Product.query.filter_by(name='Superior').first().id, 'quantity': 1},
                {'product_id': Product.query.filter_by(name='Coca Cola').first().id, 'quantity': 1}
            ],
            'is_alcoholic': True
        },
        {
            'name': 'Carta Roja + Coca Cola',
            'brand': 'Combo',
            'category': 'Combo',
            'presentation': '1L Ron + 1L Refresco',
            'price_usd': 20.0,
            'is_combo': True,
            'combo_items': [
                {'product_id': Product.query.filter_by(name='Carta Roja').first().id, 'quantity': 1},
                {'product_id': Product.query.filter_by(name='Coca Cola').first().id, 'quantity': 1}
            ],
            'is_alcoholic': True
        },
        {
            'name': 'Santa Teresa + Coca Cola',
            'brand': 'Combo',
            'category': 'Combo',
            'presentation': '750ml Ron + 1L Refresco',
            'price_usd': 25.0,
            'is_combo': True,
            'combo_items': [
                {'product_id': Product.query.filter_by(name='Santa Teresa').first().id, 'quantity': 1},
                {'product_id': Product.query.filter_by(name='Coca Cola').first().id, 'quantity': 1}
            ],
            'is_alcoholic': True
        },
        {
            'name': 'Cartujo + Gatorade',
            'brand': 'Combo',
            'category': 'Combo',
            'presentation': '1L Anís + 500ml Gatorade',
            'price_usd': 20.0,
            'is_combo': True,
            'combo_items': [
                {'product_id': Product.query.filter_by(name='Cartujo').first().id, 'quantity': 1},
                {'product_id': Product.query.filter_by(name='Gatorade').first().id, 'quantity': 1}
            ],
            'is_alcoholic': True
        }
    ]

    for combo_data in combos:
        if not Product.query.filter_by(name=combo_data['name']).first():
            # Verificar que todos los productos del combo existan
            valid_combo = True
            for item in combo_data['combo_items']:
                if not Product.query.get(item['product_id']):
                    valid_combo = False
                    break
            
            if valid_combo:
                combo = Product(
                    name=combo_data['name'],
                    brand=combo_data['brand'],
                    category=combo_data['category'],
                    presentation=combo_data['presentation'],
                    price_usd=combo_data['price_usd'],
                    price_bs=combo_data['price_usd'] * current_rate,
                    is_combo=True,
                    combo_items=combo_data['combo_items'],
                    is_alcoholic=combo_data.get('is_alcoholic', True),
                    quantity=0
                )
                db.session.add(combo)
    
    db.session.commit()


def calcular_precio_cervezas(total_cervezas, referencia_producto):
    """ Calcula el precio óptimo de cervezas mezclando marcas """
    tobos = total_cervezas // 12
    remaining = total_cervezas % 12
    half_tobos = remaining // 6
    units = remaining % 6

    subtotal = (tobos * referencia_producto.price_tobo_usd) + \
               (half_tobos * referencia_producto.price_half_tobo_usd) + \
               (units * referencia_producto.price_unit_usd)

    return subtotal