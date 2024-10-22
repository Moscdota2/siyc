from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, Product  # Importamos db y el modelo Product desde models.py

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

    return render_template('update_product.html', product=product)

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

if __name__ == '__main__':
    app.run(debug=True)
