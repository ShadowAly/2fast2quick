from flask import Flask, render_template, url_for, redirect, flash, session
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import InputRequired, Length, ValidationError, Email
from flask_bcrypt import Bcrypt
from tinydb import TinyDB, Query
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()

db = TinyDB("user.json")
users_table = db.table("users")

bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "email"

class UserClass(UserMixin):
    def __init__(self, user_id, username, email, password):
        self.id = user_id
        self.username = username
        self.email = email
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    user_data = users_table.get(doc_id=int(user_id))
    if user_data:
        return UserClass(user_data.doc_id, user_data["username"], 
                        user_data["email"], user_data["password"])
    return None

class EmailVerificationForm(FlaskForm):
    email = StringField(validators=[InputRequired(), Email()],
                      render_kw={"placeholder": "Email"})
    submit = SubmitField("Continue")

    def validate_email(self, email):
        User = Query()
        if users_table.contains(User.email == email.data):
            raise ValidationError("Email already used")

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

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/email-verification", methods=["GET", "POST"])
def email():
    form = EmailVerificationForm()
    if form.validate_on_submit():
        session['email'] = form.email.data
        return redirect(url_for("Signup"))
    return render_template("email.html", form=form)

@app.route("/signup", methods=["GET", "POST"])
def Signup():
    if 'email' not in session:
        return redirect(url_for("email"))
    
    form = SignupForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        user_id = users_table.insert({
            "username": form.username.data,
            "email": session['email'],
            "password": hashed_password
        })
        user = UserClass(user_id, form.username.data, session['email'], hashed_password)
        login_user(user)
        session.pop('email', None)
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
            user = UserClass(user_data.doc_id, user_data["username"], 
                           user_data["email"], user_data["password"])
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid username/email or password")
    return render_template("login.html", form=form)

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html",
                         username=current_user.username,
                         email=current_user.email)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)