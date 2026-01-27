from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor

def get_bcv_rate():
    """Fetches the BCV exchange rate safely."""
    try:
        monitor = Monitor(AlCambio, 'USD')
        return float(monitor.get_value_monitors("bcv").price)
    except Exception as e:
        print(f"Error fetching BCV rate: {e}")
        return 0.0


