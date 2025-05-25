# ================================================================================================================================
# Main.py
# 
# 
# 
# 
# ================================================================================================================================


# --------------------------------------------------------------------------------------------------------------------------------
# Uvozi knjižence
# --------------------------------------------------------------------------------------------------------------------------------

import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField
from wtforms.validators import InputRequired, Length, ValidationError, Email, EqualTo
from flask_bcrypt import Bcrypt
from tinydb import TinyDB, Query
import yagmail
import random
import string
from dotenv import load_dotenv
import stripe
load_dotenv() # <- Naloži .env datoteko


# --------------------------------------------------------------------------------------------------------------------------------
# Glavne spremenljivke in drugo... I guess?
# --------------------------------------------------------------------------------------------------------------------------------

# Ustvari instanco Flaska in nastavi SECRET_KEY za zaščito sej.
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

# Secret key za stripe API (za obdelavo plačil itd...).
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


# Domena aplikacije (npr. za redirect).
YOUR_DOMAIN = os.getenv("DOMAIN")

# Dictionary za stripe ID-je cen za vse plane.
PRICES = {
    "normal": os.getenv("STRIPE_NORMAL_PRICE_ID"),
    "premium": os.getenv("STRIPE_PREMIUM_PRICE_ID")
}


# Ustvari TinyDB database, kjer se bodo shranjevali uporabnikovi podatki v datoteki 'user.json'.
# Prav tako pa ustvari tudi vse tabele itd...
db = TinyDB("user.json")
users_table = db.table("users")
verification_codes_table = db.table("verification_codes")
password_reset_codes_table = db.table("password_reset_codes")
games_table = db.table("games")
servers_table = db.table("servers")

# Bcrypt za enkripcijo/šifriranje gesel in yagmail za pošiljanje e-pošte do uporabnika (npr. password reset).
bcrypt = Bcrypt(app)
yag = yagmail.SMTP(user=os.getenv("EMAIL_USERNAME"), password=os.getenv("EMAIL_PASSWORD"))

# Ustvari sistem za user login (flask login).
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "email"


# --------------------------------------------------------------------------------------------------------------------------------
# K O D A ( ͡° ͜ʖ ͡°)
# --------------------------------------------------------------------------------------------------------------------------------

# Definiraj user class za flask login (UserClass predstavlja uporabnika).
class UserClass(UserMixin):
    def __init__(self, user_id, username, email, password, gender, verified=False, plan="free"):    
        # Lastnosti računa uporabnika
        self.id = user_id
        self.username = username
        self.email = email
        self.password = password
        self.gender = gender
        self.verified = verified    # <- Pove ali je user potrjen / je potrdil email...
        self.plan = plan            # <- Pove kateri plan/naročnino ima user.

    # Čekiri ali uporabnik lahko ustvari nov game server.
    def can_create_server(self):
        # Admin ima vedno dovoljenje za ustvarjanje serverjev, zato returni true.
        if self.username == "Admin":
            return True
        
        # User z free planom ne more ustvariti serverja, zato returni false.
        if self.plan == "free":
            return False
        
        # GET ALL THE SERVERS OR ELSE I USE THIS HAMMER TO BREAK EVERYTHING IN MY STUDIO!!!
        # Vsi serverji k jih je ustvaril uporabnik.
        user_servers = servers_table.search(Query().created_by == self.username)

        # Določi največje število serverjev glede na plan/naročnino.
        max_servers = 3 if self.plan == "normal" else 10

        # Returni true, če uporabnik še ni dosegel omejitve, če ne pa false .
        return len(user_servers) < max_servers


# Funkcija za nalaganje uporabnika iz ID-ja.
@login_manager.user_loader
def load_user(user_id):
    # Pridobi vse podatke o uporabniku po njegovem ID-ju.
    user_data = users_table.get(doc_id=int(user_id))

    # Če uporabnik obstaja, ustvari in returni 'UserClass'...
    if user_data:
        return UserClass(
            user_data.doc_id,
            user_data["username"],
            user_data["email"],
            user_data["password"],
            user_data["gender"],
            user_data.get("verified", False),
            user_data.get("plan", "free")
        )
    
    # ...sicer pa returni none.
    return None


# Funkcija za generiranje random kode za potrditev. To kodo bomo nato poslali uporabniku na email :D
def generate_verification_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


