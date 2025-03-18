from flask_sqlalchemy import SQLAlchemy
import uuid

def generate_uuid():
    return str(uuid.uuid4())

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    avatar = db.Column(db.String(200))
    oauth_provider = db.Column(db.String(50))
    oauth_id = db.Column(db.String(100))
    credits = db.Column(db.Integer, default=0)

class Upload(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    session_id = db.Column(db.String(36), unique=True, nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=True)
    file_name = db.Column(db.String(200))
    upload_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    content = db.Column(db.Text)

class Flashcard(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id'), nullable=False)
    question = db.Column(db.String(500), nullable=False)
    answer = db.Column(db.String(500), nullable=False)

class Question(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id'), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    options = db.Column(db.JSON, nullable=False)
    correct_answer = db.Column(db.Integer, nullable=False)
    explanation = db.Column(db.String(1000))

class Topic(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    is_main_topic = db.Column(db.Boolean, default=False)
    parent_id = db.Column(db.String(36), db.ForeignKey('topic.id'), nullable=True)

class Connection(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id'), nullable=False)
    source_id = db.Column(db.String(36), db.ForeignKey('topic.id'), nullable=False)
    target_id = db.Column(db.String(36), db.ForeignKey('topic.id'), nullable=False)
    label = db.Column(db.String(500), nullable=False)

class UserActivity(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    details = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

class Payment(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    credits = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

class OAuthToken(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    access_token = db.Column(db.String(200), nullable=False)
    refresh_token = db.Column(db.String(200))
    expires_at = db.Column(db.DateTime, nullable=False)
