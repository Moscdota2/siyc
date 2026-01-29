from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from py_models import User, Order, OrderDetail, InventoryMovement, Product, DailyClosure, Table
from py_exchange import db
from decorators import admin_required

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('sales.index'))
        flash('Usuario o contraseña incorrectos', 'danger')
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Handle user logout."""
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/admin/database', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_db():
    """Administrative database cleanup tools."""
    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            if action == 'clear_sales':
                # Clear all orders and details
                OrderDetail.query.delete()
                Order.query.delete()
                # Reset table status
                Table.query.update({Table.status: "disponible"})
                flash('Historial de ventas y mesas reiniciado', 'success')
                
            elif action == 'clear_history':
                # Clear inventory movements (except locked ones?)
                InventoryMovement.query.delete()
                flash('Historial de movimientos de inventario eliminado', 'success')
                
            elif action == 'clear_closures':
                # Clear daily closures
                DailyClosure.query.delete()
                # Unlink closures from orders and movements
                Order.query.update({Order.closure_id: None})
                InventoryMovement.query.update({InventoryMovement.closure_id: None})
                flash('Historial de cierres de caja eliminado', 'success')
                
            elif action == 'clear_all':
                # Nuclear option
                OrderDetail.query.delete()
                Order.query.delete()
                InventoryMovement.query.delete()
                DailyClosure.query.delete()
                Table.query.update({Table.status: "disponible"})
                flash('Bases de datos de transacciones reiniciadas completamente', 'warning')
                
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'Error al limpiar base de datos: {str(e)}', 'danger')
            
    return render_template('auth/admin_db.html')
