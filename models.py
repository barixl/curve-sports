# models.py — import db/login_manager from extensions, NOT from app.py
from extensions import db, login_manager
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    password   = db.Column(db.String(256), nullable=False)
    phone      = db.Column(db.String(20))
    is_admin   = db.Column(db.Boolean, default=False)
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    orders     = db.relationship('Order',    backref='user', lazy=True)
    addresses  = db.relationship('Address',  backref='user', lazy=True)
    wishlist   = db.relationship('Wishlist', backref='user', lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)


class Category(db.Model):
    __tablename__ = 'categories'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    slug        = db.Column(db.String(120), unique=True, nullable=False)
    icon        = db.Column(db.String(10), default='📦')
    description = db.Column(db.Text)
    image       = db.Column(db.String(200))
    is_active   = db.Column(db.Boolean, default=True)
    products    = db.relationship('Product', backref='category', lazy=True)

    def product_count(self):
        return len([p for p in self.products if p.is_active])


class Brand(db.Model):
    __tablename__ = 'brands'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    slug        = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text)
    logo        = db.Column(db.String(200))
    is_active   = db.Column(db.Boolean, default=True)
    products    = db.relationship('Product', backref='brand', lazy=True)


class Product(db.Model):
    __tablename__ = 'products'
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(200), nullable=False)
    slug         = db.Column(db.String(220), unique=True, nullable=False)
    description  = db.Column(db.Text)
    price        = db.Column(db.Float, nullable=False)
    original_price = db.Column(db.Float)
    stock        = db.Column(db.Integer, default=0)
    image        = db.Column(db.String(200))
    flavor       = db.Column(db.String(100))
    weight       = db.Column(db.String(50))
    rating       = db.Column(db.Float, default=0.0)
    review_count = db.Column(db.Integer, default=0)
    featured     = db.Column(db.Boolean, default=False)
    bestseller   = db.Column(db.Boolean, default=False)
    is_active    = db.Column(db.Boolean, default=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    category_id  = db.Column(db.Integer, db.ForeignKey('categories.id'))
    brand_id     = db.Column(db.Integer, db.ForeignKey('brands.id'))
    order_items  = db.relationship('OrderItem', backref='product', lazy=True)
    reviews      = db.relationship('Review',    backref='product', lazy=True)

    def discount_percent(self):
        if self.original_price and self.original_price > self.price:
            return int(((self.original_price - self.price) / self.original_price) * 100)
        return 0

    def in_stock(self):
        return self.stock > 0


class Address(db.Model):
    __tablename__ = 'addresses'
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    full_name    = db.Column(db.String(100), nullable=False)
    phone        = db.Column(db.String(20),  nullable=False)
    address_line1 = db.Column(db.String(200), nullable=False)
    address_line2 = db.Column(db.String(200))
    city         = db.Column(db.String(100), nullable=False)
    state        = db.Column(db.String(100), nullable=False)
    pincode      = db.Column(db.String(10),  nullable=False)
    is_default   = db.Column(db.Boolean, default=False)


class Order(db.Model):
    __tablename__ = 'orders'
    id              = db.Column(db.Integer, primary_key=True)
    order_number    = db.Column(db.String(20), unique=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    total_amount    = db.Column(db.Float, nullable=False)
    discount_amount = db.Column(db.Float, default=0)
    delivery_charge = db.Column(db.Float, default=0)
    final_amount    = db.Column(db.Float, nullable=False)
    status          = db.Column(db.String(50), default='Pending')
    payment_method  = db.Column(db.String(50), default='COD')
    payment_status  = db.Column(db.String(50), default='Pending')
    coupon_code     = db.Column(db.String(50))
    address_id      = db.Column(db.Integer, db.ForeignKey('addresses.id'))
    address_snapshot = db.Column(db.Text)
    notes           = db.Column(db.Text)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    items           = db.relationship('OrderItem', backref='order', lazy=True)

    STATUS_CHOICES = ['Pending', 'Confirmed', 'Processing', 'Shipped', 'Delivered', 'Cancelled', 'Refunded']

    def generate_order_number(self):
        import random, string
        self.order_number = 'NB' + ''.join(random.choices(string.digits, k=8))


class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey('orders.id'),   nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity   = db.Column(db.Integer, nullable=False)
    price      = db.Column(db.Float,   nullable=False)
    total      = db.Column(db.Float,   nullable=False)


class Coupon(db.Model):
    __tablename__ = 'coupons'
    id                = db.Column(db.Integer, primary_key=True)
    code              = db.Column(db.String(50), unique=True, nullable=False)
    discount_type     = db.Column(db.String(20), default='percent')   # 'percent' | 'flat'
    discount_value    = db.Column(db.Float, nullable=False)
    min_order_amount  = db.Column(db.Float, default=0)
    max_discount      = db.Column(db.Float)
    usage_limit       = db.Column(db.Integer)
    used_count        = db.Column(db.Integer, default=0)
    is_active         = db.Column(db.Boolean, default=True)
    expires_at        = db.Column(db.DateTime)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)

    def is_valid(self, order_amount=0):
        if not self.is_active:
            return False, 'Coupon is inactive'
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False, 'Coupon has expired'
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False, 'Coupon usage limit reached'
        if order_amount < self.min_order_amount:
            return False, f'Minimum order amount is ₹{self.min_order_amount:.0f}'
        return True, 'Valid'

    def calculate_discount(self, amount):
        if self.discount_type == 'percent':
            discount = (amount * self.discount_value) / 100
            if self.max_discount:
                discount = min(discount, self.max_discount)
        else:
            discount = min(self.discount_value, amount)
        return round(discount, 2)


class Review(db.Model):
    __tablename__ = 'reviews'
    id         = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=False)
    rating     = db.Column(db.Integer, nullable=False)
    title      = db.Column(db.String(200))
    body       = db.Column(db.Text)
    is_verified = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)


class Wishlist(db.Model):
    __tablename__ = 'wishlist'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Banner(db.Model):
    __tablename__ = 'banners'
    id        = db.Column(db.Integer, primary_key=True)
    title     = db.Column(db.String(200))
    subtitle  = db.Column(db.String(300))
    image     = db.Column(db.String(200))
    link      = db.Column(db.String(300))
    position  = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    bg_color  = db.Column(db.String(20), default='#0a1628')
