from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Instancia de SQLAlchemy
db = SQLAlchemy()

# Modelo de Producto
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    price_usd = db.Column(db.Float, nullable=False)
    price_bs = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Modelo de Mesa
class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, unique=True, nullable=False)  # Número de mesa
    status = db.Column(db.String(20), nullable=False, default="disponible")  # disponible, ocupada, esperando pago
    orders = db.relationship('Order', backref='table', lazy=True)  # Relación con pedidos

# Modelo de Pedido
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey('table.id'), nullable=False)  # Relación con la mesa
    total_price = db.Column(db.Float, nullable=False, default=0.0)
    status = db.Column(db.String(20), nullable=False, default="pendiente")  # pendiente, pagado
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relación muchos a muchos con productos
    products = db.relationship('OrderDetail', backref='order', lazy=True)

# Modelo intermedio para pedidos-productos
class OrderDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    subtotal = db.Column(db.Float, nullable=False)