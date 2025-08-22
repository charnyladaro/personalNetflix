from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    movie_requests = db.relationship("MovieRequest", backref="user", lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)


class Movie(db.Model):
    __tablename__ = "movies"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    genre = db.Column(db.String(100))
    duration = db.Column(db.Integer)
    release_year = db.Column(db.Integer)
    video_file = db.Column(db.String(300), nullable=False)
    thumbnail_file = db.Column(db.String(300))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    auto_generated_thumb = db.Column(db.Boolean, default=False)
    is_series = db.Column(db.Boolean, default=False)
    series_name = db.Column(db.String(200))
    season_number = db.Column(db.Integer)
    episode_number = db.Column(db.Integer)
    episode_title = db.Column(db.String(200))


class MovieRequest(db.Model):
    __tablename__ = "movie_requests"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    request_type = db.Column(db.String(50), default="movie")
    genre = db.Column(db.String(100))
    release_year = db.Column(db.Integer)
    series_name = db.Column(db.String(200))
    season_number = db.Column(db.Integer)
    episode_number = db.Column(db.Integer)
    imdb_link = db.Column(db.String(300))
    additional_info = db.Column(db.Text)
    status = db.Column(db.String(50), default="pending")
    admin_notes = db.Column(db.Text)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    processed_by = db.Column(db.Integer, db.ForeignKey("users.id"))


class IPWhitelist(db.Model):
    __tablename__ = "ip_whitelist"

    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), unique=True, nullable=False)
    description = db.Column(db.Text)
    added_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)


class IPAccessRequest(db.Model):
    __tablename__ = "ip_access_requests"

    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False)
    name = db.Column(db.String(100))
    reason = db.Column(db.Text)
    request_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default="pending")
    processed_time = db.Column(db.DateTime)
    processed_by = db.Column(db.Integer, db.ForeignKey("users.id"))


class AdminAccessLog(db.Model):
    __tablename__ = "admin_access_log"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    ip_address = db.Column(db.String(45))
    access_time = db.Column(db.DateTime, default=datetime.utcnow)
    action = db.Column(db.String(200))
    success = db.Column(db.Boolean, default=True)
