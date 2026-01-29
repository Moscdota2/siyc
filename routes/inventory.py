from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from py_exchange import db, get_current_rate
from py_models import Product, InventoryMovement
from decorators import admin_required, manager_or_admin_required

inventory_bp = Blueprint('inventory', __name__)

@inventory_bp.route('/inventory')
@login_required
def inventory():
    """Display real-time inventory."""
    products = Product.query.all()
    low_stock = Product.query.filter(Product.quantity < 10).count()
    return render_template('inventory/inventory.html', products=products, low_stock=low_stock)

@inventory_bp.route('/create_product', methods=['GET', 'POST'])
@admin_required
def create_product():
    """Handle new product creation."""
    if request.method == 'POST':
        try:
            current_rate = get_current_rate()
            new_product = Product(
                name=request.form['name'],
                brand=request.form['brand'],
                category=request.form['category'],
                presentation=request.form['presentation'],
                quantity=int(request.form['quantity']),
                price_usd=float(request.form['price_usd']),
                price_bs=float(request.form['price_usd']) * current_rate,
                price_unit_usd=float(request.form['price_usd']),
                price_unit_bs=float(request.form['price_usd']) * current_rate,
                last_modified_by=current_user.id
            )
            db.session.add(new_product)
            db.session.flush()

            initial_quantity = int(request.form['quantity'])
            purchase_price = float(request.form.get('purchase_price', 0))
            
            creation_movement = InventoryMovement(
                product_id=new_product.id,
                user_id=current_user.id,
                movement_type='entrada',
                quantity=initial_quantity,
                notes=f"Creación de producto: {new_product.name}",
                currency='usd',
                distributor='sistema',
                purchase_price=purchase_price,
                total_usd_investment=purchase_price
            )
            db.session.add(creation_movement)
            
            db.session.commit()
            flash('Producto creado con registro histórico', 'success')
            return redirect(url_for('inventory.inventory'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
    return render_template('inventory/create_product.html')

@inventory_bp.route('/update_product/<int:id>', methods=['GET', 'POST'])
@admin_required
def update_product(id):
    """Handle product updates."""
    product = Product.query.get_or_404(id)
    if request.method == 'POST':
        try:
            current_rate = get_current_rate()
            product.name = request.form['name']
            product.brand = request.form['brand']
            product.category = request.form['category']
            product.presentation = request.form['presentation']
            product.quantity = int(request.form['quantity'])
            product.price_usd = float(request.form['price_usd'])
            product.price_bs = float(request.form['price_usd']) * current_rate
            product.price_unit_usd = float(request.form['price_usd'])
            product.price_unit_bs = float(request.form['price_usd']) * current_rate
            product.last_modified_by = current_user.id
            db.session.commit()
            flash('Producto actualizado exitosamente', 'success')
            return redirect(url_for('inventory.inventory'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar producto: {str(e)}', 'danger')
    return render_template('inventory/update_product.html', product=product)

@inventory_bp.route('/delete_product/<int:id>')
@admin_required
def delete_product(id):
    """Reset product quantities (do NOT remove the product record).

    This is safer for 'reset' operations from the UI: remove historical
    inventory movements for the product and set `quantity` and
    `box_quantity` to zero, keeping the product metadata intact.
    """
    product = Product.query.get_or_404(id)
    try:
        # Remove movement history but preserve product entry
        InventoryMovement.query.filter_by(product_id=id).delete()
        product.quantity = 0
        product.box_quantity = 0
        db.session.commit()
        flash('Producto reseteado: cantidades puestas a 0 y movimientos eliminados', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al resetear producto: {str(e)}', 'danger')
    return redirect(url_for('inventory.inventory'))

@inventory_bp.route('/inventory_entry', methods=['GET', 'POST'])
@manager_or_admin_required
def inventory_entry():
    """Handle stock entries."""
    if request.method == 'POST':
        product_id = request.form['product_id']
        boxes = float(request.form['boxes'])
        product_type = request.form.get('product_type', '')
        currency = request.form['currency']
        purchase_price = float(request.form['purchase_price'])
        distributor = request.form.get('distributor', '')
        
        product = Product.query.get_or_404(product_id)
        
        if product_type == 'cerveza':
            units_per_box = 36
        else:
            units_per_box = 1

        units = int(boxes * units_per_box)
        total_usd_investment = 0.0

        # If the user provided an explicit purchase_price, prefer it (convert from BS if needed)
        if purchase_price and purchase_price > 0:
            if currency == 'bs':
                current_rate = get_current_rate()
                if current_rate <= 0:
                    flash("Error: Tasa de cambio no disponible o es cero.", "danger")
                    return redirect(url_for('inventory.inventory_entry'))
                # purchase_price is expressed in BS; convert entire total to USD
                total_usd_investment = purchase_price / current_rate
            else:
                # purchase_price already in USD (treated as total for the whole entry)
                total_usd_investment = purchase_price
        else:
            # Fallback: use configured per-box / per-unit defaults
            if currency == 'bs':
                current_rate = get_current_rate()
                if current_rate > 0:
                    if product_type == 'cerveza':
                        usd_price_per_box = 20.80 if distributor == 'polar' else 19.50
                        total_usd_investment = boxes * usd_price_per_box
                    else:
                        usd_price_per_unit = purchase_price / (units * current_rate) if units > 0 else 0
                        total_usd_investment = usd_price_per_unit * units
                else:
                    flash("Error: Tasa de cambio no disponible o es cero.", "danger")
                    return redirect(url_for('inventory.inventory_entry'))
            else:
                if product_type == 'cerveza':
                    usd_price_per_box = 17.00 if distributor == 'polar' else 19.00
                    total_usd_investment = boxes * usd_price_per_box
                else:
                    usd_price_per_unit = purchase_price / units if units > 0 else 0
                    total_usd_investment = usd_price_per_unit * units
        
        product.quantity += units
        if product_type == 'cerveza':
            product.box_quantity += boxes
        
        movement = InventoryMovement(
            product_id=product.id,
            user_id=current_user.id,
            movement_type='entrada',
            quantity=units,
            boxes=boxes if product_type == 'cerveza' else None,
            units_per_box=units_per_box,
            currency=currency,
            purchase_price=purchase_price,
            distributor=distributor if product_type == 'cerveza' else 'sistema',
            notes=f"Entrada de {boxes} {'cajas' if product_type == 'cerveza' else 'unidades'} de {product.name}",
            total_usd_investment=total_usd_investment
        )
        
        try:
            db.session.add(movement)
            db.session.commit()
            flash(f"✅ {units} unidades agregadas | Inversión: ${total_usd_investment:.2f}", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Error al registrar: {str(e)}", 'danger')
        
        return redirect(url_for('inventory.inventory_entry'))
    
    products = Product.query.filter(Product.category.in_(['Cerveza', 'Ron', 'Anís', 'Whisky', 'Misceláneo'])).all()
    return render_template("inventory/inventory_entry.html", products=products, precio_bcv=get_current_rate())

@inventory_bp.route('/inventory_history')
@manager_or_admin_required
def inventory_history():
    """Display paginated movement history."""
    page = request.args.get('page', 1, type=int)
    movements_pagination = db.session.query(InventoryMovement, Product)\
        .join(Product, InventoryMovement.product_id == Product.id)\
        .options(db.contains_eager(InventoryMovement.product))\
        .order_by(InventoryMovement.movement_date.desc())\
        .paginate(page=page, per_page=20, error_out=False)
    
    return render_template('inventory/inventory_history.html', movements_pagination=movements_pagination)

@inventory_bp.route('/edit_movement/<int:movement_id>', methods=['GET', 'POST'])
@admin_required
def edit_movement(movement_id):
    """Adjust a previous inventory movement."""
    movement = InventoryMovement.query.get_or_404(movement_id)
    if request.method == 'POST':
        original_qty = movement.quantity
        new_qty = int(request.form['quantity'])
        product = movement.product
        product.quantity += (original_qty - new_qty)
        movement.quantity = new_qty
        movement.notes = f"Ajustado por {current_user.username}. Original: {original_qty}, Nuevo: {new_qty}"
        movement.is_locked = True
        movement.locked_by_admin = True
        try:
            db.session.commit()
            flash('Movimiento actualizado', 'success')
            return redirect(url_for('inventory.inventory_history'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar: {str(e)}', 'danger')
    return render_template('edit_movement.html', movement=movement)

@inventory_bp.route('/register_adjustment', methods=['GET', 'POST'])
@login_required
def register_adjustment():
    """Register losses (pérdidas) or giveaways (regalías)."""
    if request.method == 'POST':
        try:
            product_id = request.form['product_id']
            quantity = int(request.form['quantity'])
            adj_type = request.form['adj_type'] # 'regalia' or 'perdida'
            notes = request.form.get('notes', '')
            
            product = Product.query.get_or_404(product_id)
            
            if product.quantity < quantity:
                flash(f'Stock insuficiente. Disponible: {product.quantity}', 'danger')
                return redirect(url_for('inventory.register_adjustment'))
            
            product.quantity -= quantity
            
            movement = InventoryMovement(
                product_id=product_id,
                user_id=current_user.id,
                movement_type='salida',
                quantity=quantity,
                exit_type=adj_type,
                notes=f"{adj_type.capitalize()}: {notes} (por {current_user.username})",
                is_locked=True
            )
            
            db.session.add(movement)
            db.session.commit()
            flash(f'Ajuste registrado ({adj_type}): {quantity} unidades de {product.name}', 'success')
            return redirect(url_for('inventory.inventory'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar ajuste: {str(e)}', 'danger')
            
    products = Product.query.filter(Product.quantity > 0).all()
    return render_template('inventory/register_adjustment.html', products=products)
