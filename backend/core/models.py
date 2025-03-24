from flask_sqlalchemy import SQLAlchemy
import uuid
from datetime import datetime

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
    
    # Beziehung zu TokenUsage-Modell hinzufügen
    token_usages = db.relationship('TokenUsage', back_populates='user')

class Upload(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    session_id = db.Column(db.String(36), unique=True, nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=True)
    file_name_1 = db.Column(db.String(200), nullable=True)
    file_name_2 = db.Column(db.String(200), nullable=True)
    file_name_3 = db.Column(db.String(200), nullable=True)
    file_name_4 = db.Column(db.String(200), nullable=True)
    file_name_5 = db.Column(db.String(200), nullable=True)
    upload_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    content = db.Column(db.Text)
    token_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    last_used_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    processing_status = db.Column(db.String(50), default="pending")  # pending, processing, completed, failed

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
    parent_id = db.Column(db.String(36), nullable=True)
    description = db.Column(db.Text, nullable=True)
    is_key_term = db.Column(db.Boolean, default=False)

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
    main_topic = db.Column(db.String(200))
    subtopics = db.Column(db.JSON)
    session_id = db.Column(db.String(36), db.ForeignKey('upload.session_id'), nullable=True)
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
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text)
    expires_at = db.Column(db.DateTime, nullable=False)

# Das neue TokenUsage-Modell (ersetzt ApiTokenUsage)
class TokenUsage(db.Model):
    """
    Speichert die Nutzung von API-Tokens für verschiedene Funktionen.
    Trackt detailliert Token-Nutzung, Kosten und Cache-Status.
    """
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=True)
    session_id = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    model = db.Column(db.String(50), nullable=False)
    input_tokens = db.Column(db.Integer, nullable=False)
    output_tokens = db.Column(db.Integer, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    endpoint = db.Column(db.String(100), nullable=True)
    function_name = db.Column(db.String(100), nullable=True)
    cached = db.Column(db.Boolean, default=False)
    request_metadata = db.Column(db.JSON, nullable=True)
    
    # Beziehung zu User
    user = db.relationship("User", back_populates="token_usages")
    
    def __repr__(self):
        return f"<TokenUsage {self.id} user_id={self.user_id} tokens={self.input_tokens}+{self.output_tokens} cost={self.cost}>"
