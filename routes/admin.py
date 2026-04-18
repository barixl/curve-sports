from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from functools import wraps
from extensions import db
from models import (User, Product, Category, Brand, Order, OrderItem,
                    Coupon, Review, Banner)
from datetime import datetime, timedelta
from sqlalchemy import func
import os, uuid
from werkzeug.utils import secure_filename

admin_bp = Blueprint('admin', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return login_required(decorated)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(file, folder):
    from flask import current_app
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        fname = f"{uuid.uuid4().hex}.{ext}"
        path = os.path.join(current_app.static_folder, 'images', folder, fname)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file.save(path)
        return fname
    return None


# ─── DASHBOARD ───────────────────────────────────────────────────────────────

@admin_bp.route('/')
@admin_required
def dashboard():
    today = datetime.utcnow().date()
    week_ago = datetime.utcnow() - timedelta(days=7)
    month_ago = datetime.utcnow() - timedelta(days=30)

    total_orders = Order.query.count()
    total_revenue = db.session.query(func.sum(Order.final_amount)).scalar() or 0
    total_users = User.query.filter_by(is_admin=False).count()
    total_products = Product.query.filter_by(is_active=True).count()

    today_orders = Order.query.filter(func.date(Order.created_at) == today).count()
    today_revenue = db.session.query(func.sum(Order.final_amount)).filter(
        func.date(Order.created_at) == today).scalar() or 0

    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    low_stock = Product.query.filter(Product.stock < 20, Product.is_active == True).all()

    monthly_revenue = []
    for i in range(6):
        d = datetime.utcnow() - timedelta(days=30 * i)
        rev = db.session.query(func.sum(Order.final_amount)).filter(
            func.strftime('%Y-%m', Order.created_at) == d.strftime('%Y-%m')
        ).scalar() or 0
        monthly_revenue.append({'month': d.strftime('%b %Y'), 'revenue': float(rev)})
    monthly_revenue.reverse()

    order_status_counts = db.session.query(
        Order.status, func.count(Order.id)
    ).group_by(Order.status).all()

    top_products = db.session.query(
        Product.name, func.sum(OrderItem.quantity).label('sold')
    ).join(OrderItem).group_by(Product.id).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()

    return render_template('admin/dashboard.html',
                           total_orders=total_orders, total_revenue=total_revenue,
                           total_users=total_users, total_products=total_products,
                           today_orders=today_orders, today_revenue=today_revenue,
                           recent_orders=recent_orders, low_stock=low_stock,
                           monthly_revenue=monthly_revenue,
                           order_status_counts=order_status_counts,
                           top_products=top_products)


# ─── PRODUCTS ────────────────────────────────────────────────────────────────

@admin_bp.route('/products')
@admin_required
def products():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '')
    cat_id = request.args.get('category', type=int)
    query = Product.query
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    if cat_id:
        query = query.filter_by(category_id=cat_id)
    products = query.order_by(Product.created_at.desc()).paginate(page=page, per_page=20)
    categories = Category.query.all()
    return render_template('admin/products.html', products=products, categories=categories, search=search, cat_id=cat_id)


@admin_bp.route('/products/add', methods=['GET', 'POST'])
@admin_required
def add_product():
    categories = Category.query.filter_by(is_active=True).all()
    brands = Brand.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        img_file = request.files.get('image')
        img_name = save_image(img_file, 'products') if img_file and img_file.filename else None
        from slugify import slugify
        slug = slugify(request.form.get('name', ''))
        existing = Product.query.filter_by(slug=slug).first()
        if existing:
            slug = slug + '-' + uuid.uuid4().hex[:4]
        p = Product(
            name=request.form.get('name'),
            slug=slug,
            description=request.form.get('description'),
            price=float(request.form.get('price', 0)),
            original_price=float(request.form.get('original_price') or 0) or None,
            stock=int(request.form.get('stock', 0)),
            category_id=int(request.form.get('category_id')) if request.form.get('category_id') else None,
            brand_id=int(request.form.get('brand_id')) if request.form.get('brand_id') else None,
            flavor=request.form.get('flavor', ''),
            weight=request.form.get('weight', ''),
            featured=request.form.get('featured') == 'on',
            bestseller=request.form.get('bestseller') == 'on',
            is_active=request.form.get('is_active') == 'on',
            image=img_name
        )
        db.session.add(p)
        db.session.commit()
        flash('Product added successfully!', 'success')
        return redirect(url_for('admin.products'))
    return render_template('admin/product_form.html', product=None, categories=categories, brands=brands)


