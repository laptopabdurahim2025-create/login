import os
import json
import requests
from flask import Flask, render_template, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import current_user, login_user, logout_user, login_required, LoginManager
from authlib.integrations.flask_client import OAuth

from config import Config
from models import db, User
from forms import LoginForm, SignUpForm

app = Flask(__name__)
app.config.from_object(Config)

# Initialize DB
db.init_app(app)

# Initialize Login Manager
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize OAuth
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config.get('GOOGLE_CLIENT_ID'),
    client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
    access_token_url='https://accounts.google.com/o/oauth2/token',
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    userinfo_endpoint='https://openidconnect.googleapis.com/v1/userinfo',
    client_kwargs={'scope': 'openid email profile'},
    server_metadata_url=app.config.get('GOOGLE_DISCOVERY_URL')
)

@app.before_request
def create_tables():
    db.create_all()

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = SignUpForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        user = User(name=form.name.data, email=form.email.data, password=hashed_password, auth_provider='local')
        db.session.add(user)
        db.session.commit()
        flash('Account created successfully! You are now able to log in.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.password and check_password_hash(user.password, form.password.data):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Login unsuccessful. Please check email and password.', 'danger')
    return render_template('login.html', form=form)

@app.route('/login/google')
def google_login():
    if not app.config.get('GOOGLE_CLIENT_ID'):
        flash('Google Login is not configured. Please set GOOGLE_CLIENT_ID in the environment.', 'warning')
        return redirect(url_for('login'))
    redirect_uri = url_for('google_authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/login/google/authorize')
def google_authorize():
    try:
        token = google.authorize_access_token()
        resp = google.get('userinfo')
        user_info = resp.json()
        
        email = user_info['email']
        name = user_info['name']
        profile_pic = user_info.get('picture', '')

        user = User.query.filter_by(email=email).first()
        if not user:
            # Create a new user for Google OAuth
            user = User(email=email, name=name, profile_pic=profile_pic, auth_provider='google')
            db.session.add(user)
            db.session.commit()
            
        # Log the user in
        login_user(user, remember=True)
        return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f'Error logging in with Google: {str(e)}', 'danger')
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
