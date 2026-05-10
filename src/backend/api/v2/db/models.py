import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, UUID
)
import sqlalchemy
from sqlalchemy.orm import relationship
from v2.db.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    user_id = Column(String, index=True)
    title=Column(String, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow)
    summary = Column(Text, default="")

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String)  # user / assistant
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    tokens = Column(sqlalchemy.Integer, default=0)

    conversation = relationship("Conversation", back_populates="messages")

class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(String, index=True)
    type = Column(String) # like / dislike / report
    prompt = Column(Text)
    response = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    severity = Column(String, default="Low") # Low, Medium, High
    resolved = Column(sqlalchemy.Boolean, default=False)
    reason = Column(Text, nullable=True)

class UserMemory(Base):
    __tablename__ = "user_memories"

    id = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    fact = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
