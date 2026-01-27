from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from py_bcv import get_bcv_rate

# Creamos la instancia de db aquí
db = SQLAlchemy()

def init_exchange_rate(app):
    with app.app_context():
        # Verificar si ya existe una tasa activa
        try:
            rate = ExchangeRate.query.filter_by(is_active=True).first()
            if not rate:
                # Si no hay tasa, intentamos BCV
                bcv_rate = get_bcv_rate()
                # Si BCV falla, empezamos en 0.0
                rate = ExchangeRate(rate=bcv_rate, is_active=True)
                db.session.add(rate)
                db.session.commit()
        except Exception:
            # Si la tabla no existe o algo falla, no bloqueamos
            pass

class ExchangeRate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rate = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

def get_current_rate():
    try:
        rate = ExchangeRate.query.filter_by(is_active=True).order_by(ExchangeRate.created_at.desc()).first()
        if rate:
            return rate.rate
        
        # Si no hay nada en DB, intentamos BCV una vez
        return get_bcv_rate()
    except Exception:
        return 0.0

def update_rate(new_rate):
    try:
        ExchangeRate.query.update({'is_active': False})
        rate = ExchangeRate(rate=new_rate, is_active=True)
        db.session.add(rate)
        db.session.commit()
        return rate
    except Exception:
        return None