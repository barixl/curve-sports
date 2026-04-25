from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from functools import wraps
from extensions import db
from models import (User, Product, Category, Brand, Order, OrderItem,
                    Coupon, Review, Banner, ProductImage, Setting,
                    Attribute, AttributeValue, ProductVariation)
from context import invalidate_nav_cache
from datetime import datetime, timedelta
from sqlalchemy import func
import os, uuid
from werkzeug.utils import secure_filename
from slugify import slugify

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


import cloudinary
import cloudinary.uploader

def save_image(file, folder):
    if file and allowed_file(file.filename):
        try:
            # Upload to Cloudinary
            result = cloudinary.uploader.upload(
                file, 
                folder=folder,
                resource_type="auto"
            )
            # Return the secure URL from Cloudinary
            return result.get('secure_url')
        except Exception as e:
            print(f"Cloudinary upload error: {e}")
            return None
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

    today_orders = Order.query.filter(func.cast(Order.created_at, db.Date) == today).count()
    today_revenue = db.session.query(func.sum(Order.final_amount)).filter(
        func.cast(Order.created_at, db.Date) == today).scalar() or 0

    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    low_stock = Product.query.filter(Product.stock < 20, Product.is_active == True).all()

    monthly_revenue = []
    for i in range(6):
        d = datetime.utcnow() - timedelta(days=30 * i)
        rev = db.session.query(func.sum(Order.final_amount)).filter(
            func.to_char(Order.created_at, 'YYYY-MM') == d.strftime('%Y-%m')
        ).scalar() or 0
        monthly_revenue.append({'month': d.strftime('%b %Y'), 'revenue': float(rev)})
    monthly_revenue.reverse()

    order_status_counts = db.session.query(
        Order.status, func.count(Order.id)
    ).group_by(Order.status).all()
    # Convert Row objects to lists for JSON serialization
    order_status_counts = [list(r) for r in order_status_counts]

    top_products = db.session.query(
        Product.name, func.sum(OrderItem.quantity).label('sold')
    ).join(OrderItem).group_by(Product.id).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()
    top_products = [list(r) for r in top_products]

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
            featured=request.form.get('featured') == 'on',
            bestseller=request.form.get('bestseller') == 'on',
            is_active=request.form.get('is_active') == 'on',
            image=img_name,
            product_type=request.form.get('product_type', 'simple')
        )
        db.session.add(p)
        db.session.flush() # To get product id

        # Multiple Images
        images_files = request.files.getlist('gallery')
        for img_file in images_files:
            if img_file and img_file.filename:
                saved_name = save_image(img_file, 'products')
                if saved_name:
                    pi = ProductImage(product_id=p.id, image=saved_name)
                    db.session.add(pi)

        # Handle Variations if Variable
        if p.product_type == 'variable':
            var_prices = request.form.getlist('var_price[]')
            var_stocks = request.form.getlist('var_stock[]')
            var_value_ids = request.form.getlist('var_values[]') # Comma separated IDs "1,5"
            variation_uids = request.form.getlist('variation_uid[]')
            primary_variation_uid = request.form.get('primary_variation')
            created_variations = []

            for i in range(len(var_prices)):
                pv = ProductVariation(
                    product_id=p.id,
                    price=float(var_prices[i]) if var_prices[i] else p.price,
                    stock=int(var_stocks[i]) if var_stocks[i] else 0,
                    sku=f"{p.slug}-{i}-{uuid.uuid4().hex[:4]}"
                )
                if var_value_ids[i]:
                    # Use set() to ensure unique value IDs per variation
                    ids = list(set([int(vid) for vid in var_value_ids[i].split(',') if vid]))
                    vals = AttributeValue.query.filter(AttributeValue.id.in_(ids)).all()
                    pv.values = vals
                pv.is_primary = (i < len(variation_uids) and variation_uids[i] == primary_variation_uid)
                db.session.add(pv)
                created_variations.append(pv)

            if created_variations:
                primary_variation = next((v for v in created_variations if v.is_primary), created_variations[0])
                for v in created_variations:
                    v.is_primary = (v == primary_variation)
                p.price = primary_variation.price
                if p.original_price is None:
                    p.original_price = primary_variation.price

        db.session.commit()
        flash('Product added successfully!', 'success')
        return redirect(url_for('admin.products'))
    return render_template('admin/product_form.html', product=None, categories=categories, brands=brands, attributes=Attribute.query.all())


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
        product.featured = request.form.get('featured') == 'on'
        product.bestseller = request.form.get('bestseller') == 'on'
        product.is_active = request.form.get('is_active') == 'on'
        product.product_type = request.form.get('product_type', product.product_type)

        # Multiple Images
        images_files = request.files.getlist('gallery')
        for img_file in images_files:
            if img_file and img_file.filename:
                saved_name = save_image(img_file, 'products')
                if saved_name:
                    pi = ProductImage(product_id=product.id, image=saved_name)
                    db.session.add(pi)

        # Sync Variations
        if product.product_type == 'variable':
            # Use session delete to trigger cascades correctly
            for v in product.variations[:]:
                db.session.delete(v)
            db.session.flush() # Ensure deletions are processed before insertions
            
            var_prices = request.form.getlist('var_price[]')
            var_stocks = request.form.getlist('var_stock[]')
            var_value_ids = request.form.getlist('var_values[]')
            variation_uids = request.form.getlist('variation_uid[]')
            primary_variation_uid = request.form.get('primary_variation')
            created_variations = []

            for i in range(len(var_prices)):
                pv = ProductVariation(
                    product_id=product.id,
                    price=float(var_prices[i]) if var_prices[i] else product.price,
                    stock=int(var_stocks[i]) if var_stocks[i] else 0,
                    sku=f"{product.slug}-{i}-{uuid.uuid4().hex[:4]}"
                )
                if var_value_ids[i]:
                    # Use set() to ensure unique value IDs per variation to avoid IntegrityError
                    ids = list(set([int(vid) for vid in var_value_ids[i].split(',') if vid]))
                    vals = AttributeValue.query.filter(AttributeValue.id.in_(ids)).all()
                    pv.values = vals
                pv.is_primary = (i < len(variation_uids) and variation_uids[i] == primary_variation_uid)
                db.session.add(pv)
                created_variations.append(pv)

            if created_variations:
                primary_variation = next((v for v in created_variations if v.is_primary), created_variations[0])
                for v in created_variations:
                    v.is_primary = (v == primary_variation)
                product.price = primary_variation.price
                if product.original_price is None:
                    product.original_price = primary_variation.price

        db.session.commit()
        flash('Product updated!', 'success')
        return redirect(url_for('admin.products'))
    return render_template('admin/product_form.html', product=product, categories=categories, brands=brands, attributes=Attribute.query.all())


