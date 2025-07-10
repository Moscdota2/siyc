from flask import Flask, render_template, request, redirect, url_for, flash
from py_models import db, Product, Order, OrderDetail, Table  # Importamos db y el modelo Product desde models.py

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pharmacy.db'
app.config['SECRET_KEY'] = 'mysecretkey'

# Inicializamos SQLAlchemy con la aplicación Flask
db.init_app(app)

# Crear la base de datos
with app.app_context():
    db.create_all()

# Ruta principal para listar todos los productos
@app.route('/')
def index():
    products = Product.query.all()
    return render_template('index.html', products=products)

# Ruta para crear un nuevo producto
@app.route('/create_product', methods=['GET', 'POST'])
def create_product():
    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        quantity = request.form['quantity']
        price_usd = request.form['price_usd']
        price_bs = request.form['price_bs']

        new_product = Product(name=name, category=category, quantity=quantity, price_usd=price_usd, price_bs=price_bs)

        try:
            db.session.add(new_product)
            db.session.commit()
            flash('Producto agregado correctamente')
            return redirect('/')
        except:
            flash('Error al agregar el producto')
            return 'Hubo un problema al agregar el producto.'

    return render_template('create_product.html')

# Ruta para actualizar un producto
@app.route('/update_product/<int:id>', methods=['GET', 'POST'])
def update_product(id):
    product = Product.query.get_or_404(id)

    if request.method == 'POST':
        product.name = request.form['name']
        product.category = request.form['category']
        product.quantity = request.form['quantity']
        product.price_usd = request.form['price_usd']
        product.price_bs = request.form['price_bs']

        try:
            db.session.commit()
            flash('Producto actualizado correctamente')
            return redirect('/')
        except:
            flash('Error al actualizar el producto')
            return 'Hubo un problema al actualizar el producto.'

    return render_template('update.html', product=product)

# Ruta para eliminar un producto
@app.route('/delete_product/<int:id>')
def delete_product(id):
    product = Product.query.get_or_404(id)

    try:
        db.session.delete(product)
        db.session.commit()
        flash('Producto eliminado correctamente')
        return redirect('/')
    except:
        flash('Error al eliminar el producto')
        return 'Hubo un problema al eliminar el producto.'
    

# Ruta para ver todas las mesas
@app.route('/tables')
def view_tables():
    tables = Table.query.all()
    return render_template('tables.html', tables=tables)

# Ruta para crear un pedido en una mesa
@app.route('/create_order/<int:table_id>')
def create_order(table_id):
    table = Table.query.get_or_404(table_id)

    if table.status != "disponible":
        flash("La mesa ya tiene un pedido activo.")
        return redirect(url_for('view_tables'))

    new_order = Order(table_id=table_id, status="pendiente")
    table.status = "ocupada"

    db.session.add(new_order)
    db.session.commit()

    flash(f"Pedido creado para la Mesa {table_id}")
    return redirect(url_for('view_order', order_id=new_order.id))

# Ruta para ver un pedido
@app.route('/order/<int:order_id>')
def view_order(order_id):
    order = Order.query.get_or_404(order_id)
    order_details = OrderDetail.query.filter_by(order_id=order.id).all()
    products = Product.query.all()
    return render_template('order.html', order=order, order_details=order_details, products=products)

# Ruta para agregar un producto a un pedido
@app.route('/add_product/<int:order_id>', methods=['POST'])
def add_product(order_id):
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])

    order = Order.query.get_or_404(order_id)
    product = Product.query.get_or_404(product_id)

    if product.quantity < quantity:
        flash(f"No hay suficiente stock de {product.name}.")
        return redirect(url_for('view_order', order_id=order_id))

    subtotal = product.price_usd * quantity
    order.total_price += subtotal
    product.quantity -= quantity

    order_detail = OrderDetail(order_id=order_id, product_id=product_id, quantity=quantity, subtotal=subtotal)
    
    db.session.add(order_detail)
    db.session.commit()

    flash(f"{quantity}x {product.name} agregado al pedido.")
    return redirect(url_for('view_order', order_id=order_id))

# Ruta para cerrar un pedido
@app.route('/close_order/<int:order_id>')
def close_order(order_id):
    order = Order.query.get_or_404(order_id)
    table = Table.query.get(order.table_id)

    order.status = "pagado"
    table.status = "disponible"

    db.session.commit()
    flash(f"Pedido {order.id} pagado y mesa {table.id} disponible.")
    return redirect(url_for('view_tables'))

if __name__ == '__main__':
    app.run(debug=True)
