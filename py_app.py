from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, login_user, login_required, current_user, logout_user
from functools import wraps
from py_models import db, User, Product, Table, Order, OrderDetail, InventoryMovement, create_initial_products
from py_bcv import precio_bcv_actual
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

# En la ruta de inventory_entry
@app.route('/inventory_entry', methods=['GET', 'POST'])
@manager_or_admin_required
def inventory_entry():
    if request.method == 'POST':
        product_id = request.form['product_id']
        boxes = float(request.form['boxes'])
        product_type = request.form.get('product_type', '')
        currency = request.form['currency']  # 'usd' o 'bs'
        purchase_price = float(request.form['purchase_price'])
        distributor = request.form['distributor']  # 'polar' o 'regional'
        
        product = Product.query.get_or_404(product_id)
        
        # Calcular unidades por caja según tipo de producto
        if product_type == 'cerveza':
            units_per_box = 36
        elif product_type == 'ron':
            units_per_box = 6
        else:
            units_per_box = 1
        
        units = int(boxes * units_per_box)
        
        # Calcular precio en dólares según moneda de pago y distribuidor
        if currency == 'bs':
            if distributor == 'polar':
                # Polar en BS: $20.80 por caja
                usd_price_per_box = 20.80
            else:
                # Regional en BS: $19.50 por caja
                usd_price_per_box = 19.50
        else:
            if distributor == 'polar':
                # Polar en USD: $17 por caja
                usd_price_per_box = 17.00
            else:
                # Regional en USD: $19 por caja
                usd_price_per_box = 19.00
        
        total_usd_investment = boxes * usd_price_per_box
        
        # Actualizar inventario
        product.quantity += units
        product.box_quantity += boxes
        
        # Registrar movimiento con detalles financieros
        movement = InventoryMovement(
            product_id=product.id,
            user_id=current_user.id,
            movement_type='entrada',
            quantity=units,
            currency=currency,
            purchase_price=purchase_price,
            distributor=distributor,
            notes=f"Entrada de {boxes} cajas de {product.name} ({units} unidades) | {distributor} | {currency.upper()}"
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
    
    return render_template(
        "inventory/inventory_entry.html",
        products=beers + rums,
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
        
        # Calcular cantidad según tipo de salida
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
        # En lugar de mostrar warning, redirigir al pedido activo
        active_order = Order.query.filter_by(table_id=table.id, status="pendiente").first()
        if active_order:
            return redirect(url_for('view_order', table_id=table.id))
        else:
            # Si no hay orden activa pero la mesa está marcada como ocupada, corregir estado
            table.status = "disponible"
            db.session.commit()
            flash('Estado de mesa corregido', 'info')
            return redirect(url_for('view_tables'))
    
    new_order = Order(table_id=table_id)
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
    
    # Buscar la orden activa (no pagada) para esta mesa
    active_order = Order.query.filter_by(table_id=table.id, status="pendiente").first()
    
    if not active_order:
        flash('No hay pedido activo para esta mesa', 'warning')
        return redirect(url_for('view_tables'))
    
    order_details = OrderDetail.query.filter_by(order_id=active_order.id).all()
    products = Product.query.filter(Product.quantity > 0).all()
    
    return render_template('sales/order.html', 
                         order=active_order, 
                         order_details=order_details, 
                         products=products,
                         table=table)

@app.route('/add_product/<int:table_id>', methods=['POST'])
@login_required
def add_product(table_id):
    # Obtener la orden activa para esta mesa
    active_order = Order.query.filter_by(table_id=table_id, status="pendiente").first()
    if not active_order:
        flash('No hay pedido activo para esta mesa', 'danger')
        return redirect(url_for('view_tables'))
    
    product = Product.query.get_or_404(request.form['product_id'])
    quantity = int(request.form['quantity'])
    
    if product.quantity < quantity:
        flash(f'Stock insuficiente de {product.name}', 'danger')
        return redirect(url_for('view_order', table_id=table_id))
    
    subtotal = product.price_usd * quantity
    order_detail = OrderDetail(
        order_id=active_order.id,
        product_id=product.id,
        quantity=quantity,
        subtotal=subtotal,
        exit_type='individual'
    )
    
    active_order.total_price += subtotal
    product.quantity -= quantity
    
    try:
        db.session.add(order_detail)
        db.session.commit()
        flash(f'{quantity}x {product.name} agregado al pedido', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al agregar producto: {str(e)}', 'danger')
    
    return redirect(url_for('view_order', table_id=table_id))

@app.route('/close_order/<int:table_id>')
@login_required
def close_order(table_id):
    # Obtener la orden activa para esta mesa
    active_order = Order.query.filter_by(table_id=table_id, status="pendiente").first()
    if not active_order:
        flash('No hay pedido activo para esta mesa', 'danger')
        return redirect(url_for('view_tables'))
    
    table = active_order.table
    
    active_order.status = "pagado"
    table.status = "disponible"
    
    try:
        db.session.commit()
        flash(f'Pedido #{active_order.id} cerrado. Mesa {table.number} liberada', 'success')
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


# Ventas/Consumo
@app.route('/sales', methods=['GET', 'POST'])
@login_required
def sales():
    if request.method == 'POST':
        # Procesar el formulario de venta
        sale_type = request.form['sale_type']
        
        if sale_type == 'mesa':
            table_id = request.form['table_id']
            # Procesar orden para mesa
        elif sale_type == 'barra':
            customer_name = request.form.get('customer_name', 'Consumo en barra')
            # Procesar orden para barra
        
        # Procesar productos
        # ...
        
        return redirect(url_for('sales'))
    
    products = Product.query.filter(Product.quantity > 0).all()
    tables = Table.query.all()
    return render_template('sales/sales.html', products=products, tables=tables)



@app.route('/sales_reports')
@login_required
def sales_reports():
    # Obtener todas las órdenes pagadas
    completed_orders = Order.query.filter_by(status="pagado").all()
    
    # Calcular total de ventas
    total_sales = sum(order.total_price for order in completed_orders)
    
    return render_template('sales/sales_reports.html', 
                         orders=completed_orders,
                         total_sales=total_sales)

@app.route('/register_sale', methods=['POST'])
@login_required
def register_sale():
    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            sale_type = request.form['sale_type']
            product_ids = request.form.getlist('product_id[]')
            quantities = request.form.getlist('quantity[]')
            
            # Crear nueva orden
            if sale_type == 'mesa':
                table_id = request.form['table_id']
                new_order = Order(table_id=table_id)
            else:
                customer_name = request.form.get('customer_name', 'Consumo en barra')
                new_order = Order(customer_name=customer_name)
            
            db.session.add(new_order)
            db.session.flush()  # Para obtener el ID de la orden
            
            # Procesar productos
            total = 0
            for product_id, quantity in zip(product_ids, quantities):
                product = Product.query.get_or_404(product_id)
                quantity = int(quantity)
                
                if product.quantity < quantity:
                    flash(f'Stock insuficiente de {product.name}', 'danger')
                    return redirect(url_for('sales'))
                
                subtotal = product.price_usd * quantity
                total += subtotal
                
                order_detail = OrderDetail(
                    order_id=new_order.id,
                    product_id=product.id,
                    quantity=quantity,
                    subtotal=subtotal,
                    exit_type='individual'
                )
                
                # Actualizar inventario
                product.quantity -= quantity
                db.session.add(order_detail)
            
            # Actualizar total de la orden
            new_order.total_price = total
            
            # Si es una mesa, marcarla como ocupada
            if sale_type == 'mesa':
                table = Table.query.get_or_404(request.form['table_id'])
                table.status = "ocupada"
            
            db.session.commit()
            flash('Venta registrada exitosamente', 'success')
            return redirect(url_for('sales'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar venta: {str(e)}', 'danger')
            return redirect(url_for('sales'))

if __name__ == '__main__':
    with app.app_context():
    # Eliminar todas las tablas (solo en desarrollo!)
        db.drop_all()
        
        # Crear todas las tablas con los nuevos esquemas
        db.create_all()
        
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