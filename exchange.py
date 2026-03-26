from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from bcv_provider import get_bcv_rate

# Centralized database instance
db = SQLAlchemy()

def init_exchange_rate(app):
    """
    Initialize the exchange rate in the database if no active rate exists.
    Tries to fetch from BCV API, otherwise defaults to 0.0.
    """
    with app.app_context():
        try:
            rate = ExchangeRate.query.filter_by(is_active=True).first()
            if not rate:
                bcv_rate = get_bcv_rate()
                rate = ExchangeRate(rate=bcv_rate, is_active=True)
                db.session.add(rate)
                db.session.commit()
        except Exception:
            pass

class ExchangeRate(db.Model):
    """Model to store historical and current exchange rates (USD/BS)."""
    id = db.Column(db.Integer, primary_key=True)
    rate = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

def get_current_rate():
    """
    Fetch the currently active exchange rate from the database.
    Fallback to BCV API if nothing is found in the database.
    """
    try:
        rate = ExchangeRate.query.filter_by(is_active=True).order_by(ExchangeRate.created_at.desc()).first()
        if rate:
            return rate.rate
        return get_bcv_rate()
    except Exception:
        return 0.0

def update_rate(new_rate):
    """
    Deactivate the current rate and set a new manual exchange rate.
    """
    try:
        ExchangeRate.query.update({'is_active': False})
        rate = ExchangeRate(rate=new_rate, is_active=True)
        db.session.add(rate)
        db.session.commit()
        return rate
    except Exception:
        return None