@admin_bp.route('/products/delete/<int:id>', methods=['POST'])
@admin_required
def delete_product(id):
    p = Product.query.get_or_404(id)
    
    # Check if the product is in any orders
    if p.order_items:
        p.is_active = False
        db.session.commit()
        flash(f'Product "{p.name}" has order history and cannot be fully deleted. It has been deactivated instead.', 'info')
    else:
        db.session.delete(p)
        db.session.commit()
        flash(f'Product "{p.name}" has been permanently deleted.', 'success')
    
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
                       description=request.form.get('description', ''),
                       image=img_name,
                       parent_id=request.form.get('parent_id', type=int) or None,
                       is_active=request.form.get('is_active') == 'on')
        db.session.add(cat)
        db.session.commit()
        invalidate_nav_cache()
        flash('Category added!', 'success')
        return redirect(url_for('admin.categories'))
    parent_categories = Category.query.filter_by(parent_id=None).order_by(Category.name.asc()).all()
    return render_template('admin/category_form.html', category=None, parent_categories=parent_categories)


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
        cat.description = request.form.get('description', cat.description)
        cat.parent_id = request.form.get('parent_id', type=int) or None
        cat.is_active = request.form.get('is_active') == 'on'
        db.session.commit()
        invalidate_nav_cache()
        flash('Category updated!', 'success')
        return redirect(url_for('admin.categories'))
    parent_categories = Category.query.filter(
        Category.parent_id.is_(None),
        Category.id != cat.id
    ).order_by(Category.name.asc()).all()
    return render_template('admin/category_form.html', category=cat, parent_categories=parent_categories)


@admin_bp.route('/categories/delete/<int:id>', methods=['POST'])
@admin_required
def delete_category(id):
    cat = Category.query.get_or_404(id)
    db.session.delete(cat)
    db.session.commit()
    invalidate_nav_cache()
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
        invalidate_nav_cache()
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
        invalidate_nav_cache()
        flash('Brand updated!', 'success')
        return redirect(url_for('admin.brands'))
    return render_template('admin/brand_form.html', brand=brand)


