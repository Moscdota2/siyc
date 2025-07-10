from pyDolarVenezuela.pages import AlCambio
from pyDolarVenezuela import Monitor


monitor = Monitor(AlCambio, 'USD')

# Obtener los valores de todos los monitores
all_monitors = monitor.get_all_monitors()

# Obtener el valor del dólar en EnParaleloVzla
get_precio_bcv_actual = monitor.get_value_monitors("bcv")
precio_bcv_actual = get_precio_bcv_actual.price


print(precio_bcv_actual)



