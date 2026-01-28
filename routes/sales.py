from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from py_exchange import db, get_current_rate, update_rate
from py_models import Product, Table, Order, OrderDetail, DailyClosure, PaymentMethod, InventoryMovement, calcular_precio_cervezas
from decorators import admin_required, manager_or_admin_required
from datetime import datetime

sales_bp = Blueprint('sales', __name__)

@sales_bp.route('/')
@login_required
def index():
    """Main dashboard showing stock and table status."""
    products = Product.query.all()
    low_stock_count = Product.query.filter(Product.quantity < 10).count()
    total_tables = Table.query.count()
    occupied_tables = Table.query.filter_by(status="ocupada").count()
    
    # Calculate daily sales (USD)
    today = datetime.now().date()
    daily_sales = db.session.query(db.func.sum(Order.payment_amount_usd))\
        .filter(Order.status == 'pagado', 
                db.func.date(Order.closed_at) == today).scalar() or 0.0
                
    return render_template('index.html', 
                         products=products, 
                         low_stock_count=low_stock_count,
                         total_tables=total_tables,
                         occupied_tables=occupied_tables,
                         daily_sales=daily_sales)

@sales_bp.route('/exchange_rate', methods=['GET', 'POST'])
@admin_required
def manage_exchange_rate():
    """Manage manual exchange rate."""
    if request.method == 'POST':
        new_rate = float(request.form['rate'])
        update_rate(new_rate)
        flash(f'Tasa de cambio actualizada a {new_rate} Bs/USD', 'success')
        return redirect(url_for('sales.manage_exchange_rate'))
    
    current_rate = get_current_rate()
    return render_template('sales/exchange_rate.html', current_rate=current_rate)

@sales_bp.route('/tables')
@login_required
def view_tables():
    """Display all tables and their statuses with lazy cleanup for empty orders."""
    tables = Table.query.order_by(Table.number).all()
    
    # Lazy Cleanup: If a table is 'ocupada' but has no items in its active order, reset it.
    # This happens when a waiter opens a table but doesn't add anything.
    cleaned = False
    for table in tables:
        if table.status == "ocupada":
            active_order = Order.query.filter_by(table_id=table.id, status="pendiente").first()
            if not active_order or not active_order.products:
                table.status = "disponible"
                if active_order:
                    db.session.delete(active_order)
                cleaned = True
    
    if cleaned:
        db.session.commit()
        # Refresh table list after cleanup
        tables = Table.query.order_by(Table.number).all()
        
    return render_template('sales/tables.html', tables=tables)

@sales_bp.route('/manage_tables')
@admin_required
def manage_tables():
    """Admin view to manage tables."""
    tables = Table.query.order_by(Table.number).all()
    return render_template('sales/manage_tables.html', tables=tables)

@sales_bp.route('/create_table', methods=['POST'])
@admin_required
def create_table():
    """Create a new table."""
    try:
        table_number = request.form['number']
        if Table.query.filter_by(number=table_number).first():
            flash(f'La mesa {table_number} ya existe', 'warning')
        else:
            new_table = Table(number=table_number)
            db.session.add(new_table)
            db.session.commit()
            flash('Mesa creada exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear mesa: {str(e)}', 'danger')
    return redirect(url_for('sales.manage_tables'))

@sales_bp.route('/edit_table/<int:table_id>', methods=['POST'])
@admin_required
def edit_table(table_id):
    """Edit table number/name."""
    table = Table.query.get_or_404(table_id)
    try:
        new_number = request.form['number']
        existing = Table.query.filter_by(number=new_number).first()
        if existing and existing.id != table_id:
            flash(f'Esa mesa ya existe', 'warning')
        else:
            table.number = new_number
            db.session.commit()
            flash('Mesa actualizada', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('sales.manage_tables'))

@sales_bp.route('/delete_table/<int:table_id>')
@admin_required
def delete_table(table_id):
    """Delete a table if it's not occupied."""
    table = Table.query.get_or_404(table_id)
    if table.status == "ocupada":
        flash('No se puede eliminar una mesa ocupada', 'danger')
    else:
        try:
            db.session.delete(table)
            db.session.commit()
            flash('Mesa eliminada', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('sales.manage_tables'))