@admin_bp.route('/brands/delete/<int:id>', methods=['POST'])
@admin_required
def delete_brand(id):
    brand = Brand.query.get_or_404(id)
    db.session.delete(brand)
    db.session.commit()
    invalidate_nav_cache()
    flash('Brand deleted!', 'success')
    return redirect(url_for('admin.brands'))


# ─── ATTRIBUTES ──────────────────────────────────────────────────────────────

@admin_bp.route('/attributes')
@admin_required
def attributes():
    attrs = Attribute.query.all()
    return render_template('admin/attributes.html', attributes=attrs)


@admin_bp.route('/attributes/add', methods=['POST'])
@admin_required
def add_attribute():
    name = request.form.get('name')
    if name:
        attr = Attribute(name=name)
        db.session.add(attr)
        db.session.commit()
        flash('Attribute added!', 'success')
    return redirect(url_for('admin.attributes'))


@admin_bp.route('/attributes/<int:id>/add-value', methods=['POST'])
@admin_required
def add_attribute_value(id):
    val = request.form.get('value')
    if val:
        av = AttributeValue(attribute_id=id, value=val)
        db.session.add(av)
        db.session.commit()
        flash('Value added!', 'success')
    return redirect(url_for('admin.attributes'))


@admin_bp.route('/attributes/value/delete/<int:id>', methods=['POST'])
@admin_required
def delete_attribute_value(id):
    av = AttributeValue.query.get_or_404(id)
    db.session.delete(av)
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/attributes/delete/<int:id>', methods=['POST'])
@admin_required
def delete_attribute(id):
    attr = Attribute.query.get_or_404(id)
    db.session.delete(attr)
    db.session.commit()
    return jsonify({'success': True})


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


@admin_bp.route('/orders/update-status/<int:id>', methods=['POST'])
@admin_required
def update_order_status(id):
    order = Order.query.get_or_404(id)
    new_status = request.form.get('status')
    if new_status in Order.STATUS_CHOICES:
        order.status = new_status
        db.session.commit()
        flash(f'Order #{order.order_number} status updated to {new_status}', 'success')
    return redirect(request.referrer or url_for('admin.orders'))


@admin_bp.route('/orders/<int:id>')
@admin_required
def order_detail(id):
    order = Order.query.get_or_404(id)
    return render_template('admin/order_detail.html', order=order,
                           status_choices=Order.STATUS_CHOICES)


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
        func.to_char(Order.created_at, 'YYYY-MM').label('month'),
        func.count(Order.id).label('orders'),
        func.sum(Order.final_amount).label('revenue')
    ).group_by('month').order_by('month').limit(12).all()

    return render_template('admin/reports.html', top_products=top_products,
                           revenue_by_cat=revenue_by_cat, monthly=monthly)


# ─── SETTINGS ────────────────────────────────────────────────────────────────

@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    from models import Setting
    # Keys that must never be overwritten with a blank submission
    SENSITIVE_KEYS = {'razorpay_key_secret', 'razorpay_webhook_secret'}
    # Keys that are never saved from the form at all (handled separately)
    SKIP_KEYS = {'new_password', 'confirm_password'}

    if request.method == 'POST':
        # List of all checkboxes to ensure they are handled even if unchecked
        CHECKBOX_KEYS = {'enable_cod', 'enable_online'}
        
        # 1. Handle all items in the form
        for key, value in request.form.items():
            if key in SKIP_KEYS:
                continue
            # Don't overwrite a saved secret if the admin left the field blank
            if key in SENSITIVE_KEYS and not value.strip():
                continue
            s = Setting.query.filter_by(key=key).first()
            if not s:
                s = Setting(key=key)
                db.session.add(s)
            s.value = value

        # 2. Handle checkboxes that might be missing from the form because they are unchecked
        for key in CHECKBOX_KEYS:
            if key not in request.form:
                s = Setting.query.filter_by(key=key).first()
                if not s:
                    s = Setting(key=key)
                    db.session.add(s)
                s.value = 'off'

        new_pass    = request.form.get('new_password', '').strip()
        confirm_pass = request.form.get('confirm_password', '').strip()
        if new_pass:
            if new_pass == confirm_pass:
                current_user.set_password(new_pass)
            else:
                flash('Passwords do not match!', 'danger')
                return redirect(url_for('admin.settings'))

        db.session.commit()
        flash('Settings saved successfully!', 'success')
        return redirect(url_for('admin.settings'))

    all_s = Setting.query.all()
    settings_dict = {s.key: s.value for s in all_s}
    return render_template('admin/settings.html', settings=settings_dict)
