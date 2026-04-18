from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import current_user, login_required
from extensions import db
from models import Product, Order, OrderItem, Address, Coupon
import json

cart_bp = Blueprint('cart', __name__)


def get_cart():
    return session.get('cart', {})


def save_cart(cart):
    session['cart'] = cart
    session.modified = True


def cart_total(cart):
    total = 0
    for pid, item in cart.items():
        p = Product.query.get(int(pid))
        if p and p.is_active:
            total += p.price * item['qty']
    return total


@cart_bp.route('/cart')
def cart():
    cart = get_cart()
    items = []
    subtotal = 0
    for pid, data in cart.items():
        p = Product.query.get(int(pid))
        if p and p.is_active:
            item_total = p.price * data['qty']
            subtotal += item_total
            items.append({'product': p, 'qty': data['qty'], 'total': item_total})
    delivery = 0 if subtotal >= 499 else 49
    coupon_discount = session.get('coupon_discount', 0)
    coupon_code = session.get('coupon_code', '')
    grand_total = subtotal + delivery - coupon_discount
    return render_template('shop/cart.html', items=items, subtotal=subtotal,
                           delivery=delivery, coupon_discount=coupon_discount,
                           coupon_code=coupon_code, grand_total=grand_total)


@cart_bp.route('/cart/add', methods=['POST'])
def add_to_cart():
    product_id = request.form.get('product_id', type=int)
    qty = request.form.get('qty', 1, type=int)
    product = Product.query.get_or_404(product_id)
    if not product.in_stock():
        flash('Product is out of stock.', 'danger')
        return redirect(request.referrer or url_for('shop.index'))
    cart = get_cart()
    pid = str(product_id)
    if pid in cart:
        cart[pid]['qty'] = min(cart[pid]['qty'] + qty, product.stock)
    else:
        cart[pid] = {'qty': qty}
    save_cart(cart)
    flash(f'"{product.name}" added to cart!', 'success')
    return redirect(request.referrer or url_for('cart.cart'))


@cart_bp.route('/cart/update', methods=['POST'])
def update_cart():
    product_id = str(request.form.get('product_id', type=int))
    qty = request.form.get('qty', 1, type=int)
    cart = get_cart()
    if product_id in cart:
        if qty <= 0:
            del cart[product_id]
        else:
            p = Product.query.get(int(product_id))
            cart[product_id]['qty'] = min(qty, p.stock if p else qty)
    save_cart(cart)
    return redirect(url_for('cart.cart'))


@cart_bp.route('/cart/remove/<int:product_id>')
def remove_from_cart(product_id):
    cart = get_cart()
    cart.pop(str(product_id), None)
    save_cart(cart)
    flash('Item removed from cart.', 'info')
    return redirect(url_for('cart.cart'))


@cart_bp.route('/cart/apply-coupon', methods=['POST'])
def apply_coupon():
    code = request.form.get('coupon_code', '').strip().upper()
    cart = get_cart()
    subtotal = cart_total(cart)
    coupon = Coupon.query.filter_by(code=code).first()
    if not coupon:
        flash('Invalid coupon code.', 'danger')
        return redirect(url_for('cart.cart'))
    valid, msg = coupon.is_valid(subtotal)
    if not valid:
        flash(msg, 'danger')
        return redirect(url_for('cart.cart'))
    discount = coupon.calculate_discount(subtotal)
    session['coupon_code'] = code
    session['coupon_discount'] = discount
    session['coupon_id'] = coupon.id
    flash(f'Coupon applied! You saved ₹{discount:.0f}', 'success')
    return redirect(url_for('cart.cart'))


@cart_bp.route('/cart/remove-coupon')
def remove_coupon():
    session.pop('coupon_code', None)
    session.pop('coupon_discount', None)
    session.pop('coupon_id', None)
    flash('Coupon removed.', 'info')
    return redirect(url_for('cart.cart'))


@cart_bp.route('/cart/count')
def cart_count():
    cart = get_cart()
    return jsonify({'count': sum(v['qty'] for v in cart.values())})


@cart_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart = get_cart()
    if not cart:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('cart.cart'))
    items = []
    subtotal = 0
    for pid, data in cart.items():
        p = Product.query.get(int(pid))
        if p and p.is_active and p.in_stock():
            item_total = p.price * data['qty']
            subtotal += item_total
            items.append({'product': p, 'qty': data['qty'], 'total': item_total})
    delivery = 0 if subtotal >= 499 else 49
    coupon_discount = session.get('coupon_discount', 0)
    grand_total = subtotal + delivery - coupon_discount
    addresses = Address.query.filter_by(user_id=current_user.id).all()

    if request.method == 'POST':
        address_id = request.form.get('address_id', type=int)
        payment_method = request.form.get('payment_method', 'COD')
        new_addr = request.form.get('new_address') == 'on'

        if new_addr or not address_id:
            addr = Address(
                user_id=current_user.id,
                full_name=request.form.get('full_name'),
                phone=request.form.get('phone'),
                address_line1=request.form.get('address_line1'),
                address_line2=request.form.get('address_line2', ''),
                city=request.form.get('city'),
                state=request.form.get('state'),
                pincode=request.form.get('pincode'),
            )
            db.session.add(addr)
            db.session.flush()
            address_id = addr.id

        addr = Address.query.get(address_id)
        addr_snapshot = json.dumps({
            'full_name': addr.full_name, 'phone': addr.phone,
            'address_line1': addr.address_line1, 'address_line2': addr.address_line2,
            'city': addr.city, 'state': addr.state, 'pincode': addr.pincode
        })

        order = Order(
            user_id=current_user.id,
            total_amount=subtotal,
            discount_amount=coupon_discount,
            delivery_charge=delivery,
            final_amount=grand_total,
            payment_method=payment_method,
            coupon_code=session.get('coupon_code', ''),
            address_id=address_id,
            address_snapshot=addr_snapshot,
            status='Confirmed' if payment_method == 'COD' else 'Pending'
        )
        order.generate_order_number()
        db.session.add(order)
        db.session.flush()

        for item in items:
            oi = OrderItem(
                order_id=order.id,
                product_id=item['product'].id,
                quantity=item['qty'],
                price=item['product'].price,
                total=item['total']
            )
            db.session.add(oi)
            item['product'].stock -= item['qty']

        if session.get('coupon_id'):
            c = Coupon.query.get(session['coupon_id'])
            if c:
                c.used_count += 1

        db.session.commit()
        session['cart'] = {}
        session.pop('coupon_code', None)
        session.pop('coupon_discount', None)
        session.pop('coupon_id', None)
        flash(f'Order #{order.order_number} placed successfully!', 'success')
        return redirect(url_for('cart.order_success', order_id=order.id))

    return render_template('shop/checkout.html', items=items, subtotal=subtotal,
                           delivery=delivery, coupon_discount=coupon_discount,
                           grand_total=grand_total, addresses=addresses)


@cart_bp.route('/order/success/<int:order_id>')
@login_required
def order_success(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    return render_template('shop/order_success.html', order=order)
