from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from extensions import db
from models import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('shop.index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated.', 'danger')
                return redirect(url_for('auth.login'))
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(next_page or url_for('shop.index'))
        flash('Invalid email or password.', 'danger')
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('shop.index'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if not all([name, email, password]):
            flash('Please fill all required fields.', 'danger')
            return render_template('auth/register.html')
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('auth/register.html')
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('auth/register.html')
        user = User(name=name, email=email, phone=phone,
                    password=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Registration successful! Welcome to Nutrabay.', 'success')
        return redirect(url_for('shop.index'))
    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('shop.index'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    from models import Order, Address
    if request.method == 'POST':
        current_user.name = request.form.get('name', current_user.name).strip()
        current_user.phone = request.form.get('phone', current_user.phone).strip()
        new_pass = request.form.get('new_password', '')
        if new_pass:
            if not current_user.check_password(request.form.get('current_password', '')):
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for('auth.profile'))
            current_user.password = generate_password_hash(new_pass)
        db.session.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('auth.profile'))
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    addresses = Address.query.filter_by(user_id=current_user.id).all()
    return render_template('auth/profile.html', orders=orders, addresses=addresses)


@auth_bp.route('/address/add', methods=['POST'])
@login_required
def add_address():
    from models import Address
    addr = Address(
        user_id=current_user.id,
        full_name=request.form.get('full_name'),
        phone=request.form.get('phone'),
        address_line1=request.form.get('address_line1'),
        address_line2=request.form.get('address_line2', ''),
        city=request.form.get('city'),
        state=request.form.get('state'),
        pincode=request.form.get('pincode'),
        is_default=request.form.get('is_default') == 'on'
    )
    if addr.is_default:
        Address.query.filter_by(user_id=current_user.id).update({'is_default': False})
    db.session.add(addr)
    db.session.commit()
    flash('Address added.', 'success')
    return redirect(url_for('auth.profile'))


@auth_bp.route('/address/delete/<int:id>')
@login_required
def delete_address(id):
    from models import Address
    addr = Address.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(addr)
    db.session.commit()
    flash('Address removed.', 'success')
    return redirect(url_for('auth.profile'))
