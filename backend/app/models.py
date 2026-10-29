from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    users: Mapped[list["User"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    organization: Mapped[Organization | None] = relationship(back_populates="users")
    deliveries: Mapped[list["Delivery"]] = relationship(back_populates="volunteer")


class FoodListing(Base):
    __tablename__ = "food_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    donor_organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    portions: Mapped[int] = mapped_column(Integer, nullable=False)
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pickup_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    packaging: Mapped[str] = mapped_column(String(120), nullable=False)
    storage: Mapped[str] = mapped_column(String(120), nullable=False)
    allergens_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    safety_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="available", nullable=False, index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    donor: Mapped[Organization] = relationship()


class MealRequest(Base):
    __tablename__ = "meal_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    meals_needed: Mapped[int] = mapped_column(Integer, nullable=False)
    dietary_restrictions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    recipient: Mapped[Organization] = relationship()


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("food_listings.id"), index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("meal_requests.id"), index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="recommended", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    listing: Mapped[FoodListing] = relationship()
    request: Mapped[MealRequest] = relationship()


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), unique=True)
    volunteer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="available", nullable=False)
    volunteer_latitude: Mapped[float | None] = mapped_column(Float)
    volunteer_longitude: Mapped[float | None] = mapped_column(Float)
    proof_photo_path: Mapped[str | None] = mapped_column(String(500))
    proof_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proof_latitude: Mapped[float | None] = mapped_column(Float)
    proof_longitude: Mapped[float | None] = mapped_column(Float)
    reassignment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    emergency_cancel_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    volunteer: Mapped[User | None] = relationship(back_populates="deliveries")
    match: Mapped[Match] = relationship()


class PointEntry(Base):
    __tablename__ = "point_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    volunteer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id"), unique=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