@admin_bp.route('/products/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    categories = Category.query.filter_by(is_active=True).all()
    brands = Brand.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        img_file = request.files.get('image')
        if img_file and img_file.filename:
            product.image = save_image(img_file, 'products')
        product.name = request.form.get('name', product.name)
        product.description = request.form.get('description', product.description)
        product.price = float(request.form.get('price', product.price))
        product.original_price = float(request.form.get('original_price') or 0) or None
        product.stock = int(request.form.get('stock', product.stock))
        product.category_id = int(request.form.get('category_id')) if request.form.get('category_id') else None
        product.brand_id = int(request.form.get('brand_id')) if request.form.get('brand_id') else None
        product.flavor = request.form.get('flavor', '')
        product.weight = request.form.get('weight', '')
        product.featured = request.form.get('featured') == 'on'
        product.bestseller = request.form.get('bestseller') == 'on'
        product.is_active = request.form.get('is_active') == 'on'
        db.session.commit()
        flash('Product updated!', 'success')
        return redirect(url_for('admin.products'))
    return render_template('admin/product_form.html', product=product, categories=categories, brands=brands)


@admin_bp.route('/products/delete/<int:id>', methods=['POST'])
@admin_required
def delete_product(id):
    p = Product.query.get_or_404(id)
    p.is_active = False
    db.session.commit()
    flash('Product deactivated.', 'info')
    return redirect(url_for('admin.products'))


@admin_bp.route('/products/toggle/<int:id>', methods=['POST'])
@admin_required
def toggle_product(id):
    p = Product.query.get_or_404(id)
    p.is_active = not p.is_active
    db.session.commit()
    return jsonify({'active': p.is_active})


# ─── CATEGORIES ──────────────────────────────────────────────────────────────

@admin_bp.route('/categories')
@admin_required
def categories():
    cats = Category.query.all()
    return render_template('admin/categories.html', categories=cats)


@admin_bp.route('/categories/add', methods=['GET', 'POST'])
@admin_required
def add_category():
    if request.method == 'POST':
        from slugify import slugify
        name = request.form.get('name')
        img_file = request.files.get('image')
        img_name = save_image(img_file, 'categories') if img_file and img_file.filename else None
        cat = Category(name=name, slug=slugify(name),
                       icon=request.form.get('icon', '📦'),
                       description=request.form.get('description', ''),
                       image=img_name,
                       is_active=request.form.get('is_active') == 'on')
        db.session.add(cat)
        db.session.commit()
        flash('Category added!', 'success')
        return redirect(url_for('admin.categories'))
    return render_template('admin/category_form.html', category=None)


@admin_bp.route('/categories/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_category(id):
    cat = Category.query.get_or_404(id)
    if request.method == 'POST':
        from slugify import slugify
        img_file = request.files.get('image')
        if img_file and img_file.filename:
            cat.image = save_image(img_file, 'categories')
        cat.name = request.form.get('name', cat.name)
        cat.slug = slugify(cat.name)
        cat.icon = request.form.get('icon', cat.icon)
        cat.description = request.form.get('description', cat.description)
        cat.is_active = request.form.get('is_active') == 'on'
        db.session.commit()
        flash('Category updated!', 'success')
        return redirect(url_for('admin.categories'))
    return render_template('admin/category_form.html', category=cat)


@admin_bp.route('/categories/delete/<int:id>', methods=['POST'])
@admin_required
def delete_category(id):
    cat = Category.query.get_or_404(id)
    db.session.delete(cat)
    db.session.commit()
    flash('Category deleted!', 'success')
    return redirect(url_for('admin.categories'))


# ─── BRANDS ──────────────────────────────────────────────────────────────────

@admin_bp.route('/brands')
@admin_required
def brands():
    brands = Brand.query.all()
    return render_template('admin/brands.html', brands=brands)


@admin_bp.route('/brands/add', methods=['GET', 'POST'])
@admin_required
def add_brand():
    if request.method == 'POST':
        from slugify import slugify
        name = request.form.get('name')
        img_file = request.files.get('logo')
        img_name = save_image(img_file, 'brands') if img_file and img_file.filename else None
        brand = Brand(name=name, slug=slugify(name),
                      description=request.form.get('description', ''),
                      logo=img_name,
                      is_active=request.form.get('is_active') == 'on')
        db.session.add(brand)
        db.session.commit()
        flash('Brand added!', 'success')
        return redirect(url_for('admin.brands'))
    return render_template('admin/brand_form.html', brand=None)


@admin_bp.route('/brands/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_brand(id):
    brand = Brand.query.get_or_404(id)
    if request.method == 'POST':
        from slugify import slugify
        img_file = request.files.get('logo')
        if img_file and img_file.filename:
            brand.logo = save_image(img_file, 'brands')
        brand.name = request.form.get('name', brand.name)
        brand.slug = slugify(brand.name)
        brand.description = request.form.get('description', brand.description)
        brand.is_active = request.form.get('is_active') == 'on'
        db.session.commit()
        flash('Brand updated!', 'success')
        return redirect(url_for('admin.brands'))
    return render_template('admin/brand_form.html', brand=brand)


@admin_bp.route('/brands/delete/<int:id>', methods=['POST'])
@admin_required
def delete_brand(id):
    brand = Brand.query.get_or_404(id)
    db.session.delete(brand)
    db.session.commit()
    flash('Brand deleted!', 'success')
    return redirect(url_for('admin.brands'))


# ─── ORDERS ──────────────────────────────────────────────────────────────────

@admin_bp.route('/orders')
@admin_required
def orders():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    search = request.args.get('q', '')
    query = Order.query
    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.join(User).filter(
            (Order.order_number.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )
    orders = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('admin/orders.html', orders=orders,
                           status_filter=status, search=search,
                           status_choices=Order.STATUS_CHOICES)


@admin_bp.route('/orders/<int:id>')
@admin_required
def order_detail(id):
    order = Order.query.get_or_404(id)
    return render_template('admin/order_detail.html', order=order,
                           status_choices=Order.STATUS_CHOICES)


@admin_bp.route('/orders/<int:id>/update-status', methods=['POST'])
@admin_required
def update_order_status(id):
    order = Order.query.get_or_404(id)
    new_status = request.form.get('status')
    if new_status in Order.STATUS_CHOICES:
        order.status = new_status
        db.session.commit()
        flash(f'Order status updated to {new_status}.', 'success')
    return redirect(url_for('admin.order_detail', id=id))


# ─── USERS ───────────────────────────────────────────────────────────────────

@admin_bp.route('/users')
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '')
    query = User.query
    if search:
        query = query.filter(
            (User.name.ilike(f'%{search}%')) | (User.email.ilike(f'%{search}%'))
        )
    users = query.order_by(User.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('admin/users.html', users=users, search=search)


@admin_bp.route('/users/<int:id>/toggle', methods=['POST'])
@admin_required
def toggle_user(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash('Cannot deactivate yourself.', 'danger')
        return redirect(url_for('admin.users'))
    user.is_active = not user.is_active
    db.session.commit()
    flash(f'User {"activated" if user.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin.users'))


# ─── COUPONS ─────────────────────────────────────────────────────────────────

@admin_bp.route('/coupons')
@admin_required
def coupons():
    coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()
    return render_template('admin/coupons.html', coupons=coupons)


@admin_bp.route('/coupons/add', methods=['GET', 'POST'])
@admin_required
def add_coupon():
    if request.method == 'POST':
        expires_str = request.form.get('expires_at')
        coupon = Coupon(
            code=request.form.get('code', '').upper().strip(),
            discount_type=request.form.get('discount_type', 'percent'),
            discount_value=float(request.form.get('discount_value', 0)),
            min_order_amount=float(request.form.get('min_order_amount') or 0),
            max_discount=float(request.form.get('max_discount') or 0) or None,
            usage_limit=int(request.form.get('usage_limit') or 0) or None,
            is_active=request.form.get('is_active') == 'on',
            expires_at=datetime.strptime(expires_str, '%Y-%m-%d') if expires_str else None
        )
        db.session.add(coupon)
        db.session.commit()
        flash('Coupon created!', 'success')
        return redirect(url_for('admin.coupons'))
    return render_template('admin/coupon_form.html', coupon=None)


@admin_bp.route('/coupons/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_coupon(id):
    coupon = Coupon.query.get_or_404(id)
    if request.method == 'POST':
        expires_str = request.form.get('expires_at')
        coupon.code = request.form.get('code', '').upper().strip()
        coupon.discount_type = request.form.get('discount_type', 'percent')
        coupon.discount_value = float(request.form.get('discount_value', 0))
        coupon.min_order_amount = float(request.form.get('min_order_amount') or 0)
        coupon.max_discount = float(request.form.get('max_discount') or 0) or None
        coupon.usage_limit = int(request.form.get('usage_limit') or 0) or None
        coupon.is_active = request.form.get('is_active') == 'on'
        coupon.expires_at = datetime.strptime(expires_str, '%Y-%m-%d') if expires_str else None
        db.session.commit()
        flash('Coupon updated!', 'success')
        return redirect(url_for('admin.coupons'))
    return render_template('admin/coupon_form.html', coupon=coupon)


@admin_bp.route('/coupons/delete/<int:id>', methods=['POST'])
@admin_required
def delete_coupon(id):
    coupon = Coupon.query.get_or_404(id)
    db.session.delete(coupon)
    db.session.commit()
    flash('Coupon deleted.', 'success')
    return redirect(url_for('admin.coupons'))


# ─── BANNERS ─────────────────────────────────────────────────────────────────

@admin_bp.route('/banners')
@admin_required
def banners():
    banners = Banner.query.order_by(Banner.position).all()
    return render_template('admin/banners.html', banners=banners)


@admin_bp.route('/banners/add', methods=['GET', 'POST'])
@admin_required
def add_banner():
    if request.method == 'POST':
        img_file = request.files.get('image')
        img_name = save_image(img_file, 'banners') if img_file and img_file.filename else None
        b = Banner(title=request.form.get('title'), subtitle=request.form.get('subtitle'),
                   link=request.form.get('link', ''), image=img_name,
                   position=int(request.form.get('position', 0)),
                   bg_color=request.form.get('bg_color', '#0a1628'),
                   is_active=request.form.get('is_active') == 'on')
        db.session.add(b)
        db.session.commit()
        flash('Banner added!', 'success')
        return redirect(url_for('admin.banners'))
    return render_template('admin/banner_form.html', banner=None)


@admin_bp.route('/banners/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_banner(id):
    banner = Banner.query.get_or_404(id)
    if request.method == 'POST':
        img_file = request.files.get('image')
        if img_file and img_file.filename:
            banner.image = save_image(img_file, 'banners')
        banner.title = request.form.get('title', banner.title)
        banner.subtitle = request.form.get('subtitle', banner.subtitle)
        banner.link = request.form.get('link', banner.link)
        banner.position = int(request.form.get('position', banner.position))
        banner.bg_color = request.form.get('bg_color', banner.bg_color)
        banner.is_active = request.form.get('is_active') == 'on'
        db.session.commit()
        flash('Banner updated!', 'success')
        return redirect(url_for('admin.banners'))
    return render_template('admin/banner_form.html', banner=banner)


@admin_bp.route('/banners/delete/<int:id>', methods=['POST'])
@admin_required
def delete_banner(id):
    b = Banner.query.get_or_404(id)
    db.session.delete(b)
    db.session.commit()
    flash('Banner deleted.', 'success')
    return redirect(url_for('admin.banners'))


# ─── REVIEWS ─────────────────────────────────────────────────────────────────

@admin_bp.route('/reviews')
@admin_required
def reviews():
    page = request.args.get('page', 1, type=int)
    reviews = Review.query.order_by(Review.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('admin/reviews.html', reviews=reviews)


@admin_bp.route('/reviews/delete/<int:id>', methods=['POST'])
@admin_required
def delete_review(id):
    r = Review.query.get_or_404(id)
    db.session.delete(r)
    db.session.commit()
    flash('Review deleted.', 'success')
    return redirect(url_for('admin.reviews'))


# ─── REPORTS ─────────────────────────────────────────────────────────────────

@admin_bp.route('/reports')
@admin_required
def reports():
    from sqlalchemy import extract
    top_products = db.session.query(
        Product.name,
        func.sum(OrderItem.quantity).label('units'),
        func.sum(OrderItem.total).label('revenue')
    ).join(OrderItem).group_by(Product.id).order_by(func.sum(OrderItem.total).desc()).limit(10).all()

    revenue_by_cat = db.session.query(
        Category.name,
        func.sum(OrderItem.total).label('revenue')
    ).join(Product, Product.category_id == Category.id).join(
        OrderItem, OrderItem.product_id == Product.id
    ).group_by(Category.id).all()

    monthly = db.session.query(
        func.strftime('%Y-%m', Order.created_at).label('month'),
        func.count(Order.id).label('orders'),
        func.sum(Order.final_amount).label('revenue')
    ).group_by('month').order_by('month').limit(12).all()

    return render_template('admin/reports.html', top_products=top_products,
                           revenue_by_cat=revenue_by_cat, monthly=monthly)


# ─── SETTINGS ────────────────────────────────────────────────────────────────

@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    if request.method == 'POST':
        flash('Settings saved successfully!', 'success')
        return redirect(url_for('admin.settings'))
    return render_template('admin/settings.html')
