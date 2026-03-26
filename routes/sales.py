from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from exchange import db, get_current_rate, update_rate
from models import Product, Table, Order, OrderDetail, DailyClosure, PaymentMethod, InventoryMovement
from decorators import admin_required, manager_or_admin_required
from logic import calculate_beer_price
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
    Table.cleanup_empty_orders()
        
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
        active_order = Order.query.filter(
            Order.table_id == table.id, 
            Order.status.in_(['pendiente', 'parcial'])
        ).first()
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
    active_order = Order.query.filter(
        Order.table_id == table.id,
        Order.status.in_(['pendiente', 'parcial'])
    ).first()
    if not active_order:
        flash('No hay pedido activo', 'warning')
        return redirect(url_for('sales.view_tables'))
    
    # Calculate remaining balance
    if active_order.total_paid_usd == 0 and active_order.payments:
        active_order.total_paid_usd = sum(p.amount for p in active_order.payments)
        active_order.total_paid_bs = sum(p.amount * (p.exchange_rate or 0) for p in active_order.payments)
        db.session.commit()
        
    remaining_balance = active_order.total_price - (active_order.total_paid_usd or 0.0)
    
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
                         remaining_balance=remaining_balance,
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
        # La cantidad recibida ya representa las unidades totales (e.g. 6 para medio tobo)
        actual_units = quantity
        if product.quantity < actual_units:
            return False, f'Stock insuficiente de {product.name}'

    # Calcular subtotal
    if product.is_combo:
        subtotal = product.price_usd * quantity
    elif product.category == 'Cerveza' and exit_type == 'individual':
        cervezas_actuales = sum(d.quantity for d in order.products if d.product.category == "Cerveza" and d.exit_type == 'individual')
        total_cervezas = cervezas_actuales + quantity
        subtotal = calculate_beer_price(total_cervezas, product) - calculate_beer_price(cervezas_actuales, product)
    else:
        prices = {
            'half_tobo': product.price_half_tobo_usd,
            'tobo': product.price_tobo_usd,
            'half_box': product.price_half_box_usd,
            'box': product.price_box_usd
        }
        # Determinar base_price con fallback seguro a 0.0
        base_price = prices.get(exit_type) or product.price_unit_usd or product.price_usd or 0.0
        try:
            base_price = float(base_price)
        except Exception:
            base_price = 0.0
        mult = unit_multiplier.get(exit_type, 1) if exit_type != 'individual' else 1
        # Si es un pack, el precio es por pack, calculamos cuántos packs hay en la cantidad de unidades
        if mult > 0:
            subtotal = (quantity / mult) * base_price
        else:
            subtotal = quantity * base_price

    # Registrar detalle
    detail = OrderDetail(
        order_id=order.id, 
        product_id=product.id, 
        quantity=quantity,
        subtotal=subtotal, 
        exit_type=exit_type
    )
    
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
        product.quantity -= actual_units
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
    order = Order.query.filter(
        Order.table_id == table_id, 
        Order.status.in_(['pendiente', 'parcial'])
    ).first_or_404()
    
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
@login_required
def close_order(table_id):
    """Process payment and close a table order."""
    active_order = Order.query.filter_by(table_id=table_id, status="pendiente").first_or_404()
    payment_currency = request.form['payment_currency']
    payment_method_id = int(request.form['payment_method'])
    payment_amount = float(request.form['payment_amount'])
    current_rate = get_current_rate()
    
    # Normalize amounts (avoid division by zero)
    payment_amount_bs = payment_amount if payment_currency == 'bs' else payment_amount * current_rate
    payment_amount_usd = payment_amount if payment_currency == 'usd' else (payment_amount / current_rate if current_rate else 0.0)

    # Comparación con tolerancia para evitar fallos por redondeo
    required_bs = round(active_order.total_price * current_rate, 2)
    paid_bs = round(payment_amount_bs, 2)
    # Permitimos una pequeña diferencia (1 centavo) al comparar
    if payment_currency == 'bs' and (paid_bs + 0.01) < required_bs:
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
            'category': p.category,
            'cost_usd': float(p.cost_per_unit_usd or 0)
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
            order_type = request.form.get('order_type', 'venta')
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
                    order_type=order_type,
                    waiter_id=current_user.id
                )
                table.status = "ocupada"
                db.session.add(table)
            else:
                customer_name = request.form.get('customer_name', 'Consumo en barra')
                if order_type != 'venta':
                    # For regalia/perdida, we auto-close it as 'pagado' so it shows in reports
                    # We also prepend the type to the customer name for clarity
                    customer_name = f"[{order_type.upper()}] {customer_name}"
                    
                new_order = Order(
                    customer_name=customer_name,
                    status="pagado" if order_type != 'venta' else "pendiente",
                    order_type=order_type,
                    waiter_id=current_user.id,
                    table_id=None,
                    closed_at=datetime.now() if order_type != 'venta' else None
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
                        
                        actual_units = quantity
                        
                        # Valuation logic: use cost if it's not a standard sale
                        if order_type != 'venta':
                            # Use cost_per_unit_usd, fallback to a small default or half of price if 0
                            cost = product.cost_per_unit_usd or (product.price_unit_usd * 0.5) if product.price_unit_usd else 0.5
                            base_price = cost
                        else:
                            base_price = prices.get(exit_type, product.price_unit_usd or product.price_usd) or 0.0
                            
                        mult = unit_multiplier.get(exit_type, 1) if exit_type != 'individual' else 1
                        subtotal = (quantity / mult) * base_price if mult > 0 else quantity * base_price
                        
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
                            exit_type=order_type if order_type != 'venta' else exit_type,
                            notes=f'{order_type.capitalize()} (Orden #{new_order.id})',
                            is_locked=True
                        ))

            if total_cervezas > 0:
                # Distribuir el subtotal de cervezas entre los detalles individuales
                beer_details = OrderDetail.query.filter_by(order_id=new_order.id, exit_type='individual').order_by(OrderDetail.id).all()
                prev_count = 0
                for detail in beer_details:
                    qty = detail.quantity
                    # Subtotal incremental para este bloque de cervezas
                    sub = calculate_beer_price(prev_count + qty, cerveza_ref) - calculate_beer_price(prev_count, cerveza_ref)
                    try:
                        detail.subtotal = float(sub)
                    except Exception:
                        detail.subtotal = 0.0
                    db.session.add(detail)
                    total += detail.subtotal
                    prev_count += qty

                # Registrar movimiento de salida total para cervezas
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
    if order.status not in ["pendiente", "parcial"]:
        return redirect(url_for('sales.sales_reports'))
    
    # Calculate remaining balance
    if order.total_paid_usd == 0 and order.payments:
        order.total_paid_usd = sum(p.amount for p in order.payments)
        order.total_paid_bs = sum(p.amount * (p.exchange_rate or 0) for p in order.payments)
        db.session.commit()
        
    remaining_balance = order.total_price - (order.total_paid_usd or 0.0)
    
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
                         remaining_balance=remaining_balance,
                         is_bar_order=True, 
                         current_rate=get_current_rate())

