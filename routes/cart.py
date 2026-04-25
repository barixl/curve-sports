from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, abort
from flask_login import current_user, login_required
from extensions import db
from models import Product, Order, OrderItem, Address, Coupon, Setting
import json, os, hmac, hashlib
import razorpay
import razorpay.errors

cart_bp = Blueprint('cart', __name__)


# ── Session helpers ───────────────────────────────────────────────────────────

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


# ── Settings helpers ──────────────────────────────────────────────────────────

def get_setting(key, default=None):
    s = Setting.query.filter_by(key=key).first()
    return s.value if s else default


def get_shipping_cost(subtotal):
    try:
        threshold = float(get_setting('free_shipping') or 499)
        charge    = float(get_setting('delivery_charge') or 49)
    except (TypeError, ValueError):
        threshold, charge = 499, 49
    return 0 if subtotal >= threshold else charge


def get_razorpay_client():
    """Return (client, key_id). Env vars take priority over DB settings."""
    key_id     = os.environ.get('RAZORPAY_KEY_ID')     or get_setting('razorpay_key_id')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET') or get_setting('razorpay_key_secret')
    if not key_id or not key_secret:
        return None, None
    return razorpay.Client(auth=(key_id, key_secret)), key_id


def online_payment_enabled():
    _, key_id = get_razorpay_client()
    return get_setting('enable_online') == 'on' and bool(key_id)


def cod_enabled():
    v = get_setting('enable_cod')
    return v != 'off'  # default True unless admin explicitly disabled


# ── Internal cart utilities ───────────────────────────────────────────────────

def _build_cart_items():
    """Return (items list, subtotal) from the current session cart."""
    items, subtotal = [], 0
    for pid, data in get_cart().items():
        p = Product.query.get(int(pid))
        if p and p.is_active and p.in_stock():
            item_total = p.price * data['qty']
            subtotal  += item_total
            items.append({'product': p, 'qty': data['qty'], 'total': item_total})
    return items, subtotal


def _clear_checkout_session():
    session['cart'] = {}
    for key in ('coupon_code', 'coupon_discount', 'coupon_id',
                'pending_order_id', 'pending_rzp_order_id'):
        session.pop(key, None)


# ── Cart routes ───────────────────────────────────────────────────────────────

@cart_bp.route('/cart')
def cart():
    cart = get_cart()
    items, subtotal = [], 0
    for pid, data in cart.items():
        p = Product.query.get(int(pid))
        if p and p.is_active:
            item_total = p.price * data['qty']
            subtotal  += item_total
            items.append({'product': p, 'qty': data['qty'], 'total': item_total})
    delivery        = get_shipping_cost(subtotal)
    coupon_discount = session.get('coupon_discount', 0)
    coupon_code     = session.get('coupon_code', '')
    grand_total     = subtotal + delivery - coupon_discount
    return render_template('shop/cart.html', items=items, subtotal=subtotal,
                           delivery=delivery, coupon_discount=coupon_discount,
                           coupon_code=coupon_code, grand_total=grand_total)


@cart_bp.route('/cart/add', methods=['POST'])
def add_to_cart():
    product_id = request.form.get('product_id', type=int)
    qty        = request.form.get('qty', 1, type=int)
    product    = Product.query.get_or_404(product_id)
    if not product.in_stock():
        flash('Product is out of stock.', 'danger')
        return redirect(request.referrer or url_for('shop.index'))
    cart = get_cart()
    pid  = str(product_id)
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
    qty        = request.form.get('qty', 1, type=int)
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
    code    = request.form.get('coupon_code', '').strip().upper()
    subtotal = cart_total(get_cart())
    coupon  = Coupon.query.filter_by(code=code).first()
    if not coupon:
        flash('Invalid coupon code.', 'danger')
        return redirect(url_for('cart.cart'))
    valid, msg = coupon.is_valid(subtotal)
    if not valid:
        flash(msg, 'danger')
        return redirect(url_for('cart.cart'))
    discount = coupon.calculate_discount(subtotal)
    session['coupon_code']     = code
    session['coupon_discount'] = discount
    session['coupon_id']       = coupon.id
    flash(f'Coupon applied! You saved ₹{discount:.0f}', 'success')
    return redirect(url_for('cart.cart'))


@cart_bp.route('/cart/remove-coupon')
def remove_coupon():
    session.pop('coupon_code',     None)
    session.pop('coupon_discount', None)
    session.pop('coupon_id',       None)
    flash('Coupon removed.', 'info')
    return redirect(url_for('cart.cart'))


@cart_bp.route('/cart/count')
def cart_count():
    cart = get_cart()
    return jsonify({'count': sum(v['qty'] for v in cart.values())})


# ── Checkout ──────────────────────────────────────────────────────────────────

