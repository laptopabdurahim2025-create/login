from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=True) # password can be null for oauth users
    name = db.Column(db.String(150), nullable=False)
    profile_pic = db.Column(db.String(500), nullable=True)
    auth_provider = db.Column(db.String(50), nullable=False, default='local') # 'local' or 'google'
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f'<User {self.email}>'