@sales_bp.route('/add_product_to_bar_order/<int:order_id>', methods=['POST'])
@login_required
def add_product_to_bar_order(order_id):
    """Add a product to an existing bar order."""
    order = Order.query.get_or_404(order_id)
    if order.status not in ["pendiente", "parcial"]:
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
@login_required
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
@manager_or_admin_required
def sales_reports():
    """View sales history and reports."""
    from models import Payment
    completed_orders = Order.query.filter_by(status="pagado").order_by(Order.closed_at.desc()).all()
    closures = DailyClosure.query.order_by(DailyClosure.date.desc()).all()
    
    # Calculate actual money entered but not yet closed (from all payments)
    pending_total_sales = db.session.query(db.func.sum(Payment.amount)).filter(Payment.closure_id == None).scalar() or 0.0
    
    # Get 50 most recent payments for the "What has really entered" view
    recent_payments = Payment.query.order_by(Payment.payment_date.desc()).limit(50).all()
    
    # Get recent adjustments (regalías/pérdidas) not yet closed
    pending_adjustments = InventoryMovement.query.filter(
        InventoryMovement.exit_type.in_(['regalia', 'perdida']),
        InventoryMovement.closure_id == None
    ).all()
    
    return render_template('sales/sales_reports.html', 
                         orders=completed_orders,
                         recent_payments=recent_payments,
                         closures=closures,
                         pending_total_sales=pending_total_sales,
                         pending_adjustments=pending_adjustments,
                         current_rate=get_current_rate())

