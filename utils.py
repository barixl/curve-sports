import random
import string
from datetime import datetime, timedelta
from flask_mail import Message
from extensions import mail, db

def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))

def send_otp_email(email, otp, type='verification'):
    subject = ""
    body = ""
    
    if type == 'verification':
        subject = "Verify your account - Curve Sports"
        body = f"Your OTP for account verification is: {otp}. It is valid for 10 minutes."
    elif type == 'password_change':
        subject = "Password Change Request - Curve Sports"
        body = f"Your OTP for password change is: {otp}. It is valid for 10 minutes."
    
    msg = Message(subject, recipients=[email])
    msg.body = body
    try:
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def verify_otp(user, otp_input):
    if not user.otp or not user.otp_expiry:
        return False, "No OTP generated."
    
    if datetime.utcnow() > user.otp_expiry:
        return False, "OTP has expired."
    
    if user.otp != otp_input:
        return False, "Invalid OTP."
    
    return True, "OTP verified."
