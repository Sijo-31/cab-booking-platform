from datetime import datetime
from typing import Optional
from enum import Enum

from sqlmodel import SQLModel, Field
from pydantic import BaseModel


# ===============================
# REVIEW MODEL
# ===============================

class Review(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    ride_id: int
    reviewer_id: int
    reviewed_user_id: int

    rating: int
    comment: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ===============================
# REVIEW SCHEMA
# ===============================

class ReviewCreate(BaseModel):
    ride_id: int
    reviewed_user_id: int
    rating: int
    comment: Optional[str] = None


# ===============================
# RIDE STATUS ENUM
# ===============================

class RideStatus(str, Enum):
    requested = "requested"
    assigned = "assigned"
    in_progress = "in_progress"
    completed = "completed"
    paid = "paid"
    payment_failed = "payment_failed"
    cancelled = "cancelled"


# ===============================
# USER MODEL
# ===============================

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    name: str
    email: str
    hashed_password: str
    role: str = "user"
    wallet_balance: float = 0


# ===============================
# RIDE MODEL
# ===============================

class Ride(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: int = Field(index=True)
    driver_id: Optional[int] = Field(default=None, index=True)

    pickup_lat: float
    pickup_lng: float
    drop_lat: float
    drop_lng: float

    distance_km: float
    estimated_price: float

    status: RideStatus = Field(default=RideStatus.requested, index=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ===============================
# DRIVER MODEL
# ===============================

class Driver(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    name: str
    lat: float
    lng: float

    is_available: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ===============================
# DRIVER LOCATION UPDATE
# ===============================

class DriverLocationUpdate(SQLModel):
    driver_id: int
    lat: float
    lng: float


# ===============================
# REQUEST BODY MODELS
# ===============================

class EstimateRequest(BaseModel):
    pickup_lat: float
    pickup_lng: float
    drop_lat: float
    drop_lng: float


class RideRequest(BaseModel):
    pickup_lat: float = Field(..., ge=-90, le=90)
    pickup_lng: float = Field(..., ge=-180, le=180)
    drop_lat: float = Field(..., ge=-90, le=90)
    drop_lng: float = Field(..., ge=-180, le=180)


class RideStatusUpdate(BaseModel):
    status: RideStatus


class UserCreate(BaseModel):
    name: str
    email: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


# ===============================
# PROMO CODE MODEL
# ===============================

class PromoCode(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True)
    discount_amount: float
    active: bool = True