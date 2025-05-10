from flask import Flask, render_template, url_for, redirect, flash, session
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField
from wtforms.validators import InputRequired, Length, ValidationError, Email, EqualTo
from flask_bcrypt import Bcrypt
from tinydb import TinyDB, Query
import os
from dotenv import load_dotenv
import yagmail
import random
import string
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

db = TinyDB("user.json")
users_table = db.table("users")
verification_codes_table = db.table("verification_codes")
password_reset_codes_table = db.table("password_reset_codes")

bcrypt = Bcrypt(app)
yag = yagmail.SMTP(user=os.getenv("EMAIL_USERNAME"), password=os.getenv("EMAIL_PASSWORD"))

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "email"

class UserClass(UserMixin):
    def __init__(self, user_id, username, email, password, gender, verified=False):
        self.id = user_id
        self.username = username
        self.email = email
        self.password = password
        self.gender = gender
        self.verified = verified

@login_manager.user_loader
def load_user(user_id):
    user_data = users_table.get(doc_id=int(user_id))
    if user_data:
        return UserClass(user_data.doc_id, user_data["username"],
                         user_data["email"], user_data["password"],
                         user_data["gender"], user_data.get("verified", False))
    return None

def generate_verification_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def send_verification_email(email, code):
    try:
        contents = f"""
      <!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verification Code</title>
</head>
<body style="font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f5f7fa; color: #333333; margin: 0; padding: 0; line-height: 1.6;">

<div style="max-width: 600px; margin: 20px auto; padding: 0; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08); overflow: hidden;">
    <div style="background-color: #4F46E5; padding: 30px 20px; text-align: center; color: white;">
        <h1 style="font-size: 24px; font-weight: 600; margin: 0; letter-spacing: 0.5px;">Your Verification Code</h1>
    </div>
    
    <div style="padding: 30px;">
        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">Hello,</p>
        
        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">Thank you for joining <span style="color: #4F46E5; font-weight: 600;">Too Fast For you</span>! To complete your registration, please use the following verification code:</p>
        
        <div style="background-color: #f8f9fc; border-left: 4px solid #4F46E5; padding: 15px; margin: 25px 0; text-align: center; font-size: 24px; font-weight: 700; color: #1a237e; letter-spacing: 2px;">
            {code}
        </div>
        
        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">For security reasons, this code will expire in <strong>15 minutes</strong>. Please do not share this code with anyone.</p>
        
        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">If you didn't request this code, you can safely ignore this email or contact our support team if you have any concerns.</p>
    </div>
    
    <div style="padding: 20px; text-align: center; font-size: 14px; color: #718096; background-color: #f8f9fc; border-top: 1px solid #e2e8f0;">
        <p style="margin: 5px 0;">Best regards,</p>
        <p style="margin: 5px 0;">The <span style="color: #4F46E5; font-weight: 600;">Too Fast For you</span> Team</p>
        <p style="margin: 15px 0 0 0; font-size: 12px;">
            © 2025 2f4y. All rights reserved.
        </p>
    </div>
</div>

</body>
</html>
        """

        yag.send(to=email, subject="Email Verification Code", contents=contents)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_password_reset_code(email, code):
    try:
        contents = [
            "Password Reset Request "
            f"Your password reset code is: <strong>{code}</strong> "
            "Code expires in 15 minutes."
        ]
        yag.send(to=email, subject="Password Reset Code", contents=contents)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

class EmailVerificationForm(FlaskForm):
    email = StringField(validators=[InputRequired(), Email()], render_kw={"placeholder": "Email"})
    submit = SubmitField("Continue")

    def validate_email(self, email):
        User = Query()
        if users_table.contains(User.email == email.data):
            raise ValidationError("Email already used")

class VerificationCodeForm(FlaskForm):
    code = StringField(validators=[InputRequired(), Length(min=6, max=6)], render_kw={"placeholder": "Verification Code"})
    submit = SubmitField("Verify")

class SignupForm(FlaskForm):
    username = StringField(validators=[InputRequired(), Length(min=4, max=20)], render_kw={"placeholder": "Username"})
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)], render_kw={"placeholder": "Password"})
    confirm_password = PasswordField(validators=[InputRequired(), EqualTo('password', message="Passwords must match")], render_kw={"placeholder": "Confirm Password"})
    gender = SelectField(choices=[('male', 'Male'), ('female', 'Female')], validators=[InputRequired()])
    submit = SubmitField("Signup")

    def validate_username(self, username):
        User = Query()
        if users_table.contains(User.username == username.data):
            raise ValidationError("Username already taken")

class LoginForm(FlaskForm):
    username_or_email = StringField(validators=[InputRequired()], render_kw={"placeholder": "Username or Email"})
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)], render_kw={"placeholder": "Password"})
    submit = SubmitField("Login")

class ResetPasswordRequestForm(FlaskForm):
    email = StringField(validators=[InputRequired(), Email()], render_kw={"placeholder": "Email"})
    submit = SubmitField("Request code")

class ResetCodeForm(FlaskForm):
    code = StringField(validators=[InputRequired(), Length(min=6, max=6)], render_kw={"placeholder": "Reset Code"})
    submit = SubmitField("Verify Code")

