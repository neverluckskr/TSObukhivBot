"""
ORM модели для базы данных
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    registration_date = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    is_banned = Column(Boolean, default=False, server_default="0")

    # Связи
    posts = relationship("Post", back_populates="user")
    payments = relationship("Payment", back_populates="user")


class Post(Base):
    """Модель поста"""
    __tablename__ = "posts"

    post_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    post_type = Column(String(20), nullable=False)  # 'free', 'ad35', 'offtopic50'
    content = Column(Text, nullable=False)
    media_file_id = Column(String(255), nullable=True)
    status = Column(String(20), default="pending", server_default="pending")  # 'pending', 'approved', 'rejected'
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    moderated_at = Column(DateTime, nullable=True)
    moderator_id = Column(BigInteger, nullable=True)
    channel_message_id = Column(BigInteger, nullable=True)

    # Связи
    user = relationship("User", back_populates="posts")


class Payment(Base):
    """Модель платежа"""
    __tablename__ = "payments"

    payment_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    post_type = Column(String(20), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), nullable=False)  # 'UAH', 'XTR' (Stars)
    payment_method = Column(String(20), nullable=False)  # 'stars', 'stripe'
    status = Column(String(20), default="pending", server_default="pending")  # 'pending', 'completed', 'failed'
    transaction_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())

    # Связи
    user = relationship("User", back_populates="payments")


class ChatJoinRequest(Base):
    """Модель заявки на вступление в канал"""
    __tablename__ = "chat_join_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    username = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    status = Column(String(20), default="pending", server_default="pending")  # 'pending','approved','rejected'
    moderator_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    handled_at = Column(DateTime, nullable=True)


class Moderator(Base):
    """Модель модератора"""
    __tablename__ = "moderators"

    moderator_id = Column(BigInteger, primary_key=True)
    username = Column(String(255), nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())

