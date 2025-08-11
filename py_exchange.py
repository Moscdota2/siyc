from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Creamos la instancia de db aquí
db = SQLAlchemy()

def init_exchange_rate(app):
    with app.app_context():
        # Verificar si ya existe una tasa activa
        rate = ExchangeRate.query.filter_by(is_active=True).first()
        if not rate:
            # Crear tasa por defecto si no existe
            default_rate = 38.0
            rate = ExchangeRate(rate=default_rate, is_active=True)
            db.session.add(rate)
            db.session.commit()

class ExchangeRate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rate = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

def get_current_rate():
    rate = ExchangeRate.query.filter_by(is_active=True).order_by(ExchangeRate.created_at.desc()).first()
    return rate.rate if rate else 38.0  # Valor por defecto

def update_rate(new_rate):
    ExchangeRate.query.update({'is_active': False})
    rate = ExchangeRate(rate=new_rate, is_active=True)
    db.session.add(rate)
    db.session.commit()
    return rate