from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Configure SQLite database
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'food_ordering.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    orders = db.relationship('Order', backref='user', lazy=True)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    items = db.relationship('MenuItem', backref='category', lazy=True)

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    order_items = db.relationship('OrderItem', backref='menu_item', lazy=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    order_items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)

# Helper Functions
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Routes - Authentication
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password, method='sha256')
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful. Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not check_password_hash(user.password, password):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))
        
        session['user_id'] = user.id
        session['username'] = user.username
        session['is_admin'] = user.is_admin
        
        if user.is_admin:
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('customer_menu'))
    
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

# Routes - Customer
@app.route('/')
def index():
    return render_template('customer/menu.html', categories=Category.query.all())

@app.route('/menu')
@login_required
def customer_menu():
    categories = Category.query.all()
    return render_template('customer/menu.html', categories=categories)

@app.route('/add_to_cart/<int:item_id>', methods=['POST'])
@login_required
def add_to_cart(item_id):
    if 'cart' not in session:
        session['cart'] = []
    
    item = MenuItem.query.get_or_404(item_id)
    cart = session['cart']
    
    # Check if item already in cart
    for cart_item in cart:
        if cart_item['id'] == item.id:
            cart_item['quantity'] += 1
            session.modified = True
            flash(f'Added another {item.name} to your cart', 'success')
            return redirect(url_for('customer_menu'))
    
    # Add new item to cart
    cart.append({
        'id': item.id,
        'name': item.name,
        'price': item.price,
        'quantity': 1,
        'image': item.image
    })
    session.modified = True
    flash(f'Added {item.name} to your cart', 'success')
    return redirect(url_for('customer_menu'))

@app.route('/cart')
@login_required
def view_cart():
    cart = session.get('cart', [])
    total = sum(item['price'] * item['quantity'] for item in cart)
    return render_template('customer/cart.html', cart=cart, total=total)

@app.route('/update_cart/<int:index>', methods=['POST'])
@login_required
def update_cart(index):
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        action = request.form.get('action')
        
        if action == 'increase':
            cart[index]['quantity'] += 1
        elif action == 'decrease':
            cart[index]['quantity'] -= 1
            if cart[index]['quantity'] <= 0:
                del cart[index]
        elif action == 'remove':
            del cart[index]
        
        session.modified = True
        flash('Cart updated', 'success')
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    cart = session.get('cart', [])
    if not cart:
        flash('Your cart is empty', 'warning')
        return redirect(url_for('customer_menu'))
    
    total = sum(item['price'] * item['quantity'] for item in cart)
    order = Order(user_id=session['user_id'], total=total)
    db.session.add(order)
    db.session.commit()
    
    for item in cart:
        order_item = OrderItem(
            order_id=order.id,
            menu_item_id=item['id'],
            quantity=item['quantity'],
            price=item['price']
        )
        db.session.add(order_item)
    
    db.session.commit()
    session.pop('cart', None)
    flash('Order placed successfully!', 'success')
    return redirect(url_for('order_confirmation', order_id=order.id))

@app.route('/order_confirmation/<int:order_id>')
@login_required
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != session['user_id']:
        flash('You are not authorized to view this order', 'danger')
        return redirect(url_for('customer_menu'))
    
    return render_template('customer/order_confirmation.html', order=order)

@app.route('/my_orders')
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=session['user_id']).order_by(Order.created_at.desc()).all()
    return render_template('customer/orders.html', orders=orders)

# Routes - Admin
@app.route('/admin')
@admin_required
def admin_dashboard():
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='Pending').count()
    completed_orders = Order.query.filter_by(status='Completed').count()
    total_users = User.query.count()
    
    return render_template('admin/dashboard.html', 
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         completed_orders=completed_orders,
                         total_users=total_users)

@app.route('/admin/menu')
@admin_required
def admin_menu():
    categories = Category.query.all()
    items = MenuItem.query.all()
    return render_template('admin/menu.html', categories=categories, items=items)

@app.route('/admin/add_category', methods=['POST'])
@admin_required
def add_category():
    name = request.form.get('name')
    if not name:
        flash('Category name is required', 'danger')
        return redirect(url_for('admin_menu'))
    
    if Category.query.filter_by(name=name).first():
        flash('Category already exists', 'danger')
        return redirect(url_for('admin_menu'))
    
    new_category = Category(name=name)
    db.session.add(new_category)
    db.session.commit()
    flash('Category added successfully', 'success')
    return redirect(url_for('admin_menu'))

@app.route('/admin/add_item', methods=['POST'])
@admin_required
def add_item():
    name = request.form.get('name')
    description = request.form.get('description')
    price = float(request.form.get('price'))
    category_id = int(request.form.get('category_id'))
    
    if not name or not price or not category_id:
        flash('Name, price and category are required', 'danger')
        return redirect(url_for('admin_menu'))
    
    new_item = MenuItem(
        name=name,
        description=description,
        price=price,
        category_id=category_id,
        image='default.jpg'  # In a real app, you'd handle file uploads
    )
    db.session.add(new_item)
    db.session.commit()
    flash('Menu item added successfully', 'success')
    return redirect(url_for('admin_menu'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    status_filter = request.args.get('status', 'all')
    
    if status_filter == 'pending':
        orders = Order.query.filter_by(status='Pending').order_by(Order.created_at.desc()).all()
    elif status_filter == 'completed':
        orders = Order.query.filter_by(status='Completed').order_by(Order.created_at.desc()).all()
    else:
        orders = Order.query.order_by(Order.created_at.desc()).all()
    
    return render_template('admin/orders.html', orders=orders, status_filter=status_filter)

@app.route('/admin/update_order_status/<int:order_id>', methods=['POST'])
@admin_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    
    if new_status in ['Pending', 'Completed', 'Cancelled']:
        order.status = new_status
        db.session.commit()
        flash('Order status updated', 'success')
    else:
        flash('Invalid status', 'danger')
    
    return redirect(url_for('admin_orders'))

@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/make_admin/<int:user_id>')
@admin_required
def make_admin(user_id):
    user = User.query.get_or_404(user_id)
    user.is_admin = True
    db.session.commit()
    flash(f'{user.username} is now an admin', 'success')
    return redirect(url_for('admin_users'))

# Initialize Database
@app.before_first_request
def create_tables():
    db.create_all()
    # Create admin user if not exists
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            email='admin@example.com',
            password=generate_password_hash('admin123', method='sha256'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
