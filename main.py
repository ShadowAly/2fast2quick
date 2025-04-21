from flask import Flask, render_template, url_for, redirect, flash, session, request
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import InputRequired, Length, ValidationError, Email
from flask_bcrypt import Bcrypt
from tinydb import TinyDB, Query
import os
from dotenv import load_dotenv
import yagmail
import random
import string
from datetime import datetime, timedelta
import secrets

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

db = TinyDB("user.json")
users_table = db.table("users")
verification_codes_table = db.table("verification_codes")
password_reset_tokens_table = db.table("password_reset_tokens")

bcrypt = Bcrypt(app)

yag = yagmail.SMTP(user=os.getenv("EMAIL_USERNAME"), password=os.getenv("EMAIL_PASSWORD"))

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "email"

class UserClass(UserMixin):
    def __init__(self, user_id, username, email, password, verified=False):
        self.id = user_id
        self.username = username
        self.email = email
        self.password = password
        self.verified = verified

@login_manager.user_loader
def load_user(user_id):
    user_data = users_table.get(doc_id=int(user_id))
    if user_data:
        return UserClass(user_data.doc_id, user_data["username"], 
                         user_data["email"], user_data["password"],
                         user_data.get("verified", False))
    return None

def generate_verification_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def generate_reset_token():
    return secrets.token_urlsafe(32)

def send_verification_email(email, code):
    try:
        contents = [
            "Welcome to 2f4y "
            f"Your verification code is: <strong>{code}</strong> "
            "Code expires in 15 minutes."
        ]
        yag.send(
            to=email,
            subject="Your Email Verification Code",
            contents=contents
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_password_reset_email(email, token):
    try:
        reset_url = url_for('reset_password', token=token, _external=True)
        contents = [
            "To reset your password, click the following link: "
            f"<a href='{reset_url}'>{reset_url}</a> "
            "This link will expire in 1 hour."
        ]
        yag.send(
            to=email,
            subject="Password Reset Request",
            contents=contents
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

class EmailVerificationForm(FlaskForm):
    email = StringField(validators=[InputRequired(), Email()],
                        render_kw={"placeholder": "Email"})
    submit = SubmitField("Continue")

    def validate_email(self, email):
        User = Query()
        if users_table.contains(User.email == email.data):
            raise ValidationError("Email already used")

class VerificationCodeForm(FlaskForm):
    code = StringField(validators=[InputRequired(), Length(min=6, max=6)],
                       render_kw={"placeholder": "Verification Code"})
    submit = SubmitField("Verify")

class SignupForm(FlaskForm):
    username = StringField(validators=[InputRequired(), Length(min=4, max=20)],
                           render_kw={"placeholder": "Username"})
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)],
                             render_kw={"placeholder": "Password"})
    submit = SubmitField("Signup")

    def validate_username(self, username):
        User = Query()
        if users_table.contains(User.username == username.data):
            raise ValidationError("Username already taken")

class LoginForm(FlaskForm):
    username_or_email = StringField(validators=[InputRequired()],
                                    render_kw={"placeholder": "Username or Email"})
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)],
                             render_kw={"placeholder": "Password"})
    submit = SubmitField("Login")

class ResetPasswordRequestForm(FlaskForm):
    email = StringField(validators=[InputRequired(), Email()],
                        render_kw={"placeholder": "Email"})
    submit = SubmitField("Request Password Reset")

class ResetPasswordForm(FlaskForm):
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)],
                             render_kw={"placeholder": "New Password"})
    confirm_password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)],
                                     render_kw={"placeholder": "Confirm New Password"})
    submit = SubmitField("Reset Password")

    def validate_confirm_password(self, confirm_password):
        if self.password.data != confirm_password.data:
            raise ValidationError("Passwords must match")

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
        code_record = verification_codes_table.get(
            (Verification.email == session["email"]) & 
            (Verification.code == form.code.data.upper()))
        
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
            "verified": True
        })
        user = UserClass(user_id, form.username.data, session["email"], hashed_password, True)
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
            
            user = UserClass(user_data.doc_id, user_data["username"], 
                             user_data["email"], user_data["password"], user_data.get("verified", False))
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
            token = generate_reset_token()
            password_reset_tokens_table.insert({
                "email": form.email.data,
                "token": token,
                "created_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(hours=1)).isoformat()
            })
            if send_password_reset_email(form.email.data, token):
                flash("Check your email to reset your password")
                return redirect(url_for("login"))
            else:
                flash("Error sending password reset email. Please try again.")
        else:
            flash("You will receive a password reset link.")
            return redirect(url_for("login"))
    return render_template("reset_password_request.html", form=form)

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    Token = Query()
    token_record = password_reset_tokens_table.get(Token.token == token)
    
    if not token_record:
        flash("Invalid or expired password reset link")
        return redirect(url_for("reset_password_request"))
    
    expires_at = datetime.fromisoformat(token_record["expires_at"])
    if datetime.now() > expires_at:
        password_reset_tokens_table.remove(Token.token == token)
        flash("Password reset link has expired")
        return redirect(url_for("reset_password_request"))
    
    form = ResetPasswordForm()
    if form.validate_on_submit():
        User = Query()
        user_data = users_table.get(User.email == token_record["email"])
        if user_data:
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
            users_table.update({"password": hashed_password}, doc_ids=[user_data.doc_id])
            password_reset_tokens_table.remove(Token.token == token)
            flash("Your password has been updated!")
            return redirect(url_for("login"))
        else:
            flash("User not found")
            return redirect(url_for("reset_password_request"))
    
    return render_template("reset_password.html", form=form)

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", username=current_user.username)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)