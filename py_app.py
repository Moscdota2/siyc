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
    low_stock = Product.query.filter(Product.quantity < 10).count()
    return render_template('index.html', products=products, low_stock=low_stock)

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
            db.session.commit()
            flash('Producto creado exitosamente', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear producto: {str(e)}', 'danger')
    return render_template('create_product.html')

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
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar producto: {str(e)}', 'danger')
    return render_template('update_product.html', product=product)

@app.route('/delete_product/<int:id>')
@admin_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    try:
        db.session.delete(product)
        db.session.commit()
        flash('Producto eliminado exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar producto: {str(e)}', 'danger')
    return redirect(url_for('index'))

@app.route('/inventory_entry', methods=['GET', 'POST'])
@manager_or_admin_required
def inventory_entry():
    if request.method == 'POST':
        product_id = request.form['product_id']
        boxes = float(request.form['boxes'])
        product_type = request.form.get('product_type', '')
        
        product = Product.query.get_or_404(product_id)
        
        if product_type == 'cerveza':
            units_per_box = 36
        elif product_type == 'ron':
            units_per_box = 6
        else:
            units_per_box = 1
        
        units = int(boxes * units_per_box)
        
        product.quantity += units
        product.box_quantity += boxes
        
        movement = InventoryMovement(
            product_id=product.id,
            user_id=current_user.id,
            movement_type='entrada',
            quantity=units,
            notes=f"Entrada de {boxes} cajas de {product.name} ({units} unidades)"
        )
        
        try:
            db.session.add(movement)
            db.session.commit()
            flash(f"✅ {units} unidades de {product.name} agregadas", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Error al registrar entrada: {str(e)}", 'danger')
        
        return redirect(url_for('inventory_entry'))
    
    # Obtener productos agrupados
    beers = Product.query.filter_by(category='Cerveza').all()
    rums = Product.query.filter_by(category='Ron').all()
    
    return render_template(
        'inventory_entry.html',
        products=beers + rums
    )

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
    return render_template('tables.html', tables=tables)

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
        flash('La mesa ya tiene un pedido activo', 'warning')
        return redirect(url_for('view_tables'))
    
    new_order = Order(table_id=table_id)
    table.status = "ocupada"
    
    try:
        db.session.add(new_order)
        db.session.commit()
        flash(f'Pedido creado para Mesa {table.number}', 'success')
        return redirect(url_for('view_order', order_id=new_order.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear pedido: {str(e)}', 'danger')
        return redirect(url_for('view_tables'))

@app.route('/order/<int:order_id>')
@login_required
def view_order(order_id):
    order = Order.query.get_or_404(order_id)
    order_details = OrderDetail.query.filter_by(order_id=order.id).all()
    products = Product.query.filter(Product.quantity > 0).all()
    return render_template('order.html', 
                         order=order, 
                         order_details=order_details, 
                         products=products)

@app.route('/add_product/<int:order_id>', methods=['POST'])
@login_required
def add_product(order_id):
    order = Order.query.get_or_404(order_id)
    product = Product.query.get_or_404(request.form['product_id'])
    quantity = int(request.form['quantity'])
    
    if product.quantity < quantity:
        flash(f'Stock insuficiente de {product.name}', 'danger')
        return redirect(url_for('view_order', order_id=order.id))
    
    subtotal = product.price_usd * quantity
    order_detail = OrderDetail(
        order_id=order.id,
        product_id=product.id,
        quantity=quantity,
        subtotal=subtotal,
        exit_type='individual'  # Asumimos venta individual en pedidos
    )
    
    order.total_price += subtotal
    product.quantity -= quantity
    
    try:
        db.session.add(order_detail)
        db.session.commit()
        flash(f'{quantity}x {product.name} agregado al pedido', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al agregar producto: {str(e)}', 'danger')
    
    return redirect(url_for('view_order', order_id=order.id))

@app.route('/close_order/<int:order_id>')
@login_required
def close_order(order_id):
    order = Order.query.get_or_404(order_id)
    table = order.table
    
    order.status = "pagado"
    table.status = "disponible"
    
    try:
        db.session.commit()
        flash(f'Pedido #{order.id} cerrado. Mesa {table.number} liberada', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cerrar pedido: {str(e)}', 'danger')
    
    return redirect(url_for('view_tables'))

# Auditoría
@app.route('/inventory_history')
@manager_or_admin_required
def inventory_history():
    movements = InventoryMovement.query.order_by(InventoryMovement.movement_date.desc()).all()
    return render_template('inventory_history.html', movements=movements)

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

if __name__ == '__main__':
    with app.app_context():
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