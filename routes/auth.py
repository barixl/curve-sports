from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from extensions import db, oauth
from models import User
from utils import generate_otp, send_otp_email, verify_otp
from datetime import datetime, timedelta

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
            if not user.email_verified:
                flash('Please verify your email address before logging in.', 'warning')
                session['verify_email'] = user.email
                return redirect(url_for('auth.verify_email_otp'))
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(next_page or url_for('shop.index'))
        flash('Invalid email or password.', 'danger')
    return render_template('auth/login.html')
    

# --- Google OAuth Routes ---

@auth_bp.route('/login/google')
def google_login():
    redirect_uri = url_for('auth.google_authorize', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route('/authorize/google')
def google_authorize():
    token = oauth.google.authorize_access_token()
    user_info = token.get('userinfo')
    if not user_info:
        flash('Failed to get user info from Google.', 'danger')
        return redirect(url_for('auth.login'))
    
    email = user_info['email'].lower()
    google_id = user_info['sub']
    name = user_info.get('name', email.split('@')[0])
    
    user = User.query.filter((User.email == email) | (User.google_id == google_id)).first()
    
    if not user:
        # Create new user if not exists
        user = User(
            name=name,
            email=email,
            google_id=google_id,
            email_verified=True, # Google accounts are already verified
            is_active=True
        )
        db.session.add(user)
        db.session.commit()
    else:
        # Update google_id if not already set
        if not user.google_id:
            user.google_id = google_id
            user.email_verified = True
            db.session.commit()

    if not user.is_active:
        flash('Your account has been deactivated.', 'danger')
        return redirect(url_for('auth.login'))

    login_user(user)
    flash(f'Logged in with Google! Welcome, {user.name}!', 'success')
    return redirect(url_for('shop.index'))


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
        
        # Create user but mark as not verified
        user = User(name=name, email=email, phone=phone,
                    password=generate_password_hash(password),
                    email_verified=False)
        
        # Generate and send OTP
        otp = generate_otp()
        user.otp = otp
        user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
        
        db.session.add(user)
        db.session.commit()
        
        if send_otp_email(email, otp, type='verification'):
            session['verify_email'] = email
            flash('A verification OTP has been sent to your email.', 'info')
            return redirect(url_for('auth.verify_email_otp'))
        else:
            flash('Failed to send OTP. Please try again later.', 'danger')
            return render_template('auth/register.html')
            
    return render_template('auth/register.html')


@auth_bp.route('/verify-email', methods=['GET', 'POST'])
def verify_email_otp():
    email = session.get('verify_email')
    if not email:
        return redirect(url_for('auth.register'))
    
    if request.method == 'POST':
        otp_input = request.form.get('otp')
        user = User.query.filter_by(email=email).first()
        
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('auth.register'))
        
        success, message = verify_otp(user, otp_input)
        if success:
            user.email_verified = True
            user.otp = None
            user.otp_expiry = None
            db.session.commit()
            login_user(user)
            session.pop('verify_email', None)
            flash('Email verified! Registration successful.', 'success')
            return redirect(url_for('shop.index'))
        else:
            flash(message, 'danger')
            
    return render_template('auth/verify_otp.html', email=email, type='verification')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            otp = generate_otp()
            user.otp = otp
            user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
            db.session.commit()
            
            if send_otp_email(email, otp, type='password_change'):
                session['reset_email'] = email
                flash('An OTP for password reset has been sent to your email.', 'info')
                return redirect(url_for('auth.reset_password_otp'))
            else:
                flash('Failed to send OTP.', 'danger')
        else:
            flash('Email address not found.', 'danger')
            
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password_otp():
    email = session.get('reset_email')
    if not email:
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        otp_input = request.form.get('otp')
        new_password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html')
            
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('auth.forgot_password'))
            
        success, message = verify_otp(user, otp_input)
        if success:
            user.password = generate_password_hash(new_password)
            user.otp = None
            user.otp_expiry = None
            db.session.commit()
            session.pop('reset_email', None)
            flash('Password has been reset successfully. Please login.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash(message, 'danger')
            
    return render_template('auth/reset_password.html', email=email)


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
