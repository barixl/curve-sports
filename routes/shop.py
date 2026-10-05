from collections import defaultdict
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user, login_required
from extensions import db
from models import Product, Category, Brand, Review, Wishlist, Banner, OrderItem
from sqlalchemy import func
from sqlalchemy.orm import joinedload

shop_bp = Blueprint('shop', __name__)


@shop_bp.route('/')
def index():
    featured = Product.query.options(joinedload(Product.brand), joinedload(Product.variations)).filter_by(featured=True, is_active=True).limit(8).all()
    bestsellers = Product.query.options(joinedload(Product.brand), joinedload(Product.variations)).filter_by(bestseller=True, is_active=True).limit(8).all()
    categories = Category.query.filter_by(is_active=True, parent_id=None).order_by(Category.id.asc()).all()
    new_arrivals = Product.query.options(joinedload(Product.brand), joinedload(Product.variations)).filter_by(is_active=True).order_by(Product.created_at.desc()).limit(8).all()
    banners = Banner.query.filter_by(is_active=True).order_by(Banner.position).all()
    brands = Brand.query.filter(Brand.is_active==True, Brand.logo.isnot(None)).all()

    # Build a section for every active parent that has 2+ active subcategories with products
    stocked = {cid for (cid,) in db.session.query(Product.category_id).filter(Product.is_active == True).distinct()}
    category_sections = []
    all_parents = Category.query.options(joinedload(Category.children)).filter_by(is_active=True, parent_id=None).order_by(Category.id.asc()).all()
    for parent in all_parents:
        active_children = [c for c in parent.children if c.is_active and c.id in stocked]
        if len(active_children) >= 2:
            category_sections.append({'parent': parent, 'children': active_children})

    # "What's selling now" tabs: categories ranked by units sold, then by range size
    sold = func.coalesce(func.sum(OrderItem.quantity), 0)
    top_cats = (db.session.query(Category)
                .join(Product, Product.category_id == Category.id)
                .outerjoin(OrderItem, OrderItem.product_id == Product.id)
                .filter(Category.is_active == True, Product.is_active == True)
                .group_by(Category.id)
                .order_by(sold.desc(), func.count(func.distinct(Product.id)).desc())
                .limit(7).all())
    selling_tabs = [{
        'category': cat,
        'products': Product.query.options(joinedload(Product.brand), joinedload(Product.variations))
                    .filter_by(category_id=cat.id, is_active=True)
                    .order_by(Product.bestseller.desc(), Product.review_count.desc(), Product.id.asc())
                    .limit(10).all(),
    } for cat in top_cats]

    testimonials = [
        {
            'name': 'Rohit S.',
            'city': 'Bengaluru',
            'rating': 5,
            'quote': 'Authentic products and quick delivery. My pre-workout and whey always arrive sealed and fresh.'
        },
        {
            'name': 'Ananya K.',
            'city': 'Pune',
            'rating': 5,
            'quote': 'Loved the vitamins range. The site is easy to use and the support team helped me choose the right stack.'
        },
        {
            'name': 'Vikram P.',
            'city': 'Delhi',
            'rating': 4,
            'quote': 'Great pricing and clean checkout. I regularly order creatine and protein bars from here.'
        },
        {
            'name': 'Megha R.',
            'city': 'Hyderabad',
            'rating': 5,
            'quote': 'Performance Nutrition section is super useful. The category cards make browsing very fast.'
        },
        {
            'name': 'Arjun M.',
            'city': 'Chennai',
            'rating': 5,
            'quote': 'Good experience on mobile too. Ordering, payments, and tracking are smooth and reliable.'
        },
    ]

    return render_template('shop/index.html', featured=featured, bestsellers=bestsellers,
                           categories=categories, new_arrivals=new_arrivals, banners=banners, brands=brands,
                           category_sections=category_sections, selling_tabs=selling_tabs,
                           testimonials=testimonials)