class NewPasswordForm(FlaskForm):
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)], render_kw={"placeholder": "New Password"})
    confirm_password = PasswordField(validators=[InputRequired(), EqualTo('password', message="Passwords must match")], render_kw={"placeholder": "Confirm New Password"})
    submit = SubmitField("Set New Password")

    def validate_password(self, password):
        User = Query()
        user_data = users_table.get(User.email == session["reset_email"])
        if user_data and bcrypt.check_password_hash(user_data["password"], password.data):
            raise ValidationError("New password must be different from current password")

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/email-verification", methods=["GET", "POST"])
def email():
    form = EmailVerificationForm()
    if form.validate_on_submit():
        verification_code = generate_verification_code()
        if send_verification_email(form.email.data, verification_code):
            verification_codes_table.insert({
                "email": form.email.data,
                "code": verification_code,
                "created_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(minutes=15)).isoformat()
            })
            session["email"] = form.email.data
            return redirect(url_for("verify_code"))
        else:
            flash("Failed to send verification email. Please try again.")
    return render_template("email.html", form=form)

@app.route("/verify-code", methods=["GET", "POST"])
def verify_code():
    if "email" not in session:
        return redirect(url_for("email"))
    form = VerificationCodeForm()
    if form.validate_on_submit():
        Verification = Query()
        code_record = verification_codes_table.get((Verification.email == session["email"]) & (Verification.code == form.code.data.upper()))
        if code_record:
            expires_at = datetime.fromisoformat(code_record["expires_at"])
            if datetime.now() < expires_at:
                session["email_verified"] = True
                return redirect(url_for("signup"))
            else:
                flash("Verification code has expired. Please request a new one.")
        else:
            flash("Invalid verification code. Please try again.")
    return render_template("verify_code.html", form=form)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "email" not in session or not session.get("email_verified"):
        return redirect(url_for("email"))
    form = SignupForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        user_id = users_table.insert({
            "username": form.username.data,
            "email": session["email"],
            "password": hashed_password,
            "gender": form.gender.data,
            "verified": True
        })
        user = UserClass(user_id, form.username.data, session["email"], hashed_password, form.gender.data, True)
        login_user(user)
        session.pop("email", None)
        session.pop("email_verified", None)
        Verification = Query()
        verification_codes_table.remove(Verification.email == user.email)
        return redirect(url_for("dashboard"))
    return render_template("signup.html", form=form)

@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        User = Query()
        user_data = users_table.get(User.email == form.username_or_email.data)
        if not user_data:
            user_data = users_table.get(User.username == form.username_or_email.data)
        if user_data and bcrypt.check_password_hash(user_data["password"], form.password.data):
            if not user_data.get("verified", False):
                flash("Please verify your email first. Check your inbox.")
                return redirect(url_for("email"))
            user = UserClass(user_data.doc_id, user_data["username"], user_data["email"], user_data["password"], user_data["gender"], user_data.get("verified", False))
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid username/email or password")
    return render_template("login.html", form=form)

@app.route("/reset-password-request", methods=["GET", "POST"])
def reset_password_request():
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        User = Query()
        user_data = users_table.get(User.email == form.email.data)
        if user_data:
            reset_code = generate_verification_code()
            password_reset_codes_table.insert({
                "email": form.email.data,
                "code": reset_code,
                "created_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(minutes=15)).isoformat()
            })
            if send_password_reset_code(form.email.data, reset_code):
                session["reset_email"] = form.email.data
                flash("Check your email for the password reset code")
                return redirect(url_for("reset_code"))
            else:
                flash("Error sending password reset code. Please try again.")
        else:
            flash("If the email exists, you'll receive a password reset code.")
            return redirect(url_for("login"))
    return render_template("reset_password_request.html", form=form)

@app.route("/reset-password-code", methods=["GET", "POST"])
def reset_code():
    if "reset_email" not in session:
        return redirect(url_for("reset_password_request"))
    form = ResetCodeForm()
    if form.validate_on_submit():
        ResetCode = Query()
        code_record = password_reset_codes_table.get((ResetCode.email == session["reset_email"]) & (ResetCode.code == form.code.data.upper()))
        if code_record:
            expires_at = datetime.fromisoformat(code_record["expires_at"])
            if datetime.now() < expires_at:
                session["code_verified"] = True
                return redirect(url_for("set_new_password"))
            else:
                flash("Code expired. Please request a new one.")
        else:
            flash("Invalid code. Please try again.")
    return render_template("reset_code.html", form=form)

@app.route("/set-new-password", methods=["GET", "POST"])
def set_new_password():
    if not session.get("code_verified") or "reset_email" not in session:
        return redirect(url_for("reset_password_request"))
    form = NewPasswordForm()
    if form.validate_on_submit():
        User = Query()
        user_data = users_table.get(User.email == session["reset_email"])
        if user_data:
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
            users_table.update({"password": hashed_password}, doc_ids=[user_data.doc_id])
            ResetCode = Query()
            password_reset_codes_table.remove(ResetCode.email == session["reset_email"])
            session.pop("reset_email", None)
            session.pop("code_verified", None)
            flash("Password updated. You can log in now.")
            return redirect(url_for("login"))
        else:
            flash("User not found.")
    return render_template("set_new_password.html", form=form)

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", username=current_user.username, gender=current_user.gender)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)