# Pošlji verification email z generirano kodo.
def send_verification_email(email, code):
    try:
        # HTML koda za email
        contents = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Verification Code</title>
    </head>
    <body style="font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f5f7fa; color: #333333; margin: 0; padding: 0; line-height: 1.6;">

    <div style="max-width: 600px; margin: 20px auto; padding: 0; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08); overflow: hidden;">

        <div style="background-color: #3b82f6; padding: 30px 20px; text-align: center; color: #ffffff;">
        <h1 style="font-size: 24px; font-weight: 600; margin: 0; letter-spacing: 0.5px;">Your Verification Code</h1>
        </div>

        <div style="padding: 30px;">
        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">Hello,</p>

        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">
            Thank you for joining
            <span style="color: #3b82f6; font-weight: 600;">Too Fast For you</span>! To complete your registration, please use the following verification code:
        </p>

        <div style="background-color: #f8f9fc; border-left: 4px solid #ef4444; padding: 15px; margin: 25px 0; text-align: center; font-size: 24px; font-weight: 700; color: #ef4444; letter-spacing: 2px;">
            {code}
        </div>

        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">
            For security reasons, this code will expire in <strong>15 minutes</strong>. Please do not share this code with anyone.
        </p>

        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">
            If you didn't request this code, you can safely ignore this email or contact our support team if you have any questions.
        </p>
        </div>

        <div style="padding: 20px; text-align: center; font-size: 14px; color: #718096; background-color: #f8f9fc; border-top: 1px solid #e2e8f0;">
        <p style="margin: 5px 0;">Best regards,</p>
        <p style="margin: 5px 0;">The <span style="color: #3b82f6; font-weight: 600;">Too Fast For you</span> Team</p>
        <p style="margin: 15px 0 0 0; font-size: 12px;">
            © 2025 2F4Y. All rights reserved.
        </p>
        </div>

    </div>

    </body>
    </html>
    """
        # Pošlji email preko yagmail.
        yag.send(to=email, subject="Email Verification Code", contents=contents)
        return True
    
    # V primeru napake jo printej pa returni false. Upajmo da ne pride do tega (x_x)...
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


# Pošlji generirano kodo za nastavitev novega gesla prek emaila :D
def send_password_reset_code(email, code):
    try:
        contents = f"""

    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Password Reset Request</title>
    </head>
    <body style="font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f5f7fa; color: #333333; margin: 0; padding: 0; line-height: 1.6;">

    <div style="max-width: 600px; margin: 20px auto; padding: 0; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08); overflow: hidden;">

        <div style="background-color: #3b82f6; padding: 30px 20px; text-align: center; color: #ffffff;">
        <h1 style="font-size: 24px; font-weight: 600; margin: 0; letter-spacing: 0.5px;">Password Reset Request</h1>
        </div>

        <div style="padding: 30px;">
        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">Hello,</p>

        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">
            We received a request to reset the password for your account associated with <span style="color: #3b82f6; font-weight: 600;">Too Fast For you</span>.
        </p>

        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">
            Your password reset code is:
        </p>

        <div style="background-color: #f8f9fc; border-left: 4px solid #ef4444; padding: 15px; margin: 25px 0; text-align: center; font-size: 24px; font-weight: 700; color: #ef4444; letter-spacing: 2px;">
            {code}
        </div>

        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">
            Please use this code to reset your password. <strong>The code expires in 15 minutes</strong> for your security.
        </p>

        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">
            If you did not request a password reset, please ignore this email or contact our support team if you have any concerns.
        </p>

        <p style="margin-bottom: 20px; font-size: 16px; color: #4a5568;">
            For your safety, do not share this code with anyone.
        </p>
        </div>

        <div style="padding: 20px; text-align: center; font-size: 14px; color: #718096; background-color: #f8f9fc; border-top: 1px solid #e2e8f0;">
        <p style="margin: 5px 0;">Best regards,</p>
        <p style="margin: 5px 0;">The <span style="color: #3b82f6; font-weight: 600;">Too Fast For you</span> Team</p>
        <p style="margin: 15px 0 0 0; font-size: 12px;">
            © 2025 2F4Y. All rights reserved.
        </p>
        </div>

    </div>

    </body>
    </html>
     """

        # Kot prej, pošlji kodo prek yagmail...
        yag.send(to=email, subject="Password Reset Code", contents=contents)
        return True
    
    # ... in spet printi napako in vrni false v primeru da gre karkol narobe.
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


# --------------------------------------------------------------------------------------------------------------------------------
# Obrazci
# --------------------------------------------------------------------------------------------------------------------------------

# Obrazec za vnos email-a pri ustvarjanju računa.
class EmailVerificationForm(FlaskForm):
    email = StringField(validators=[InputRequired(), Email()], render_kw={"placeholder": "Email"})
    submit = SubmitField("Continue")

    # Čekirej če je email veljaven.
    def validate_email(self, email):
        User = Query()
        if users_table.contains(User.email == email.data):
            raise ValidationError("Email already used")


# Obrazec za vnos verifikacijske kode.
class VerificationCodeForm(FlaskForm):
    code = StringField(validators=[InputRequired(), Length(min=6, max=6)], render_kw={"placeholder": "Verification Code"})
    submit = SubmitField("Verify")


# Obrazec za registracijo uporabnika.
class SignupForm(FlaskForm):
    username = StringField(validators=[InputRequired(), Length(min=4, max=20)], render_kw={"placeholder": "Username"})
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)], render_kw={"placeholder": "Password"})
    confirm_password = PasswordField(validators=[InputRequired(), EqualTo('password', message="Passwords must match")], render_kw={"placeholder": "Confirm Password"})
    gender = SelectField(choices=[('male', 'Male'), ('female', 'Female')], validators=[InputRequired()])
    submit = SubmitField("Signup")

    # Čekirej, če je uporabniško ime že zasedeno.
    def validate_username(self, username):
        User = Query()
        if users_table.contains(User.username == username.data):
            raise ValidationError("Username already taken")


# Obrazec za prijavo uporabnika.
class LoginForm(FlaskForm):
    username_or_email = StringField(validators=[InputRequired()], render_kw={"placeholder": "Username or Email"})
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)], render_kw={"placeholder": "Password"})
    submit = SubmitField("Login")


# Obrazec za spremembo gesla.
class ResetPasswordRequestForm(FlaskForm):
    email = StringField(validators=[InputRequired(), Email()], render_kw={"placeholder": "Email"})
    submit = SubmitField("Request code")


# Obrazec za vnos varnostne kode za spremembo gesla.
class ResetCodeForm(FlaskForm):
    code = StringField(validators=[InputRequired(), Length(min=6, max=6)], render_kw={"placeholder": "Reset Code"})
    submit = SubmitField("Verify Code")


# Obrazec za vnos novega gesla. Jz vem da ga bom pozabu k sm knedl...
class NewPasswordForm(FlaskForm):
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)], render_kw={"placeholder": "New Password"})
    confirm_password = PasswordField(validators=[InputRequired(), EqualTo('password', message="Passwords must match")], render_kw={"placeholder": "Confirm New Password"})
    submit = SubmitField("Set New Password")

    # Potrdi novo geslo...
    def validate_password(self, password):
        User = Query()
        user_data = users_table.get(User.email == session["reset_email"])
        if user_data and bcrypt.check_password_hash(user_data["password"], password.data):
            raise ValidationError("New password must be different from current password")


# Home page
@app.route("/")
def home():
    return render_template("home.html")


# --------------------------------------------------------------------------------------------------------------------------------
# Sign up / register
# --------------------------------------------------------------------------------------------------------------------------------

# Vnos email-a za začetek registracije.
@app.route("/email-verification", methods=["GET", "POST"])
def email():
    # Ustvari obrazec za vnos emaila.
    form = EmailVerificationForm()
    
    # Če je obrazec izpolnjen...
    if form.validate_on_submit():
        # ... ustvari verification kodo in jo pošlji na email.
        verification_code = generate_verification_code()
       
        # Shrani kodo v database, ki je veljavna 15 minut.
        if send_verification_email(form.email.data, verification_code):
            verification_codes_table.insert({
                "email": form.email.data,
                "code": verification_code,
                "created_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(minutes=15)).isoformat()
            })

            session["email"] = form.email.data      # <- Shrani email v sejo za naprej.
            return redirect(url_for("verify_code")) # <- Redirect na stran za vnos kode.
        else:
            # Če se email ni uspel poslat, povej uporabniku.
            flash("Failed to send verification email. Please try again.")

    # Prikaži obrazec za vnos emaila :D
    return render_template("email.html", form=form)


# Preveri potrditveno kodo.
@app.route("/verify-code", methods=["GET", "POST"])
def verify_code():
    # Če email ni shranjen, preusmeri nazaj na vnos emaila.
    if "email" not in session:
        return redirect(url_for("email"))
    
    # Obrazec za vnos verifikacijske kode.
    form = VerificationCodeForm()

    # Če je obrazec izpolnjen pravilno...
    if form.validate_on_submit():
        Verification = Query()

        # ...poišči kodo, ki ustreza vnešeni kodi in email naslov, ki smo ga shranili v seji.
        code_record = verification_codes_table.get((Verification.email == session["email"]) & (Verification.code == form.code.data.upper()))
        if code_record:
            # Čekiri če je koda še veljavna...
            expires_at = datetime.fromisoformat(code_record["expires_at"])
            if datetime.now() < expires_at:
                session["email_verified"] = True    # <- Označi, da je email kul.
                return redirect(url_for("signup"))  # <- Redirecti na registracijo :D
            else:
                # ... če ne uporabniku sporoči, da ni več veljavna.
                flash("Verification code has expired. Please request a new one.")
        else:
            # V primeru da se koda ne ujema, to sporoči uporabniku.
            flash("Invalid verification code. Please try again.")

    # Prikaži obrazec za vnos kode.
    return render_template("verify_code.html", form=form)


# Registracija novega uporabnika itd...
@app.route("/signup", methods=["GET", "POST"])
def signup():
    # Če email ni shranjen ali pa ni potrjen, preusmeri na začetek postopka.
    if "email" not in session or not session.get("email_verified"):
        return redirect(url_for("email"))
    
    # Obrazec za registracijo novega uporabinka.
    form = SignupForm()

    # Če je obrazec pravilno izpolnjen...
    if form.validate_on_submit():
        # ... "hashiraj" (??? idk xD) geslo uporabnika.
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        
        # Vstavi novega uporabnika v bazooooo. Welcome buddy :))))
        user_id = users_table.insert({
            "username": form.username.data,
            "email": session["email"],
            "password": hashed_password,
            "gender": form.gender.data,
            "verified": True,
            "plan": "free" # <- Default/privzeta vrednost.
        })

        # Avtomatično prijavi uporabnika po registraciji
        user = UserClass(user_id, form.username.data, session["email"], hashed_password, form.gender.data, True)
        login_user(user)

        # Odstrani spremenljivke trenutne seje.
        session.pop("email", None)
        session.pop("email_verified", None)

        # Odstrani porabljeno verifikacijsko kodo.
        Verification = Query()
        verification_codes_table.remove(Verification.email == user.email)

        # Preusmeri uporabnika na dashboard.
        return redirect(url_for("dashboard"))
    
    # Prikaži obrazec za registracijo.
    return render_template("signup.html", form=form)


# --------------------------------------------------------------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------------------------------------------------------------

# Prijava uporabika.
@app.route("/login", methods=["GET", "POST"])
def login():
    # Ustvari obrazec za login :D
    form = LoginForm()

    # Če je bil obrazec pravilno izpolnjen...
    if form.validate_on_submit():
        User = Query()

        # ...najprej preveri ali je vpisan email...
        user_data = users_table.get(User.email == form.username_or_email.data)
        if not user_data: # ... če ni, preveri še username.
            user_data = users_table.get(User.username == form.username_or_email.data)

        # Če uporabnik obstaja in se geslo ujema...
        if user_data and bcrypt.check_password_hash(user_data["password"], form.password.data):
            # ... preveri, ali je račun verified.
            if not user_data.get("verified", False):
                flash("Please verify your email first. Check your inbox.")
                return redirect(url_for("email"))
           
            # Prijavi uporabnika.
            user = UserClass(user_data.doc_id, user_data["username"], user_data["email"], user_data["password"], user_data["gender"], user_data.get("verified", False))
            login_user(user)
            return redirect(url_for("dashboard"))
        
        # Če je prijava neuspešna, to sporoči uporabniku.
        flash("Invalid username/email or password")
    
    # Prikaži login obrazec.
    return render_template("login.html", form=form)


# --------------------------------------------------------------------------------------------------------------------------------
# Reset password
# --------------------------------------------------------------------------------------------------------------------------------
@app.route("/reset-password-request", methods=["GET", "POST"])
def reset_password_request():
    # Obrazec za vnos email naslova za resetiranje gesla.
    form = ResetPasswordRequestForm()

    # Najprej preveri če je obrazec pravilno izpolnjen, kot vedno.
    if form.validate_on_submit():
        User = Query()
        user_data = users_table.get(User.email == form.email.data)

        # Ustvari kodo za resetiranje gesla.
        if user_data:
            # Ustvari verifikacijsko kodo za resetiranje gesla.
            reset_code = generate_verification_code()

            # Shrani kodo v database z rokom veljavnosti 15 minut.
            password_reset_codes_table.insert({
                "email": form.email.data,
                "code": reset_code,
                "created_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(minutes=15)).isoformat()
            })

            # Pošlji email z reset kodo
            if send_password_reset_code(form.email.data, reset_code):
                session["reset_email"] = form.email.data
                flash("Check your email for the reset code")
                return redirect(url_for("reset_code"))
            else:
                # V primeru napake, sporoči uporabniku.
                flash("Error sending reset code. Please try again.")
        else:
            # Prikaži sporočilo da je bila koda poslana. Yay! :D
            flash("You'll receive a reset code on email.")
            return redirect(url_for("login"))
    
    return render_template("reset_password_request.html", form=form)


# Reset code stuff....
@app.route("/reset-password-code", methods=["GET", "POST"])
def reset_code():
    if "reset_email" not in session:
        return redirect(url_for("reset_password_request"))
    form = ResetCodeForm()
    if form.validate_on_submit():
        ResetCode = Query()
        code_record = password_reset_codes_table.get((ResetCode.email == session["reset_email"]) & (ResetCode.code == form.code.data.upper()))

        # Preveri, če je koda še veljavna
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
            # Posodobi geslo z novim.
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


#
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", username=current_user.username, gender=current_user.gender)


#
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))


#
@app.route("/games", methods=["GET"])
@login_required
def games():
    all_games = games_table.all()
    return render_template("games.html", games=all_games)


#
@app.route("/games/<game_id>", methods=["GET"])
@login_required
def game_servers(game_id):
    game = games_table.get(doc_id=int(game_id))
    if not game:
        flash("Game not found.", "danger")
        return redirect(url_for("games"))

    search_query = request.args.get("search", "").strip().lower()
    region_filter = request.args.get("region", "").strip()

    all_regions = ["North America", "Europe", "Asia", "Oceania", "South America", "Africa"]
    all_servers = servers_table.search(Query().game_id == int(game_id))

    filtered_servers = []
    for server in all_servers:
        matches_search = (
            search_query in server.get("name", "").lower()
            or search_query in server.get("description", "").lower()
            or search_query in server.get("created_by", "").lower()
        ) if search_query else True

        matches_region = (server.get("region") == region_filter) if region_filter else True

        if matches_search and matches_region:
            filtered_servers.append(server)

    return render_template(
        "servers.html",
        game=game,
        servers=filtered_servers,
        regions=all_regions,
        selected_region=region_filter,
        search_query=search_query
    )


#
@app.route("/games/<game_id>/add-server", methods=["GET", "POST"])
@login_required
def add_server(game_id):
    game = games_table.get(doc_id=int(game_id))
    if not game:
        flash("Game not found.", "danger")
        return redirect(url_for("games"))

    if request.method == "POST":
        name = request.form.get("name")
        region = request.form.get("region")
        description = request.form.get("description", "")
        max_players = request.form.get("max_players", "")
        ip = request.form.get("ip")

        if not name or not region or not ip:
            flash("Name, region, and IP are required!", "danger")
        else:
            try:
                max_players = int(max_players) if max_players else None
            except ValueError:
                flash("Max players must be a number!", "danger")
                max_players = None

            if max_players is not None:
                d = datetime.now()
                servers_table.insert({
                    "game_id": int(game_id),
                    "name": name,
                    "region": region,
                    "description": description,
                    "max_players": max_players,
                    "ip": ip,
                    "created_by": current_user.username,
                    "created_at": d.strftime("%A" "%d" ".%m" ".%Y")
                })
                flash("Server added successfully.", "success")
                return redirect(url_for("game_servers", game_id=game_id))
            else:
                flash("Invalid number for max players.", "danger")

    regions = ["North America", "Europe", "Asia", "Oceania", "South America", "Africa"]
    max_players_list = [5, 10, 15, 20, 25, 30]
    return render_template("add_server.html", game=game, regions=regions, max_players_list=max_players_list)


@app.route("/games/<game_id>/server/<server_id>", methods=["GET"])
@login_required
def server_details(game_id, server_id):
    game = games_table.get(doc_id=int(game_id))
    if not game:
        flash("Game not found.", "danger")
        return redirect(url_for("games"))

    server = servers_table.get(doc_id=int(server_id))
    if not server:
        flash("Server not found.", "danger")
        return redirect(url_for("game_servers", game_id=game_id))

    return render_template("server_details.html", server=server)


@app.route("/admin/add-game", methods=["GET", "POST"])
@login_required
def add_game():
    if current_user.username != "Admin":
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name")
        about_html = request.form.get("about_html")

        if name and about_html:
            games_table.insert({
                "name": name,
                "about_html": about_html
            })
            flash("Game added successfully.", "success")
            return redirect(url_for("games"))
        else:
            flash("Both name and HTML filename are required!", "danger")

    return render_template("add_game.html")


@app.route("/games/<game_id>/server/<server_id>/delete", methods=["POST"])
@login_required
def delete_server(game_id, server_id):
    game = games_table.get(doc_id=int(game_id))
    if not game:
        flash("Game not found.", "danger")
        return redirect(url_for("games"))

    server = servers_table.get(doc_id=int(server_id))
    if not server:
        flash("Server not found.", "danger")
    elif current_user.username == "Admin" or server.get("created_by") == current_user.username:
        try:
            servers_table.remove(doc_ids=[int(server_id)])
            flash("Server deleted successfully.", "success")
        except Exception:
            flash("Error deleting server.", "danger")
    else:
        flash("You do not have permission to delete this server.", "danger")

    return redirect(url_for("game_servers", game_id=game_id))


@app.route("/admin/delete-all-servers", methods=["POST"])
@login_required
def delete_all_servers():
    if current_user.username != "Admin":
        return redirect(url_for("dashboard"))

    servers_table.truncate()
    flash("All servers have been deleted.", "success")
    return redirect(url_for("games"))


@app.route("/admin/delete-game/<game_id>", methods=["POST"])
@login_required
def delete_game(game_id):
    if current_user.username != "Admin":
        return redirect(url_for("games"))

    game = games_table.get(doc_id=int(game_id))
    if not game:
        flash("Game not found.", "danger")
        return redirect(url_for("games"))

    games_table.remove(doc_ids=[int(game_id)])
    flash("Game deleted successfully.", "success")
    return redirect(url_for("games"))


@app.route("/plans")
@login_required
def plans():
    if current_user.username == "Admin":
        flash("Admin has unlimited access", "info")
        return redirect(url_for("dashboard"))
    return render_template("plans.html")


@app.route("/create-checkout-session/<plan_id>", methods=["POST"])
@login_required
def create_checkout_session(plan_id):
    if plan_id not in ["normal", "premium"]:
        abort(400, description="Invalid plan")
    
    try:
        session["selected_plan"] = plan_id
        
        checkout_session = stripe.checkout.Session.create(
            line_items=[{
                "price": PRICES[plan_id],
                "quantity": 1,
            }],
            mode="subscription",
            success_url=url_for("payment_success", _external=True),
            cancel_url=url_for("plans", _external=True),
            customer_email=current_user.email,
            metadata={
                "user_id": current_user.id,
                "plan_id": plan_id
            }
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        app.logger.error(f"Stripe error: {str(e)}")
        flash("Payment processing error. Please try again.", "danger")
        return redirect(url_for("plans"))


@app.route("/payment-success")
@login_required
def payment_success():
    plan_id = session.get("selected_plan")
    
    if not plan_id or plan_id not in ["normal", "premium"]:
        flash("Unable to determine your selected plan. Please contact support.", "danger")
        return redirect(url_for("plans"))
    
    users_table.update({"plan": plan_id}, doc_ids=[int(current_user.id)])
    current_user.plan = plan_id
    
    session.pop("selected_plan", None)
    
    flash(f"Payment successful! Your plan has been changed to {plan_id.capitalize()}.", "success")
    return redirect(url_for("plans"))


@app.route("/upgrade/<plan_id>")
@login_required
def upgrade(plan_id):
    if current_user.username == "Admin":
        return redirect(url_for("plans"))

    if plan_id not in ["normal", "premium"]:
        flash("Invalid plan", "danger")
        return redirect(url_for("plans"))

    previous_plan = current_user.plan

    if previous_plan == plan_id:
        flash(f"You are already on the {plan_id} plan.", "info")
        return redirect(url_for("plans"))

    user_doc_id = int(current_user.id)
    users_table.update({"plan": plan_id}, doc_ids=[user_doc_id])
    current_user.plan = plan_id

    flash(f"{direction} to {plan_id.capitalize()} plan!", "success")
    return redirect(url_for("plans"))


# Zalaufi skripto :D
if __name__ == "__main__":
    app.run(debug=True)