@sales_bp.route('/create_order/<int:table_id>')
@login_required
def create_order(table_id):
    """Initiate an order for a table."""
    table = Table.query.get_or_404(table_id)
    if table.status != "disponible":
        active_order = Order.query.filter_by(table_id=table.id, status="pendiente").first()
        if active_order:
            return redirect(url_for('sales.view_order', table_id=table.id))
        table.status = "disponible"
        db.session.commit()
    
    new_order = Order(table_id=table_id, waiter_id=current_user.id, status="pendiente")
    table.status = "ocupada"
    try:
        db.session.add(new_order)
        db.session.commit()
        return redirect(url_for('sales.view_order', table_id=table.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear pedido: {str(e)}', 'danger')
        return redirect(url_for('sales.view_tables'))

@sales_bp.route('/order/<int:table_id>')
@login_required
def view_order(table_id):
    """View active order for a table."""
    table = Table.query.get_or_404(table_id)
    active_order = Order.query.filter_by(table_id=table.id, status="pendiente").first()
    if not active_order:
        flash('No hay pedido activo', 'warning')
        return redirect(url_for('sales.view_tables'))
    
    order_details = OrderDetail.query.filter_by(order_id=active_order.id).all()
    
    # Enriquecer detalles con contenido de combos
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
            detail.combo_contents = enriched_items
            
    # Preparar productos para el selector y combos (mismo formato que sales)
    products_data = []
    for p in Product.query.all():
        products_data.append({
            'id': p.id,
            'name': p.name,
            'price_usd': float(p.price_usd),
            'price_unit_usd': float(p.price_unit_usd or p.price_usd),
            'price_half_tobo_usd': float(p.price_half_tobo_usd or 0),
            'price_tobo_usd': float(p.price_tobo_usd or 0),
            'price_half_box_usd': float(p.price_half_box_usd or 0),
            'price_box_usd': float(p.price_box_usd or 0),
            'quantity': p.quantity,
            'is_combo': p.is_combo,
            'category': p.category,
            'combo_items': p.combo_items
        })
            
    payment_methods = PaymentMethod.query.filter_by(is_active=True).all()
    
    return render_template('sales/order.html', 
                         order=active_order, 
                         order_details=order_details, 
                         products=products_data,
                         table=table,
                         payment_methods=payment_methods,
                         current_rate=get_current_rate(),
                         is_bar_order=False)

def _add_product_to_order(order, product_id, quantity, exit_type):
    """Helper to add a product to an order with full inventory tracking."""
    product = Product.query.get_or_404(product_id)
    
    # Validar stock
    if product.is_combo:
        for item in product.combo_items:
            component = Product.query.get(item['product_id'])
            required_qty = item['quantity'] * quantity
            if not component or component.quantity < required_qty:
                return False, f'Stock insuficiente para {component.name if component else "componente"}'
    else:
        # Mapeo de unidades reales por tipo de salida
        unit_multiplier = {
            'half_tobo': 6,
            'tobo': 12,
            'half_box': 18,
            'box': 36
        }
        actual_units = quantity * unit_multiplier.get(exit_type, 1)
        if product.quantity < actual_units:
            return False, f'Stock insuficiente de {product.name}'

    # Calcular subtotal
    if product.is_combo:
        subtotal = product.price_usd * quantity
    elif product.category == 'Cerveza' and exit_type == 'individual':
        # Calcular basado en el total de cervezas individuales en la orden
        cervezas_actuales = sum(d.quantity for d in order.products if d.product.category == "Cerveza" and d.exit_type == 'individual')
        total_cervezas = cervezas_actuales + quantity
        subtotal = calcular_precio_cervezas(total_cervezas, product) - calcular_precio_cervezas(cervezas_actuales, product)
    else:
        prices = {
            'half_tobo': product.price_half_tobo_usd,
            'tobo': product.price_tobo_usd,
            'half_box': product.price_half_box_usd,
            'box': product.price_box_usd
        }
        subtotal = prices.get(exit_type, quantity * (product.price_unit_usd or product.price_usd))

    # Registrar detalle
    detail = OrderDetail(
        order_id=order.id, 
        product_id=product.id, 
        quantity=quantity if product.is_combo or product.category != 'Cerveza' or exit_type != 'individual' else quantity,
        # Nota: quantity en OrderDetail representa las unidades vendidas segun el etype
        subtotal=subtotal, 
        exit_type=exit_type
    )
    
    # Ajustar cantidad real para productos no combo (en OrderDetail guardamos lo solicitado, 
    # pero en stock descontamos unidades reales)
    if not product.is_combo:
         unit_mult = {'half_tobo': 6, 'tobo': 12, 'half_box': 18, 'box': 36}.get(exit_type, 1)
         detail.quantity = quantity * unit_mult

    order.total_price += subtotal
    
    # Procesar inventario
    if product.is_combo:
        for item in product.combo_items:
            comp = Product.query.get(item['product_id'])
            deduction = item['quantity'] * quantity
            comp.quantity -= deduction
            db.session.add(InventoryMovement(
                product_id=comp.id, user_id=current_user.id, movement_type='salida', 
                quantity=deduction, exit_type='combo', is_locked=True,
                notes=f'Componente combo {product.name} (Orden #{order.id})'
            ))
    else:
        product.quantity -= detail.quantity
        db.session.add(InventoryMovement(
            product_id=product.id, user_id=current_user.id, movement_type='salida',
            quantity=detail.quantity, exit_type=exit_type, is_locked=True,
            notes=f'Agregado a Orden #{order.id}'
        ))
    
    db.session.add(detail)
    return True, "Producto agregado"

@sales_bp.route('/add_product/<int:table_id>', methods=['POST'])
@login_required
def add_product(table_id):
    """Add a product to an existing table order."""
    table = Table.query.get_or_404(table_id)
    order = Order.query.filter_by(table_id=table_id, status="pendiente").first_or_404()
    
    success, message = _add_product_to_order(
        order, 
        request.form['product_id'], 
        int(request.form['quantity']), 
        request.form.get('exit_type', 'individual')
    )
    
    if success:
        try:
            db.session.commit()
            flash(message, 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar: {str(e)}', 'danger')
    else:
        flash(message, 'danger')
        
    return redirect(url_for('sales.view_order', table_id=table_id))

@sales_bp.route('/close_order/<int:table_id>', methods=['POST'])
@admin_required
def close_order(table_id):
    """Process payment and close a table order."""
    active_order = Order.query.filter_by(table_id=table_id, status="pendiente").first_or_404()
    payment_currency = request.form['payment_currency']
    payment_method_id = int(request.form['payment_method'])
    payment_amount = float(request.form['payment_amount'])
    current_rate = get_current_rate()
    
    payment_amount_bs = payment_amount if payment_currency == 'bs' else payment_amount * current_rate
    payment_amount_usd = payment_amount if payment_currency == 'usd' else payment_amount / current_rate
    
    if payment_currency == 'bs' and payment_amount_bs < active_order.total_price * current_rate:
        flash('Monto insuficiente', 'danger')
        return redirect(url_for('sales.view_order', table_id=table_id))
    
    active_order.status = "pagado"
    active_order.closed_at = datetime.now()
    active_order.payment_currency = payment_currency
    active_order.exchange_rate = current_rate
    active_order.payment_amount_bs = payment_amount_bs
    active_order.payment_amount_usd = payment_amount_usd
    active_order.payment_method_id = payment_method_id
    active_order.table.status = "disponible"
    
    try:
        db.session.commit()
        flash(f'Pedido #{active_order.id} pagado exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cerrar pedido: {str(e)}', 'danger')
    return redirect(url_for('sales.view_tables'))

@sales_bp.route('/sales', methods=['GET', 'POST'])
@login_required
def sales():
    """Main sales selection view."""
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
            'available_quantity': float('inf'),
            'category': 'Combo'
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

    # Preparar datos unificados para la plantilla
    products_data = []
    
    # Agregar productos individuales
    for p in individual_products:
        products_data.append({
            'id': p.id,
            'name': p.name,
            'price_usd': float(p.price_usd),
            'price_unit_usd': float(p.price_unit_usd or p.price_usd),
            'price_half_tobo_usd': float(p.price_half_tobo_usd or 0),
            'price_tobo_usd': float(p.price_tobo_usd or 0),
            'price_half_box_usd': float(p.price_half_box_usd or 0),
            'price_box_usd': float(p.price_box_usd or 0),
            'quantity': p.quantity,
            'is_combo': False,
            'available_quantity': p.quantity,
            'category': p.category
        })
    
    # Agregar combos
    products_data.extend(available_combos)

    # Convertir mesas a formato serializable
    tables_data = [{
        'id': t.id,
        'number': t.number,
        'status': t.status
    } for t in Table.query.all()]
    
    return render_template('sales/sales.html', 
                         products=products_data, 
                         tables=tables_data,
                         current_rate=get_current_rate())

@sales_bp.route('/register_sale', methods=['POST'])
@login_required
def register_sale():
    """Register a new quick sale or mesa order with full inventory tracking."""
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
                    return redirect(url_for('sales.sales'))

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
            cerveza_ref = None

            for i, product_id in enumerate(product_ids):
                product = Product.query.get_or_404(product_id)
                quantity = int(quantities[i])
                exit_type = exit_types[i] if i < len(exit_types) else 'individual'

                if product.is_combo:
                    # Validar stock de componentes
                    if product.combo_items:
                        for item in product.combo_items:
                            component = Product.query.get(item.get('product_id'))
                            required_qty = item.get('quantity', 1) * quantity
                            if not component or component.quantity < required_qty:
                                db.session.rollback()
                                flash(f'Stock insuficiente para {component.name if component else "componente"}', 'danger')
                                return redirect(url_for('sales.sales'))
                            
                            component.quantity -= required_qty
                            db.session.add(InventoryMovement(
                                product_id=component.id,
                                user_id=current_user.id,
                                movement_type='salida',
                                quantity=required_qty,
                                exit_type='combo',
                                notes=f'Componente de {product.name} (Orden #{new_order.id})',
                                is_locked=True
                            ))

                    subtotal = product.price_usd * quantity
                    total += subtotal
                    db.session.add(OrderDetail(
                        order_id=new_order.id,
                        product_id=product.id,
                        quantity=quantity,
                        subtotal=subtotal,
                        exit_type='combo'
                    ))
                else:
                    if product.category == "Cerveza" and exit_type == "individual":
                        total_cervezas += quantity
                        cerveza_ref = product
                        db.session.add(OrderDetail(
                            order_id=new_order.id,
                            product_id=product.id,
                            quantity=quantity,
                            subtotal=0,  # Se calcula al final
                            exit_type=exit_type
                        ))
                    else:
                        prices = {
                            'half_tobo': product.price_half_tobo_usd,
                            'tobo': product.price_tobo_usd,
                            'half_box': product.price_half_box_usd,
                            'box': product.price_box_usd
                        }
                        
                        # Mapeo de unidades reales por tipo de salida
                        unit_multiplier = {
                            'half_tobo': 6,
                            'tobo': 12,
                            'half_box': 18,
                            'box': 36
                        }
                        
                        actual_units = quantity * unit_multiplier.get(exit_type, 1)
                        subtotal = prices.get(exit_type, quantity * (product.price_unit_usd or product.price_usd))
                        
                        if product.quantity < actual_units:
                            db.session.rollback()
                            flash(f'Stock insuficiente de {product.name}', 'danger')
                            return redirect(url_for('sales.sales'))

                        total += subtotal
                        product.quantity -= actual_units
                        db.session.add(OrderDetail(
                            order_id=new_order.id,
                            product_id=product.id,
                            quantity=actual_units,
                            subtotal=subtotal,
                            exit_type=exit_type
                        ))
                        db.session.add(InventoryMovement(
                            product_id=product.id,
                            user_id=current_user.id,
                            movement_type='salida',
                            quantity=actual_units,
                            exit_type=exit_type,
                            notes=f'Venta (Orden #{new_order.id})',
                            is_locked=True
                        ))

            if total_cervezas > 0:
                beer_subtotal = calcular_precio_cervezas(total_cervezas, cerveza_ref)
                total += beer_subtotal
                cerveza_ref.quantity -= total_cervezas
                db.session.add(InventoryMovement(
                    product_id=cerveza_ref.id,
                    user_id=current_user.id,
                    movement_type='salida',
                    quantity=total_cervezas,
                    exit_type='venta',
                    notes=f'Venta Cervezas (Orden #{new_order.id})',
                    is_locked=True
                ))

            new_order.total_price = total
            db.session.commit()
            flash('Orden creada exitosamente', 'success')

            if sale_type == 'mesa':
                return redirect(url_for('sales.view_order', table_id=table_id))
            else:
                return redirect(url_for('sales.view_bar_order', order_id=new_order.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar orden: {str(e)}', 'danger')
            return redirect(url_for('sales.sales'))

@sales_bp.route('/bar_order/<int:order_id>')
@login_required
def view_bar_order(order_id):
    """View and pay a bar order."""
    order = Order.query.get_or_404(order_id)
    if order.status != "pendiente":
        return redirect(url_for('sales.sales_reports'))
    
    order_details = OrderDetail.query.filter_by(order_id=order.id).all()
    
    # Preparar productos para el selector y combos (mismo formato que sales)
    products_data = []
    for p in Product.query.all():
        products_data.append({
            'id': p.id,
            'name': p.name,
            'price_usd': float(p.price_usd),
            'price_unit_usd': float(p.price_unit_usd or p.price_usd),
            'price_half_tobo_usd': float(p.price_half_tobo_usd or 0),
            'price_tobo_usd': float(p.price_tobo_usd or 0),
            'price_half_box_usd': float(p.price_half_box_usd or 0),
            'price_box_usd': float(p.price_box_usd or 0),
            'quantity': p.quantity,
            'is_combo': p.is_combo,
            'category': p.category,
            'combo_items': p.combo_items
        })

    payment_methods = PaymentMethod.query.filter_by(is_active=True).all()
    return render_template('sales/order.html', 
                         order=order, 
                         order_details=order_details, 
                         products=products_data, 
                         payment_methods=payment_methods, 
                         is_bar_order=True, 
                         current_rate=get_current_rate())

@sales_bp.route('/add_product_to_bar_order/<int:order_id>', methods=['POST'])
@login_required
def add_product_to_bar_order(order_id):
    """Add a product to an existing bar order."""
    order = Order.query.get_or_404(order_id)
    if order.status != "pendiente":
        flash("La orden ya está cerrada", "warning")
        return redirect(url_for('sales.sales_reports'))

    success, message = _add_product_to_order(
        order, 
        request.form['product_id'], 
        int(request.form['quantity']), 
        request.form.get('exit_type', 'individual')
    )
    
    if success:
        try:
            db.session.commit()
            flash(message, 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar: {str(e)}', 'danger')
    else:
        flash(message, 'danger')
        
    return redirect(url_for('sales.view_bar_order', order_id=order_id))

@sales_bp.route('/close_bar_order/<int:order_id>', methods=['POST'])
@admin_required
def close_bar_order(order_id):
    """Close a bar order (payment)."""
    order = Order.query.get_or_404(order_id)
    payment_currency = request.form['payment_currency']
    payment_method_id = int(request.form['payment_method'])
    payment_amount = float(request.form['payment_amount'])
    current_rate = get_current_rate()
    
    order.status = "pagado"
    order.closed_at = datetime.now()
    order.payment_currency = payment_currency
    order.exchange_rate = current_rate
    order.payment_amount_usd = payment_amount if payment_currency == 'usd' else payment_amount / current_rate
    order.payment_amount_bs = payment_amount if payment_currency == 'bs' else payment_amount * current_rate
    order.payment_method_id = payment_method_id
    
    try:
        db.session.commit()
        flash('Venta en barra pagada', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('sales.sales_reports'))

@sales_bp.route('/sales_reports')
@login_required
def sales_reports():
    """View sales history and reports."""
    completed_orders = Order.query.filter_by(status="pagado").order_by(Order.closed_at.desc()).all()
    closures = DailyClosure.query.order_by(DailyClosure.date.desc()).all()
    pending_total_sales = sum(o.total_price for o in Order.query.filter_by(status="pagado", closure_id=None).all())
    
    return render_template('sales/sales_reports.html', 
                         orders=completed_orders,
                         closures=closures,
                         pending_total_sales=pending_total_sales,
                         current_rate=get_current_rate())

@sales_bp.route('/daily_closure', methods=['GET', 'POST'])
@admin_required
def daily_closure():
    """Perform end-of-day closure."""
    pending_orders = Order.query.filter_by(status="pagado", closure_id=None).all()
    total_usd = sum(o.payment_amount_usd or 0 for o in pending_orders)
    total_bs = sum(o.payment_amount_bs or 0 for o in pending_orders)
    
    if request.method == 'POST':
        try:
            closure = DailyClosure(
                total_usd=total_usd,
                total_bs=total_bs,
                orders_count=len(pending_orders),
                observations=request.form.get('observations', ''),
                closed_by=current_user.id,
                date=datetime.now()
            )
            db.session.add(closure)
            db.session.flush()
            for o in pending_orders:
                o.closure_id = closure.id
            db.session.commit()
            flash('Cierre realizado exitosamente', 'success')
            return redirect(url_for('sales.sales_reports'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')

    # Calculate method breakdown for display
    method_totals = {}
    for o in pending_orders:
        method_name = o.payment_method.name if o.payment_method else "Sin método"
        if method_name not in method_totals:
            method_totals[method_name] = {
                'usd': 0.0,
                'bs': 0.0,
                'currency': o.payment_method.currency.upper() if o.payment_method else 'USD'
            }
        
        method_totals[method_name]['usd'] += o.payment_amount_usd or 0.0
        method_totals[method_name]['bs'] += o.payment_amount_bs or 0.0
            
    return render_template('sales/daily_closure.html', 
                         orders=pending_orders, 
                         total_usd=total_usd, 
                         total_bs=total_bs,
                         method_totals=method_totals)

@sales_bp.route('/bar_orders')
@login_required
def bar_orders():
    """View pending bar orders."""
    orders = Order.query.filter_by(status='pendiente', table_id=None).all()
    return render_template('sales/bar_orders.html', orders=orders, current_rate=get_current_rate())