@cart_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    if not get_cart():
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('cart.cart'))

    items, subtotal = _build_cart_items()
    if not items:
        flash('No in-stock items in your cart.', 'warning')
        return redirect(url_for('cart.cart'))

    delivery        = get_shipping_cost(subtotal)
    coupon_discount = session.get('coupon_discount', 0)
    grand_total     = max(0.0, subtotal + delivery - coupon_discount)
    addresses       = Address.query.filter_by(user_id=current_user.id).all()

    rzp_enabled = online_payment_enabled()
    cod_on      = cod_enabled()

    if request.method == 'POST':
        payment_method = request.form.get('payment_method', 'COD')

        # Validate selected payment method is actually available
        if payment_method == 'COD' and not cod_on:
            flash('Cash on Delivery is not available right now.', 'danger')
            return redirect(url_for('cart.checkout'))
        if payment_method == 'Online' and not rzp_enabled:
            flash('Online payment is not available right now.', 'danger')
            return redirect(url_for('cart.checkout'))

        # ── Resolve delivery address ──────────────────────────────────────────
        address_id   = request.form.get('address_id', type=int)
        use_new_addr = request.form.get('new_address') == 'on'

        if use_new_addr or not address_id:
            addr = Address(
                user_id      = current_user.id,
                full_name    = request.form.get('full_name',    '').strip(),
                phone        = request.form.get('phone',        '').strip(),
                address_line1= request.form.get('address_line1','').strip(),
                address_line2= request.form.get('address_line2','').strip(),
                city         = request.form.get('city',        '').strip(),
                state        = request.form.get('state',       '').strip(),
                pincode      = request.form.get('pincode',     '').strip(),
            )
            required = [addr.full_name, addr.phone, addr.address_line1,
                        addr.city, addr.state, addr.pincode]
            if not all(required):
                flash('Please fill in all required address fields.', 'danger')
                return redirect(url_for('cart.checkout'))
            db.session.add(addr)
            db.session.flush()
            address_id = addr.id
        else:
            # Security: ensure the address belongs to the current user
            addr = Address.query.filter_by(id=address_id, user_id=current_user.id).first()
            if not addr:
                flash('Invalid address.', 'danger')
                return redirect(url_for('cart.checkout'))

        addr_snapshot = json.dumps({
            'full_name':    addr.full_name,    'phone':    addr.phone,
            'address_line1':addr.address_line1,'address_line2':addr.address_line2,
            'city':         addr.city,         'state':    addr.state,
            'pincode':      addr.pincode,
        })

        # ── Create order record ───────────────────────────────────────────────
        order = Order(
            user_id        = current_user.id,
            total_amount   = subtotal,
            discount_amount= coupon_discount,
            delivery_charge= delivery,
            final_amount   = grand_total,
            payment_method = payment_method,
            payment_status = 'Pending',
            coupon_code    = session.get('coupon_code', ''),
            address_id     = address_id,
            address_snapshot=addr_snapshot,
            status         = 'Pending',
        )
        order.generate_order_number()
        db.session.add(order)
        db.session.flush()

        for item in items:
            db.session.add(OrderItem(
                order_id  = order.id,
                product_id= item['product'].id,
                quantity  = item['qty'],
                price     = item['product'].price,
                total     = item['total'],
            ))

        # ── COD path ──────────────────────────────────────────────────────────
        if payment_method == 'COD':
            order.status         = 'Confirmed'
            order.payment_status = 'COD'
            for item in items:
                item['product'].stock = max(0, item['product'].stock - item['qty'])
            if session.get('coupon_id'):
                c = Coupon.query.get(session['coupon_id'])
                if c:
                    c.used_count += 1
            db.session.commit()
            _clear_checkout_session()
            flash(f'Order #{order.order_number} placed successfully!', 'success')
            return redirect(url_for('cart.order_success', order_id=order.id))

        # ── Online payment path (Razorpay) ─────────────────────────────────────
        client, key_id = get_razorpay_client()
        if not client:
            db.session.rollback()
            flash('Online payment is unavailable right now. Please use COD.', 'danger')
            return redirect(url_for('cart.checkout'))

        try:
            rzp_order = client.order.create(data={
                'amount':   int(grand_total * 100),   # paise
                'currency': 'INR',
                'receipt':  order.order_number,
                'notes':    {'user_id': str(current_user.id)},
            })
        except Exception:
            db.session.rollback()
            flash('Could not connect to payment gateway. Please try again.', 'danger')
            return redirect(url_for('cart.checkout'))

        order.razorpay_order_id = rzp_order['id']
        db.session.commit()

        # Store order reference in server-side session — NOT in the HTML form.
        # This prevents a client from substituting a different order_id.
        session['pending_order_id']    = order.id
        session['pending_rzp_order_id'] = rzp_order['id']

        return render_template('shop/razorpay_checkout.html',
                               order=order, rzp_order=rzp_order, rzp_key=key_id)

    return render_template('shop/checkout.html',
                           items=items, subtotal=subtotal,
                           delivery=delivery, coupon_discount=coupon_discount,
                           grand_total=grand_total, addresses=addresses,
                           razorpay_enabled=rzp_enabled, cod_enabled=cod_on)


