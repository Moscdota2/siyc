from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor

monitor = Monitor(AlCambio, 'USD')
precio_bcv_actual = monitor.get_value_monitors("bcv").price