@sales_bp.route('/daily_closure', methods=['GET', 'POST'])
@admin_required
def daily_closure():
    """Perform end-of-day closure."""
    from models import Payment
    from datetime import datetime
    
    # Get all payments that haven't been closed yet
    # This is more robust than date-based filtering
    today_payments = db.session.query(Payment).filter(
        Payment.closure_id == None
    ).all()
    
    # Calculate totals from these payments
    total_usd = sum(p.amount for p in today_payments)
    total_bs = sum(p.amount * (p.exchange_rate or 0) for p in today_payments)
    
    # Get orders involved:
    # 1. Orders with payments in this closure
    # 2. Orders marked as 'pagado' but not yet in a closure
    payment_order_ids = [p.order_id for p in today_payments]
    involved_orders = Order.query.filter(
        (Order.id.in_(payment_order_ids)) | 
        ((Order.status == 'pagado') & (Order.closure_id == None))
    ).all()
    
    # Pendientes de inventario
    pending_movements = InventoryMovement.query.filter(
        InventoryMovement.exit_type.in_(['regalia', 'perdida']),
        InventoryMovement.closure_id == None
    ).all()
    
    if request.method == 'POST':
        try:
            # Count distinct orders for the record
            distinct_orders_count = len(involved_orders)
            
            closure = DailyClosure(
                total_usd=total_usd,
                total_bs=total_bs,
                orders_count=distinct_orders_count,
                observations=request.form.get('observations', ''),
                closed_by=current_user.id,
                date=datetime.now()
            )
            db.session.add(closure)
            db.session.flush()
            
            # 1. Assign closure to all payments included
            for p in today_payments:
                p.closure_id = closure.id
            
            # 2. Assign closure to orders that are FULLY paid
            # (Partial orders stay with closure_id=None so they can appear in future closures when more payments are made)
            for o in involved_orders:
                if o.status == 'pagado':
                    o.closure_id = closure.id
            
            # 3. Assign closure to inventory movements
            for m in pending_movements:
                m.closure_id = closure.id
                
            db.session.commit()
            flash('Cierre realizado exitosamente', 'success')
            return redirect(url_for('sales.sales_reports'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')

    # Calculate method breakdown and per-order contributions
    method_totals = {}
    order_contributions = {}
    
    for o in involved_orders:
        o_payments = [p for p in today_payments if p.order_id == o.id]
        total_p_today = sum(p.amount for p in o_payments)
        
        # Check if there were ANY payments for this order in PAST closures
        has_previous_payments = Payment.query.filter(
            Payment.order_id == o.id, 
            Payment.closure_id != None
        ).first() is not None
        
        # An order is 'abono' if it's currently partial OR if it was completed via multiple installments
        # (if it has previous payments, today's entry is an installment/abono)
        is_abono = (o.status == 'parcial') or has_previous_payments or (len(o_payments) > 1)
        
        order_contributions[o.id] = {
            'today_amount': total_p_today,
            'abono_amount': total_p_today if is_abono else 0.0
        }

    for p in today_payments:
        method_name = p.method.name if p.method else "Sin método"
        if method_name not in method_totals:
            method_totals[method_name] = {
                'usd': 0.0,
                'bs': 0.0,
                'currency': p.method.currency.upper() if p.method else 'USD'
            }
        
        method_totals[method_name]['usd'] += p.amount
        method_totals[method_name]['bs'] += p.amount * (p.exchange_rate or 0)
            
    return render_template('sales/daily_closure.html', 
                         orders=involved_orders,
                         payments=today_payments,
                         order_contributions=order_contributions,
                         total_usd=total_usd, 
                         total_bs=total_bs,
                         method_totals=method_totals,
                         adjustments=pending_movements)

@sales_bp.route('/bar_orders')
@login_required
def bar_orders():
    """View pending bar orders."""
    orders = Order.query.filter(
        Order.table_id == None,
        Order.status.in_(['pendiente', 'parcial'])
    ).all()
    return render_template('sales/bar_orders.html', orders=orders, current_rate=get_current_rate())

@sales_bp.route('/order/<int:order_id>/pay', methods=['POST'])
@login_required
def pay_order(order_id):
    """Handle payment for an order (full or installment)."""
    from models import Payment
    from exchange import get_current_rate
    
    order = Order.query.get_or_404(order_id)
    payment_type = request.form.get('payment_type')
    payment_currency = request.form.get('payment_currency', 'usd')
    notes = request.form.get('notes', '')
    
    # Extract payment method and amount based on currency
    if payment_currency == 'usd':
        payment_method_id = int(request.form.get('payment_method_usd'))
        payment_amount = float(request.form.get('payment_amount_usd', 0))
    else:
        payment_method_id = int(request.form.get('payment_method_bs'))
        payment_amount = float(request.form.get('payment_amount_bs', 0))
    
    current_rate = get_current_rate()
    
    # Convert payment to both currencies
    if payment_currency == 'usd':
        amount_usd = payment_amount
        amount_bs = payment_amount * current_rate
    else:
        amount_usd = payment_amount / current_rate
        amount_bs = payment_amount
    
    # Calculate remaining balance
    remaining_usd = order.total_price - (order.total_paid_usd or 0.0)
    
    if payment_type == 'contado':
        # Full payment - must cover remaining balance
        if amount_usd < remaining_usd - 0.01:  # 0.01 tolerance for rounding
            flash(f'Pago insuficiente. Debe: ${remaining_usd:.2f}, Pagó: ${amount_usd:.2f}', 'danger')
            if order.table_id:
                return redirect(url_for('sales.view_order', table_id=order.table_id))
            else:
                return redirect(url_for('sales.view_bar_order', order_id=order.id))
        
        # Create payment record
        payment = Payment(
            order_id=order.id,
            amount=amount_usd,
            payment_method=payment_method_id,
            exchange_rate=current_rate,
            registered_by=current_user.id,
            notes=notes or 'Pago completo'
        )
        
        order.total_paid_usd = (order.total_paid_usd or 0.0) + amount_usd
        order.total_paid_bs = (order.total_paid_bs or 0.0) + amount_bs
        order.status = 'pagado'
        order.closed_at = datetime.now()
        
        # Update legacy fields for backward compatibility
        order.payment_currency = payment_currency
        order.payment_amount_usd = amount_usd
        order.payment_amount_bs = amount_bs
        order.payment_method_id = payment_method_id
        order.exchange_rate = current_rate
        
        db.session.add(payment)
        flash(f'Pago completo registrado: ${amount_usd:.2f}', 'success')
        
    elif payment_type == 'abono':
        # Partial payment
        if amount_usd > remaining_usd:
            flash(f'El abono (${amount_usd:.2f}) excede la deuda (${remaining_usd:.2f})', 'warning')
            amount_usd = remaining_usd
            amount_bs = remaining_usd * current_rate
        
        # Create payment record
        payment = Payment(
            order_id=order.id,
            amount=amount_usd,
            payment_method=payment_method_id,
            exchange_rate=current_rate,
            registered_by=current_user.id,
            notes=notes or f'Abono #{len(order.payments) + 1}'
        )
        
        order.total_paid_usd = (order.total_paid_usd or 0.0) + amount_usd
        order.total_paid_bs = (order.total_paid_bs or 0.0) + amount_bs
        
        # Check if fully paid after this installment
        new_remaining = order.total_price - order.total_paid_usd
        if new_remaining <= 0.01:  # Fully paid
            order.status = 'pagado'
            order.closed_at = datetime.now()
            
            # Update legacy fields for closure report compatibility
            order.payment_currency = payment_currency
            order.payment_amount_usd = order.total_paid_usd
            order.payment_amount_bs = order.total_paid_bs
            order.payment_method_id = payment_method_id
            order.exchange_rate = current_rate
            
            flash(f'¡Orden completamente pagada! Último abono: ${amount_usd:.2f}', 'success')
        else:
            order.status = 'parcial'
            flash(f'Abono registrado: ${amount_usd:.2f}. Resta: ${new_remaining:.2f}', 'success')
        
        db.session.add(payment)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Error al registrar el pago: {str(e)}', 'danger')

    # Redirect based on order type
    if order.table_id:
        return redirect(url_for('sales.view_order', table_id=order.table_id))
    else:
        return redirect(url_for('sales.view_bar_order', order_id=order.id))