# ── Payment verification ──────────────────────────────────────────────────────

@cart_bp.route('/order/verify', methods=['POST'])
@login_required
def verify_payment():
    # Read order reference from session, never from the form.
    order_id         = session.get('pending_order_id')
    expected_rzp_id  = session.get('pending_rzp_order_id')

    if not order_id or not expected_rzp_id:
        flash('Payment session expired. Please place your order again.', 'danger')
        return redirect(url_for('cart.checkout'))

    # Ownership check — the order must belong to the logged-in user
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first()
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('cart.checkout'))

    # Idempotency — don't process an already-confirmed payment twice
    if order.payment_status == 'Paid':
        return redirect(url_for('cart.order_success', order_id=order.id))

    rzp_payment_id = request.form.get('razorpay_payment_id', '').strip()
    rzp_order_id   = request.form.get('razorpay_order_id',   '').strip()
    rzp_signature  = request.form.get('razorpay_signature',  '').strip()

    # Cross-check the Razorpay order ID from the form against the session value
    if rzp_order_id != expected_rzp_id:
        order.status         = 'Failed'
        order.payment_status = 'Failed'
        db.session.commit()
        flash('Payment verification failed: order mismatch. Contact support.', 'danger')
        return redirect(url_for('cart.checkout'))

    client, _ = get_razorpay_client()
    if not client:
        flash('Payment gateway unavailable. Contact support with your order number.', 'danger')
        return redirect(url_for('cart.checkout'))

    # Verify HMAC signature issued by Razorpay
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id':   rzp_order_id,
            'razorpay_payment_id': rzp_payment_id,
            'razorpay_signature':  rzp_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        order.status         = 'Failed'
        order.payment_status = 'Failed'
        db.session.commit()
        session.pop('pending_order_id',     None)
        session.pop('pending_rzp_order_id', None)
        flash('Payment signature invalid. If money was deducted, '
              f'contact support with order #{order.order_number}.', 'danger')
        return redirect(url_for('cart.checkout'))
    except Exception:
        flash('An unexpected error occurred. Contact support with your order number.', 'danger')
        return redirect(url_for('cart.checkout'))

    # ── All checks passed — confirm the order ────────────────────────────────
    order.status              = 'Confirmed'
    order.payment_status      = 'Paid'
    order.razorpay_payment_id = rzp_payment_id

    for item in order.items:
        item.product.stock = max(0, item.product.stock - item.quantity)

    if order.coupon_code:
        c = Coupon.query.filter_by(code=order.coupon_code).first()
        if c:
            c.used_count += 1

    db.session.commit()
    _clear_checkout_session()

    flash('Payment successful! Your order has been confirmed.', 'success')
    return redirect(url_for('cart.order_success', order_id=order.id))


# ── Razorpay webhook (async payment events) ───────────────────────────────────

@cart_bp.route('/payment/webhook', methods=['POST'])
def razorpay_webhook():
    """
    Handles async events from Razorpay (e.g. payment.captured for net-banking
    which may complete after the user leaves the browser).
    Configure this URL in Razorpay Dashboard → Webhooks.
    """
    webhook_secret = (os.environ.get('RAZORPAY_WEBHOOK_SECRET')
                      or get_setting('razorpay_webhook_secret'))
    if not webhook_secret:
        abort(400)

    raw_body  = request.get_data()
    signature = request.headers.get('X-Razorpay-Signature', '')

    expected = hmac.new(
        webhook_secret.encode('utf-8'), raw_body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        abort(400)

    event = request.get_json(silent=True) or {}

    if event.get('event') == 'payment.captured':
        payment_entity = (event.get('payload', {})
                              .get('payment', {})
                              .get('entity', {}))
        rzp_order_id   = payment_entity.get('order_id')
        rzp_payment_id = payment_entity.get('id')

        if rzp_order_id:
            order = Order.query.filter_by(razorpay_order_id=rzp_order_id).first()
            if order and order.payment_status != 'Paid':
                order.status              = 'Confirmed'
                order.payment_status      = 'Paid'
                order.razorpay_payment_id = rzp_payment_id
                for item in order.items:
                    item.product.stock = max(0, item.product.stock - item.quantity)
                if order.coupon_code:
                    c = Coupon.query.filter_by(code=order.coupon_code).first()
                    if c:
                        c.used_count += 1
                db.session.commit()

    return jsonify({'status': 'ok'}), 200


# ── Order success ─────────────────────────────────────────────────────────────

@cart_bp.route('/order/success/<int:order_id>')
@login_required
def order_success(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    return render_template('shop/order_success.html', order=order)