@shop_bp.route('/products')
def products():
    page = request.args.get('page', 1, type=int)
    category_slugs = request.args.getlist('category')
    brand_slugs = request.args.getlist('brand')
    sort = request.args.get('sort', 'popular')
    search = request.args.get('q', '').strip()
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    on_sale = request.args.get('offers', type=int)

    query = Product.query.options(joinedload(Product.brand), joinedload(Product.variations)).filter_by(is_active=True)

    if on_sale:
        query = query.filter(Product.original_price > Product.price)
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))

    selected_cats = []
    if category_slugs:
        selected_cats = Category.query.filter(Category.slug.in_(category_slugs)).all()
        if selected_cats:
            # A parent category also covers everything in its subcategories
            cat_ids = {c.id for c in selected_cats}
            cat_ids |= {c.id for parent in selected_cats for c in parent.children if c.is_active}
            query = query.filter(Product.category_id.in_(cat_ids))

    selected_brands = []
    if brand_slugs:
        selected_brands = Brand.query.filter(Brand.slug.in_(brand_slugs)).all()
        if selected_brands:
            query = query.filter(Product.brand_id.in_([b.id for b in selected_brands]))

    if min_price:
        query = query.filter(Product.price >= min_price)
    if max_price:
        query = query.filter(Product.price <= max_price)

    if sort == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_desc':
        query = query.order_by(Product.price.desc())
    elif sort == 'newest':
        query = query.order_by(Product.created_at.desc())
    elif sort == 'rating':
        query = query.order_by(Product.rating.desc())
    else:
        query = query.order_by(Product.review_count.desc())

    pagination = query.paginate(page=page, per_page=20, error_out=False)

    all_categories = Category.query.filter_by(is_active=True).all()
    all_brands = Brand.query.filter_by(is_active=True).order_by(Brand.name).all()

    grouped_brands = defaultdict(list)
    for b in all_brands:
        first = b.name[0].upper()
        grouped_brands[first if first.isalpha() else '#'].append(b)
    alphabet = sorted(grouped_brands.keys())

    selected_cat_slugs = [c.slug for c in selected_cats]
    selected_brand_slugs = [b.slug for b in selected_brands]

    return render_template('shop/products.html',
        products=pagination.items,
        pagination=pagination,
        categories=all_categories,
        brands=all_brands,
        grouped_brands=grouped_brands,
        alphabet=alphabet,
        selected_cats=selected_cats,
        selected_cat=selected_cats[0] if len(selected_cats) == 1 else None,
        selected_cat_slugs=selected_cat_slugs,
        selected_brands=selected_brands,
        selected_brand=selected_brands[0] if len(selected_brands) == 1 else None,
        selected_brand_slugs=selected_brand_slugs,
        sort=sort,
        search=search,
        offers=on_sale,
    )


@shop_bp.route('/product/<slug>')
def product_detail(slug):
    product = Product.query.options(
        joinedload(Product.brand),
        joinedload(Product.images),
        joinedload(Product.variations)
    ).filter_by(slug=slug, is_active=True).first_or_404()
    related = Product.query.options(
        joinedload(Product.brand),
        joinedload(Product.variations)
    ).filter(
        Product.category_id == product.category_id,
        Product.id != product.id,
        Product.is_active == True
    ).limit(4).all()
    reviews = Review.query.filter_by(product_id=product.id).order_by(Review.created_at.desc()).all()
    in_wishlist = False
    if current_user.is_authenticated:
        in_wishlist = Wishlist.query.filter_by(user_id=current_user.id, product_id=product.id).first() is not None

    # Pack shown as selected on load: the primary one, or the first that is in stock
    selected_variation = None
    can_buy = product.stock > 0
    if product.product_type == 'variable':
        in_stock = [v for v in product.variations if v.stock > 0]
        selected_variation = next((v for v in in_stock if v.is_primary), in_stock[0] if in_stock else None)
        can_buy = selected_variation is not None

    return render_template('shop/product_detail.html', product=product,
                           related=related, reviews=reviews, in_wishlist=in_wishlist,
                           selected_variation=selected_variation, can_buy=can_buy)


@shop_bp.route('/product/<int:product_id>/review', methods=['POST'])
@login_required
def add_review(product_id):
    product = Product.query.get_or_404(product_id)
    existing = Review.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if existing:
        flash('You have already reviewed this product.', 'warning')
        return redirect(url_for('shop.product_detail', slug=product.slug))
    rating = request.form.get('rating', type=int)
    title = request.form.get('title', '').strip()
    body = request.form.get('body', '').strip()
    if not rating or rating < 1 or rating > 5:
        flash('Please select a valid rating.', 'danger')
        return redirect(url_for('shop.product_detail', slug=product.slug))
    review = Review(product_id=product_id, user_id=current_user.id,
                    rating=rating, title=title, body=body)
    db.session.add(review)
    db.session.flush()  # the query below already includes this review — don't count it twice
    all_reviews = Review.query.filter_by(product_id=product_id).all()
    product.rating = round(sum(r.rating for r in all_reviews) / len(all_reviews), 1)
    product.review_count = len(all_reviews)
    db.session.commit()
    flash('Review submitted successfully!', 'success')
    return redirect(url_for('shop.product_detail', slug=product.slug))


@shop_bp.route('/wishlist/toggle/<int:product_id>', methods=['POST'])
@login_required
def toggle_wishlist(product_id):
    item = Wishlist.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if item:
        db.session.delete(item)
        db.session.commit()
        return jsonify({'status': 'removed'})
    else:
        db.session.add(Wishlist(user_id=current_user.id, product_id=product_id))
        db.session.commit()
        return jsonify({'status': 'added'})


@shop_bp.route('/wishlist')
@login_required
def wishlist():
    items = Wishlist.query.filter_by(user_id=current_user.id).all()
    products = [Product.query.get(w.product_id) for w in items]
    return render_template('shop/wishlist.html', products=products)


@shop_bp.route('/search')
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return redirect(url_for('shop.products'))
    return redirect(url_for('shop.products', q=q))


@shop_bp.route('/terms')
def terms():
    return render_template('shop/terms.html')

@shop_bp.route('/privacy')
def privacy():
    return render_template('shop/privacy.html')

@shop_bp.route('/refund')
def refund():
    return render_template('shop/refund.html')

@shop_bp.route('/shipping')
def shipping():
    return render_template('shop/shipping.html')

@shop_bp.route('/contact')
def contact():
    return render_template('shop/contact.html')
