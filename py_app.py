from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, login_user, login_required, current_user, logout_user
from functools import wraps
from py_exchange import db  # Importamos db desde py_exchange
from py_models import User, Product, Table, Order, OrderDetail, InventoryMovement, create_initial_products, PaymentMethod, calcular_precio_cervezas
from py_bcv import precio_bcv_actual
from py_exchange import get_current_rate, update_rate
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bar.db'
app.config['SECRET_KEY'] = 'mysecretkey'
db.init_app(app)

# Configuración de Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Decoradores de roles
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def manager_or_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['admin', 'manager']:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


# Sistema de autenticación
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        flash('Usuario o contraseña incorrectos', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# Rutas principales
@app.route('/')
@login_required
def index():
    products = Product.query.all()
    low_stock_count = Product.query.filter(Product.quantity < 10).count()
    
    # Obtener mesas
    total_tables = Table.query.count()
    occupied_tables = Table.query.filter_by(status="ocupada").count()
    
    # Calcular ventas del día (ejemplo)
    today = datetime.today().date()
    daily_sales = 0  # Puedes implementar la lógica real aquí
    
    return render_template('index.html',
                         products=products,
                         low_stock_count=low_stock_count,
                         total_tables=total_tables,
                         occupied_tables=occupied_tables,
                         daily_sales=daily_sales)


@app.route('/inventory')
@login_required
def inventory():
    products = Product.query.all()
    low_stock = Product.query.filter(Product.quantity < 10).count()
    return render_template('inventory/inventory.html', products=products, low_stock=low_stock)


# Rutas para manejar la tasa de cambio
@app.route('/exchange_rate', methods=['GET', 'POST'])
@admin_required
def manage_exchange_rate():
    if request.method == 'POST':
        new_rate = float(request.form['rate'])
        update_rate(new_rate)
        flash(f'Tasa de cambio actualizada a {new_rate} Bs/USD', 'success')
        return redirect(url_for('manage_exchange_rate'))
    
    current_rate = get_current_rate()
    return render_template('sales/exchange_rate.html', current_rate=current_rate)


# Gestión de productos
@app.route('/create_product', methods=['GET', 'POST'])
@admin_required
def create_product():
    if request.method == 'POST':
        try:
            new_product = Product(
                name=request.form['name'],
                brand=request.form['brand'],
                category=request.form['category'],
                presentation=request.form['presentation'],
                quantity=int(request.form['quantity']),
                price_usd=float(request.form['price_usd']),
                price_bs=float(request.form['price_usd']) * precio_bcv_actual,
                last_modified_by=current_user.id
            )
            db.session.add(new_product)
            db.session.flush()

            # Registrar movimiento de creación (NUEVO)
            initial_quantity = int(request.form['quantity'])
            creation_movement = InventoryMovement(
                product_id=new_product.id,
                user_id=current_user.id,
                movement_type='entrada',
                quantity=initial_quantity,
                # is_initial_stock=True,  # Marcamos como stock inicial
                notes=f"Creación de producto: {new_product.name}",
                currency='usd',  # Valor por defecto
                distributor='sistema'  # Valor especial
            )
            db.session.add(creation_movement)
            
            db.session.commit()
            flash('Producto creado con registro histórico', 'success')
            return redirect(url_for('inventory'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
    return render_template('inventory/create_product.html')


@app.route('/update_product/<int:id>', methods=['GET', 'POST'])
@admin_required
def update_product(id):
    product = Product.query.get_or_404(id)
    if request.method == 'POST':
        try:
            product.name = request.form['name']
            product.brand = request.form['brand']
            product.category = request.form['category']
            product.presentation = request.form['presentation']
            product.quantity = int(request.form['quantity'])
            product.price_usd = float(request.form['price_usd'])
            product.price_bs = float(request.form['price_usd']) * precio_bcv_actual
            product.last_modified_by = current_user.id
            db.session.commit()
            flash('Producto actualizado exitosamente', 'success')
            return redirect(url_for('inventory'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar producto: {str(e)}', 'danger')
    return render_template('inventory/update_product.html', product=product)

@app.route('/delete_product/<int:id>')
@admin_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    
    try:
        # Primero eliminar todos los movimientos relacionados
        InventoryMovement.query.filter_by(product_id=id).delete()
        
        # Luego eliminar el producto
        db.session.delete(product)
        db.session.commit()
        flash('Producto eliminado exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar producto: {str(e)}', 'danger')
    
    return redirect(url_for('inventory'))


@app.route('/inventory_entry', methods=['GET', 'POST'])
@manager_or_admin_required
def inventory_entry():
    if request.method == 'POST':
        product_id = request.form['product_id']
        boxes = float(request.form['boxes'])
        product_type = request.form.get('product_type', '')
        currency = request.form['currency']  # 'usd' o 'bs'
        purchase_price = float(request.form['purchase_price'])
        distributor = request.form.get('distributor', '')  # Solo para cerveza
        
        product = Product.query.get_or_404(product_id)
        
        # Calcular unidades por caja según tipo de producto
        if product_type == 'cerveza':
            units_per_box = 36
        elif product_type == 'ron':
            units_per_box = 1  # Ahora se registra por botella individual
        elif product_type == 'misc':
            units_per_box = 1
        else:  # Anís, whisky y otros
            units_per_box = 1
        
        units = int(boxes * units_per_box)
        
        # Calcular precio en dólares según moneda de pago y distribuidor
        if currency == 'bs':
            if product_type == 'cerveza':
                if distributor == 'polar':
                    usd_price_per_box = 20.80
                else:  # regional
                    usd_price_per_box = 19.50
                total_usd_investment = boxes * usd_price_per_box
            elif product_type == 'ron':
                # Para ron en BS, calculamos precio unitario
                usd_price_per_unit = purchase_price / (units * precio_bcv_actual)
                total_usd_investment = usd_price_per_unit * units
            elif product_type == 'misc':
                usd_price_per_unit = purchase_price / (units * precio_bcv_actual)
                total_usd_investment = usd_price_per_unit * units
            else:  # Anís, whisky
                usd_price_per_unit = purchase_price / (units * precio_bcv_actual)
                total_usd_investment = usd_price_per_unit * units
        else:  # USD
            if product_type == 'cerveza':
                if distributor == 'polar':
                    usd_price_per_box = 17.00
                else:  # regional
                    usd_price_per_box = 19.00
                total_usd_investment = boxes * usd_price_per_box
            elif product_type == 'ron':
                # Para ron en USD, calculamos precio unitario
                usd_price_per_unit = purchase_price / units
                total_usd_investment = usd_price_per_unit * units
            elif product_type == 'misc':
                usd_price_per_unit = purchase_price / units
                total_usd_investment = usd_price_per_unit * units
            else:  # Anís, whisky
                usd_price_per_unit = purchase_price / units
                total_usd_investment = usd_price_per_unit * units
        
        # Actualizar inventario
        product.quantity += units
        if product_type == 'cerveza':  # Solo cerveza actualiza box_quantity ahora
            product.box_quantity += boxes
        
        # Registrar movimiento con detalles financieros
        movement = InventoryMovement(
            product_id=product.id,
            user_id=current_user.id,
            movement_type='entrada',
            quantity=units,
            boxes=boxes if product_type == 'cerveza' else None,  # Solo cerveza registra cajas
            units_per_box=units_per_box,
            currency=currency,
            purchase_price=purchase_price,
            distributor=distributor if product_type == 'cerveza' else 'sistema',  # Solo cerveza usa distribuidor
            notes=f"Entrada de {boxes} {'cajas' if product_type == 'cerveza' else 'botellas'} de {product.name} ({units} unidades)",
            total_usd_investment=total_usd_investment
        )
        
        try:
            db.session.add(movement)
            db.session.commit()
            flash(f"✅ {units} unidades de {product.name} agregadas | Inversión: ${total_usd_investment:.2f}", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Error al registrar entrada: {str(e)}", 'danger')
        
        return redirect(url_for('inventory_entry'))
    
    # Obtener productos agrupados
    beers = Product.query.filter_by(category='Cerveza').all()
    rums = Product.query.filter_by(category='Ron').all()
    anises = Product.query.filter_by(category='Anís').all()
    whiskies = Product.query.filter_by(category='Whisky').all()
    miscs = Product.query.filter_by(category='Misceláneo').all()
    
    return render_template(
        "inventory/inventory_entry.html",
        products=beers + rums + anises + whiskies + miscs,
        precio_bcv=precio_bcv_actual
    )


# Necesitaríamos también una nueva ruta para reportes de inversión
@app.route('/inventory_investment_report')
@manager_or_admin_required
def inventory_investment_report():
    movements = InventoryMovement.query.filter_by(movement_type='entrada')\
        .order_by(InventoryMovement.movement_date.desc()).all()
    
    total_investment = sum(m.total_usd_investment for m in movements if m.total_usd_investment)
    
    return render_template('inventory_investment_report.html', 
                         movements=movements,
                         total_investment=total_investment)

@app.route('/inventory_exit', methods=['GET', 'POST'])
@login_required
def inventory_exit():
    if request.method == 'POST':
        product_id = request.form['product_id']
        exit_type = request.form['exit_type']
        product = Product.query.get_or_404(product_id)
        
        # Calcular cantidad según tipo de salida y categoría
        if product.category == 'Cerveza':
            if exit_type == 'individual':
                quantity = 1
            elif exit_type == 'tobo':
                quantity = 12
            elif exit_type == 'media_caja':
                quantity = 18
            elif exit_type == 'caja':
                quantity = 36
            else:
                flash('Tipo de salida inválido', 'danger')
                return redirect(url_for('inventory_exit'))
        elif product.category == 'Ron':
            if exit_type == 'individual':
                quantity = 1
            elif exit_type == 'media_caja':
                quantity = 3  # Media caja de ron (6/2)
            elif exit_type == 'caja':
                quantity = 6  # Caja completa de ron
            else:
                flash('Tipo de salida inválido', 'danger')
                return redirect(url_for('inventory_exit'))
        else:  # Anís, Whisky y otros
            quantity = 1  # Siempre se vende por botella
        
        # Verificar stock
        if product.quantity < quantity:
            flash(f'Stock insuficiente. Disponible: {product.quantity}', 'danger')
            return redirect(url_for('inventory_exit'))
        
        # Actualizar inventario
        product.quantity -= quantity
        if exit_type in ['caja', 'media_caja']:
            boxes_to_remove = 1 if exit_type == 'caja' else 0.5
            product.box_quantity -= boxes_to_remove
        
        # Registrar movimiento
        movement = InventoryMovement(
            product_id=product_id,
            user_id=current_user.id,
            movement_type='salida',
            quantity=quantity,
            exit_type=exit_type,
            is_locked=(current_user.role != 'admin'),
            notes=f'Salida registrada por {current_user.username}'
        )
        
        try:
            db.session.add(movement)
            db.session.commit()
            flash(f'Salida registrada: {quantity} unidades', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar salida: {str(e)}', 'danger')
        
        return redirect(url_for('inventory_exit'))
    
    products = Product.query.filter(Product.quantity > 0).all()
    return render_template('inventory_exit.html', products=products)


# Gestión de mesas
@app.route('/tables')
@login_required
def view_tables():
    tables = Table.query.order_by(Table.number).all()
    return render_template('sales/tables.html', tables=tables)


@app.route('/create_table', methods=['GET', 'POST'])
@admin_required
def create_table():
    if request.method == 'POST':
        try:
            table_number = int(request.form['number'])
            new_table = Table(number=table_number)
            db.session.add(new_table)
            db.session.commit()
            flash('Mesa creada exitosamente', 'success')
            return redirect(url_for('view_tables'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear mesa: {str(e)}', 'danger')
    return render_template('create_table.html')


# Gestión de pedidos
@app.route('/create_order/<int:table_id>')
@login_required
def create_order(table_id):
    table = Table.query.get_or_404(table_id)
    if table.status != "disponible":
        active_order = Order.query.filter_by(table_id=table.id, status="pendiente").first()
        if active_order:
            return redirect(url_for('view_order', table_id=table.id))
        else:
            table.status = "disponible"
            db.session.commit()
            flash('Estado de mesa corregido', 'info')
            return redirect(url_for('view_tables'))
    
    new_order = Order(
        table_id=table_id,
        waiter_id=current_user.id,  # Asignar el usuario actual como mesero
        status="pendiente"
    )
    table.status = "ocupada"
    
    try:
        db.session.add(new_order)
        db.session.commit()
        flash(f'Pedido creado para Mesa {table.number}', 'success')
        return redirect(url_for('view_order', table_id=table.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear pedido: {str(e)}', 'danger')
        return redirect(url_for('view_tables'))


@app.route('/order/<int:table_id>')
@login_required
def view_order(table_id):
    table = Table.query.get_or_404(table_id)
    active_order = Order.query.filter_by(table_id=table.id, status="pendiente").first()
    
    if not active_order:
        flash('No hay pedido activo para esta mesa', 'warning')
        return redirect(url_for('view_tables'))
    
    order_details = OrderDetail.query.filter_by(order_id=active_order.id).all()
    
    ## Preparar combos con nombres de productos
    for detail in order_details:
        if detail.product.is_combo and detail.product.combo_items:
            enriched_items = []
            for combo_item in detail.product.combo_items:
                product = Product.query.get(combo_item.get('product_id'))
                if product:
                    enriched_items.append({
                        'name': product.name,
                        'quantity': combo_item.get('quantity', 1)
                    })
            detail.combo_contents = enriched_items  # <- atributo dinámico
    
    products = Product.query.all()
    payment_methods = PaymentMethod.query.filter_by(is_active=True).order_by(PaymentMethod.currency, PaymentMethod.name).all()
    
    return render_template('sales/order.html', 
                         order=active_order, 
                         order_details=order_details, 
                         products=products,
                         table=table,
                         payment_methods=payment_methods,
                         current_rate=get_current_rate(),
                         is_bar_order=False)


@app.route('/add_product/<int:table_id>', methods=['POST'])
@login_required
def add_product(table_id):
    table = Table.query.get_or_404(table_id)
    order = Order.query.filter_by(table_id=table_id, status="pendiente").first_or_404()

    product = Product.query.get_or_404(request.form['product_id'])
    exit_type = request.form.get('exit_type', 'individual')
    quantity = int(request.form['quantity'])

    if product.is_combo:
        for item in product.combo_items:
            component = Product.query.get(item['product_id'])
            if not component or component.quantity < (item['quantity'] * quantity):
                flash(f'Stock insuficiente de {component.name if component else "componente"}', 'danger')
                return redirect(url_for('view_order', table_id=table_id))

        subtotal = product.price_usd * quantity
        order_detail = OrderDetail(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            subtotal=subtotal,
            exit_type='combo'
        )
        order.total_price += subtotal

        for item in product.combo_items:
            component = Product.query.get(item['product_id'])
            component.quantity -= (item['quantity'] * quantity)
            movement = InventoryMovement(
                product_id=component.id,
                user_id=current_user.id,
                movement_type='salida',
                quantity=item['quantity'] * quantity,
                exit_type='combo',
                notes=f'Componente de {product.name} (Orden #{order.id})',
                is_locked=True
            )
            db.session.add(movement)

        try:
            db.session.add(order_detail)
            db.session.commit()
            flash(f'{quantity}x {product.name} agregado a la orden', 'success')
            return redirect(url_for('view_order', table_id=table_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al agregar combo: {str(e)}', 'danger')
            return redirect(url_for('view_order', table_id=table_id))

    if product.category == 'Cerveza' and exit_type == 'individual':
        cervezas_actuales = sum(d.quantity for d in order.products if d.product.category == "Cerveza" and not d.product.is_combo)
        total_cervezas = cervezas_actuales + quantity
        referencia = product
        subtotal_total = calcular_precio_cervezas(total_cervezas, referencia)
        subtotal_nuevo = subtotal_total - calcular_precio_cervezas(cervezas_actuales, referencia)
    else:
        if exit_type == 'half_tobo':
            subtotal_nuevo = product.price_half_tobo_usd
            quantity = 6
        elif exit_type == 'tobo':
            subtotal_nuevo = product.price_tobo_usd
            quantity = 12
        elif exit_type == 'half_box':
            subtotal_nuevo = product.price_half_box_usd
            quantity = 18
        elif exit_type == 'box':
            subtotal_nuevo = product.price_box_usd
            quantity = 36
        else:
            subtotal_nuevo = quantity * product.price_unit_usd

    if product.quantity < quantity:
        flash(f'Stock insuficiente de {product.name}', 'danger')
        return redirect(url_for('view_order', table_id=table_id))

    order_detail = OrderDetail(
        order_id=order.id,
        product_id=product.id,
        quantity=quantity,
        subtotal=subtotal_nuevo,
        exit_type=exit_type
    )
    order.total_price += subtotal_nuevo
    product.quantity -= quantity
    movement = InventoryMovement(
        product_id=product.id,
        user_id=current_user.id,
        movement_type='salida',
        quantity=quantity,
        exit_type=exit_type if exit_type != 'individual' else 'venta',
        notes=f'Despachado en orden #{order.id} (pendiente de pago)',
        is_locked=True
    )

    try:
        db.session.add(order_detail)
        db.session.add(movement)
        db.session.commit()
        flash(f'{quantity}x {product.name} agregado a la orden', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al agregar producto: {str(e)}', 'danger')

    return redirect(url_for('view_order', table_id=table_id))


@app.route('/close_order/<int:table_id>', methods=['POST'])
@admin_required
def close_order(table_id):
    active_order = Order.query.filter_by(table_id=table_id, status="pendiente").first()
    if not active_order:
        flash('No hay pedido activo para esta mesa', 'danger')
        return redirect(url_for('view_tables'))
    
    # Obtener datos del formulario de pago
    payment_currency = request.form['payment_currency']
    payment_method_id = int(request.form['payment_method'])
    payment_amount = float(request.form['payment_amount'])
    current_rate = get_current_rate()
    
    # Calcular montos en ambas monedas
    if payment_currency == 'bs':
        payment_amount_usd = payment_amount
        payment_amount_bs = payment_amount * current_rate
    else:  # USD
        payment_amount_bs = payment_amount
        payment_amount_usd = payment_amount * current_rate
    
    # Validar que el pago cubra el total
    if payment_currency == 'bs' and payment_amount_bs < active_order.total_price * current_rate:
        flash('El monto pagado no cubre el total de la orden', 'danger')
        return redirect(url_for('view_order', table_id=table_id))
    
    # if payment_currency == 'usd' and payment_amount_usd < active_order.total_price:
    #     flash('El monto pagado no cubre el total de la orden', 'danger')
    #     return redirect(url_for('view_order', table_id=table_id))
    
    # Actualizar la orden con los datos del pago
    table = active_order.table
    active_order.status = "pagado"
    active_order.closed_at = datetime.utcnow()
    active_order.payment_currency = payment_currency
    active_order.exchange_rate = current_rate
    active_order.payment_amount_bs = payment_amount_bs
    active_order.payment_amount_usd = payment_amount_usd
    active_order.payment_method_id = payment_method_id
    table.status = "disponible"
    
    # Registrar cambio en los movimientos de inventario
    movements = InventoryMovement.query.filter(
        InventoryMovement.notes.like(f'%orden #{active_order.id}%')
    ).all()
    
    for mov in movements:
        mov.notes = mov.notes.replace('(pendiente de pago)', '(pagado)')
    
    try:
        db.session.commit()
        
        # Preparar mensaje de confirmación con detalles del pago
        payment_method = PaymentMethod.query.get(payment_method_id)
        if payment_currency == 'bs':
            payment_msg = f"Pago registrado: {payment_amount_bs:.2f} Bs (${payment_amount_usd:.2f}) - {payment_method.name}"
        else:
            payment_msg = f"Pago registrado: ${payment_amount_usd:.2f} ({payment_amount_bs:.2f} Bs) - {payment_method.name}"
        
        flash(f'Pedido #{active_order.id} marcado como PAGADO. {payment_msg}. Mesa {table.number} liberada', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cerrar pedido: {str(e)}', 'danger')
    
    return redirect(url_for('view_tables'))

@app.route('/inventory_history')
@manager_or_admin_required
def inventory_history():
    movements = db.session.query(
        InventoryMovement,
        Product
    ).join(
        Product, InventoryMovement.product_id == Product.id
    ).options(
        db.contains_eager(InventoryMovement.product)
    ).order_by(
        InventoryMovement.movement_date.desc()
    ).all()
    
    return render_template('inventory/inventory_history.html', movements=movements)


@app.route('/edit_movement/<int:movement_id>', methods=['GET', 'POST'])
@admin_required
def edit_movement(movement_id):
    movement = InventoryMovement.query.get_or_404(movement_id)
    if request.method == 'POST':
        original_qty = movement.quantity
        new_qty = int(request.form['quantity'])
        
        # Ajustar inventario
        product = movement.product
        product.quantity += (original_qty - new_qty)
        
        # Actualizar movimiento
        movement.quantity = new_qty
        movement.notes = f"Ajustado por {current_user.username}. Original: {original_qty}, Nuevo: {new_qty}"
        movement.is_locked = True
        movement.locked_by_admin = True
        
        try:
            db.session.commit()
            flash('Movimiento actualizado', 'success')
            return redirect(url_for('inventory_history'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar: {str(e)}', 'danger')
    
    return render_template('edit_movement.html', movement=movement)


# Ventas/Consumo - Versión actualizada
@app.route('/sales', methods=['GET', 'POST'])
@login_required
def sales():
    if request.method == 'POST':
        sale_type = request.form['sale_type']
        
        if sale_type == 'mesa':
            table_id = request.form['table_id']
        elif sale_type == 'barra':
            customer_name = request.form.get('customer_name', 'Consumo en barra')
        return redirect(url_for('sales'))
    
    # Obtener productos individuales con stock
    individual_products = Product.query.filter(
        Product.quantity > 0, 
        Product.is_combo == False
    ).all()

    # Procesar combos con disponibilidad real
    available_combos = []
    for combo in Product.query.filter_by(is_combo=True).all():
        combo_data = {
            'id': combo.id,
            'name': combo.name,
            'price_usd': float(combo.price_usd),
            'is_combo': True,
            'combo_items': combo.combo_items,
            'available_quantity': float('inf')  # Inicializar con valor alto
        }

        # Calcular disponibilidad basada en componentes
        for item in combo.combo_items:
            component = Product.query.get(item['product_id'])
            if not component or component.quantity < item['quantity']:
                combo_data['available_quantity'] = 0
                break
            
            # Calcular cuántos combos se pueden hacer con este componente
            possible_quantity = component.quantity // item['quantity']
            if possible_quantity < combo_data['available_quantity']:
                combo_data['available_quantity'] = possible_quantity
        
        if combo_data['available_quantity'] > 0:
            available_combos.append(combo_data)

    # Preparar datos para la plantilla
    products_data = []
    
    # Productos individuales
    for product in individual_products:
        products_data.append({
            'id': product.id,
            'name': product.name,
            'price_usd': float(product.price_usd),
            'quantity': product.quantity,
            'is_combo': False,
            'available_quantity': product.quantity,
            'category': product.category
        })
    
    # Combos disponibles
    for combo in available_combos:
        products_data.append({
            'id': combo['id'],
            'name': combo['name'],
            'price_usd': combo['price_usd'],
            'quantity': 0,  # Los combos no tienen stock físico
            'is_combo': True,
            'available_quantity': combo['available_quantity'],
            'combo_items': combo['combo_items'],
            'category': 'Combo'
        })

    tables = [{
        'id': t.id,
        'number': t.number,
        'status': t.status
    } for t in Table.query.all()]
    
    return render_template('sales/sales.html', 
                         products=products_data, 
                         tables=tables,
                         debug=True)


@app.route('/sales_reports')
@login_required
def sales_reports():
    # Obtener todas las órdenes pagadas
    completed_orders = Order.query.filter_by(status="pagado").all()
    
    # Calcular total de ventas
    total_sales = sum(order.total_price for order in completed_orders)
    
     # Calcular totales por moneda
    total_usd = sum(o.payment_amount_usd for o in completed_orders if o.payment_currency == 'usd')
    total_bs = sum(o.payment_amount_bs for o in completed_orders if o.payment_currency == 'bs')
    
    return render_template('sales/sales_reports.html', 
                         orders=completed_orders,
                         total_sales=total_sales,
                         total_usd=total_usd,
                         total_bs=total_bs,
                         current_rate=get_current_rate())


@app.route('/register_sale', methods=['POST'])
@login_required
def register_sale():
    if request.method == 'POST':
        try:
            sale_type = request.form['sale_type']
            product_ids = request.form.getlist('product_id[]')
            quantities = request.form.getlist('quantity[]')
            exit_types = request.form.getlist('exit_type[]') or ['individual'] * len(product_ids)

            if sale_type == 'mesa':
                table_id = request.form['table_id']
                table = Table.query.get_or_404(table_id)
                if table.status != "disponible":
                    flash('La mesa ya está ocupada', 'danger')
                    return redirect(url_for('sales'))

                new_order = Order(
                    table_id=table_id,
                    status="pendiente",
                    waiter_id=current_user.id
                )
                table.status = "ocupada"
                db.session.add(table)
            else:
                customer_name = request.form.get('customer_name', 'Consumo en barra')
                new_order = Order(
                    customer_name=customer_name,
                    status="pendiente",
                    waiter_id=current_user.id,
                    table_id=None
                )

            db.session.add(new_order)
            db.session.flush()

            total = 0
            total_cervezas = 0
            for i, product_id in enumerate(product_ids):
                product = Product.query.get_or_404(product_id)
                quantity = int(quantities[i])
                exit_type = exit_types[i] if i < len(exit_types) else 'individual'

                if product.is_combo:
                    order_detail = OrderDetail(
                        order_id=new_order.id,
                        product_id=product.id,
                        quantity=quantity,
                        subtotal=product.price_usd * quantity,
                        exit_type='combo'
                    )
                    db.session.add(order_detail)
                    total += product.price_usd * quantity

                    if product.combo_items:
                        for item in product.combo_items:
                            component = Product.query.get(item.get('product_id'))
                            required_qty = item.get('quantity', 1) * quantity
                            if not component or component.quantity < required_qty:
                                db.session.rollback()
                                flash(f'Stock insuficiente para {component.name if component else "componente"}', 'danger')
                                return redirect(url_for('sales'))
                            component.quantity -= required_qty
                            movement = InventoryMovement(
                                product_id=component.id,
                                user_id=current_user.id,
                                movement_type='salida',
                                quantity=required_qty,
                                exit_type='combo',
                                notes=f'Componente de {product.name} (Orden #{new_order.id})'
                            )
                            db.session.add(movement)
                else:
                    if product.category == "Cerveza" and exit_type == "individual":
                        total_cervezas += quantity
                        order_detail = OrderDetail(
                            order_id=new_order.id,
                            product_id=product.id,
                            quantity=quantity,
                            subtotal=0,  # se recalcula abajo
                            exit_type=exit_type
                        )
                        db.session.add(order_detail)
                        product.quantity -= quantity
                        movement = InventoryMovement(
                            product_id=product.id,
                            user_id=current_user.id,
                            movement_type='salida',
                            quantity=quantity,
                            exit_type='venta',
                            notes=f'Despachado en orden #{new_order.id} (pendiente de pago)'
                        )
                        db.session.add(movement)
                    else:
                        if exit_type == 'half_tobo':
                            subtotal = product.price_half_tobo_usd
                            quantity = 6
                        elif exit_type == 'tobo':
                            subtotal = product.price_tobo_usd
                            quantity = 12
                        elif exit_type == 'half_box':
                            subtotal = product.price_half_box_usd
                            quantity = 18
                        elif exit_type == 'box':
                            subtotal = product.price_box_usd
                            quantity = 36
                        else:
                            subtotal = product.price_unit_usd * quantity

                        total += subtotal
                        order_detail = OrderDetail(
                            order_id=new_order.id,
                            product_id=product.id,
                            quantity=quantity,
                            subtotal=subtotal,
                            exit_type=exit_type
                        )
                        db.session.add(order_detail)
                        product.quantity -= quantity
                        movement = InventoryMovement(
                            product_id=product.id,
                            user_id=current_user.id,
                            movement_type='salida',
                            quantity=quantity,
                            exit_type=exit_type,
                            notes=f'Despachado en orden #{new_order.id} (pendiente de pago)',
                        )
                        db.session.add(movement)

            if total_cervezas > 0:
                referencia = Product.query.filter_by(category="Cerveza").first()
                total += calcular_precio_cervezas(total_cervezas, referencia)

            new_order.total_price = total
            db.session.commit()
            flash('Orden creada exitosamente', 'success')

            if sale_type == 'mesa':
                return redirect(url_for('view_order', table_id=table_id))
            else:
                return redirect(url_for('view_bar_order', order_id=new_order.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar orden: {str(e)}', 'danger')
            return redirect(url_for('sales'))


@app.route('/bar_order/<int:order_id>')
@login_required
def view_bar_order(order_id):
    order = Order.query.get_or_404(order_id)
    
    if order.status != "pendiente":
        flash('Esta orden ya ha sido pagada', 'warning')
        return redirect(url_for('sales_reports'))
    
    order_details = OrderDetail.query.filter_by(order_id=order.id).all()

    # Preparar combos con nombres de productos
    for detail in order_details:
        if detail.product.is_combo and detail.product.combo_items:
            enriched_items = []
            for combo_item in detail.product.combo_items:
                product = Product.query.get(combo_item.get('product_id'))
                if product:
                    enriched_items.append({
                        'name': product.name,
                        'quantity': combo_item.get('quantity', 1)
                    })
            detail.combo_contents = enriched_items  # <- atributo dinámico
    # Incluir TODOS los productos, no solo los con stock
    products = Product.query.all()
    payment_methods = PaymentMethod.query.filter_by(is_active=True).order_by(PaymentMethod.currency, PaymentMethod.name).all()
    
    return render_template('sales/order.html', 
                         order=order, 
                         order_details=order_details, 
                         products=products,
                         payment_methods=payment_methods,
                         is_bar_order=True,
                         table=None,
                         current_rate=get_current_rate())


@app.route('/add_product_to_bar_order/<int:order_id>', methods=['POST'])
@login_required
def add_product_to_bar_order(order_id):
    order = Order.query.get_or_404(order_id)

    if order.status != "pendiente":
        flash('No se pueden agregar productos a una orden pagada', 'danger')
        return redirect(url_for('view_bar_order', order_id=order_id))

    product = Product.query.get_or_404(request.form['product_id'])
    exit_type = request.form.get('exit_type', 'individual')
    quantity = int(request.form['quantity'])

    if product.is_combo:
        for item in product.combo_items:
            component = Product.query.get(item['product_id'])
            if not component or component.quantity < (item['quantity'] * quantity):
                flash(f'Stock insuficiente de {component.name if component else "componente"}', 'danger')
                return redirect(url_for('view_bar_order', order_id=order_id))

        subtotal = product.price_usd * quantity
        order_detail = OrderDetail(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            subtotal=subtotal,
            exit_type='combo'
        )
        order.total_price += subtotal

        for item in product.combo_items:
            component = Product.query.get(item['product_id'])
            component.quantity -= (item['quantity'] * quantity)
            movement = InventoryMovement(
                product_id=component.id,
                user_id=current_user.id,
                movement_type='salida',
                quantity=item['quantity'] * quantity,
                exit_type='combo',
                notes=f'Componente de {product.name} (Orden #{order.id})',
                is_locked=True
            )
            db.session.add(movement)

        try:
            db.session.add(order_detail)
            db.session.commit()
            flash(f'{quantity}x {product.name} agregado a la orden', 'success')
            return redirect(url_for('view_bar_order', order_id=order_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al agregar combo: {str(e)}', 'danger')
            return redirect(url_for('view_bar_order', order_id=order_id))

    if product.category == 'Cerveza' and exit_type == 'individual':
        cervezas_actuales = sum(d.quantity for d in order.products if d.product.category == "Cerveza" and not d.product.is_combo)
        total_cervezas = cervezas_actuales + quantity
        referencia = product
        subtotal_total = calcular_precio_cervezas(total_cervezas, referencia)
        subtotal_nuevo = subtotal_total - calcular_precio_cervezas(cervezas_actuales, referencia)
    else:
        if exit_type == 'half_tobo':
            subtotal_nuevo = product.price_half_tobo_usd
            quantity = 6
        elif exit_type == 'tobo':
            subtotal_nuevo = product.price_tobo_usd
            quantity = 12
        elif exit_type == 'half_box':
            subtotal_nuevo = product.price_half_box_usd
            quantity = 18
        elif exit_type == 'box':
            subtotal_nuevo = product.price_box_usd
            quantity = 36
        else:
            subtotal_nuevo = quantity * product.price_unit_usd

    if product.quantity < quantity:
        flash(f'Stock insuficiente de {product.name}', 'danger')
        return redirect(url_for('view_bar_order', order_id=order_id))

    order_detail = OrderDetail(
        order_id=order.id,
        product_id=product.id,
        quantity=quantity,
        subtotal=subtotal_nuevo,
        exit_type=exit_type
    )
    order.total_price += subtotal_nuevo
    product.quantity -= quantity
    movement = InventoryMovement(
        product_id=product.id,
        user_id=current_user.id,
        movement_type='salida',
        quantity=quantity,
        exit_type=exit_type if exit_type != 'individual' else 'venta',
        notes=f'Despachado en orden #{order.id} (pendiente de pago)',
        is_locked=True
    )

    try:
        db.session.add(order_detail)
        db.session.add(movement)
        db.session.commit()
        flash(f'{quantity}x {product.name} agregado a la orden', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al agregar producto: {str(e)}', 'danger')

    return redirect(url_for('view_bar_order', order_id=order_id))


@app.route('/close_bar_order/<int:order_id>', methods=['POST'])
@admin_required
def close_bar_order(order_id):
    order = Order.query.get_or_404(order_id)
    
    if order.status != "pendiente":
        flash('Esta orden ya ha sido pagada', 'warning')
        return redirect(url_for('view_bar_order', order_id=order_id))
    
    try:
        payment_currency = request.form['payment_currency']
        payment_method_id = int(request.form['payment_method'])
        payment_amount = float(request.form['payment_amount'])
        current_rate = get_current_rate()
        
        # Calcular montos
        if payment_currency == 'bs':
            payment_amount_usd = payment_amount
            
            print(f"Payment amount in USD: {payment_amount_usd}")
            payment_amount_bs = payment_amount_usd * current_rate
            print(f"Payment amount in bs: {payment_amount_bs}")
        else:  # USD
            payment_amount_usd = payment_amount
            print(f"Payment amount in USD: {payment_amount_usd}")
            payment_amount_bs = payment_amount * current_rate
            print(f"Payment amount in Bs: {payment_amount_bs}")
        
        # Validar pago
        if payment_currency == 'bs' and payment_amount_bs < order.total_price * current_rate:
            flash('El monto pagado no cubre el total', 'danger')
            return redirect(url_for('view_bar_order', order_id=order_id))
        
        # if payment_currency == 'usd' and payment_amount_usd < order.total_price:
        #     flash('El monto pagado no cubre el total', 'danger')
        #     return redirect(url_for('view_bar_order', order_id=order_id))
        
        # Actualizar orden (CORRECCIÓN PRINCIPAL: usar datetime.now())
        order.status = "pagado"
        order.closed_at = datetime.now()  # ¡Aquí estaba el error!
        order.payment_currency = payment_currency
        order.exchange_rate = current_rate
        order.payment_amount_bs = payment_amount_bs
        order.payment_amount_usd = payment_amount_usd
        order.payment_method_id = payment_method_id
        
        # Actualizar movimientos de inventario
        movements = InventoryMovement.query.filter(
            InventoryMovement.notes.like(f'%orden #{order.id}%')
        ).all()
        
        for mov in movements:
            mov.notes = mov.notes.replace('(pendiente de pago)', '(pagado)')
        
        db.session.commit()
        
        payment_method = PaymentMethod.query.get(payment_method_id)
        flash(f'Orden #{order.id} pagada con {payment_method.name} - ${payment_amount_usd:.2f} / {payment_amount_bs:.2f} Bs', 'success')
        return redirect(url_for('sales_reports'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al procesar pago: {str(e)}', 'danger')
        return redirect(url_for('view_bar_order', order_id=order_id))
    

@app.route('/bar_orders')
@login_required
def bar_orders():
    bar_orders = Order.query.filter(
        Order.status == 'pendiente',
        Order.table_id == None  # Órdenes sin mesa asignada
    ).all()
    return render_template('sales/bar_orders.html', orders=bar_orders)

if __name__ == '__main__':
    with app.app_context():
    # Eliminar todas las tablas (solo en desarrollo!)
        db.drop_all()
        
        # Crear todas las tablas con los nuevos esquemas
        db.create_all()

        # Crear métodos de pago iniciales si no existen
        if not PaymentMethod.query.first():
            payment_methods = [
                PaymentMethod(name='Efectivo USD', currency='usd'),
                PaymentMethod(name='Efectivo BS', currency='bs'),
                PaymentMethod(name='Pago Móvil', currency='bs'),
                PaymentMethod(name='Punto de Venta', currency='bs'),
                PaymentMethod(name='Transferencia', currency='bs')
            ]
            db.session.add_all(payment_methods)
        
        # Crear usuarios iniciales
        if not User.query.first():
            users = [
                User(username='admin', role='admin'),
                User(username='encargado', role='manager'),
                User(username='personal', role='staff')
            ]
            for user in users:
                user.set_password(user.username + '123')
                db.session.add(user)
            
            # Crear mesas
            for i in range(1, 6):
                db.session.add(Table(number=i))
            
            # Crear productos iniciales
            create_initial_products()
            
            db.session.commit()
    
    app.run(debug=True)