from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


Role = Literal["donor", "recipient", "volunteer", "admin"]


class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    role: Literal["donor", "recipient", "volunteer"]
    organization_name: str | None = Field(default=None, max_length=160)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def organization_required_for_org_roles(self):
        if self.role in ("donor", "recipient") and not self.organization_name:
            raise ValueError("An organization name is required for donor and recipient accounts.")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude, or leave both empty.")
        return self


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class UserView(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: Role
    organization_id: int | None


class TokenView(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ListingCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    category: str = Field(min_length=2, max_length=80)
    portions: int = Field(gt=0, le=10000)
    prepared_at: datetime
    pickup_deadline: datetime
    packaging: str = Field(min_length=2, max_length=120)
    storage: str = Field(min_length=2, max_length=120)
    allergens: list[str] = Field(default_factory=list, max_length=30)
    safety_confirmed: bool

    @model_validator(mode="after")
    def validate_listing(self):
        if not self.safety_confirmed:
            raise ValueError("Food safety confirmation is required.")
        if self.pickup_deadline <= self.prepared_at:
            raise ValueError("Pickup deadline must be later than preparation time.")
        return self


class ListingView(BaseModel):
    id: int
    title: str
    category: str
    portions: int
    status: str
    pickup_deadline: datetime
    donor_name: str
    latitude: float | None
    longitude: float | None


class RequestCreate(BaseModel):
    meals_needed: int = Field(gt=0, le=10000)
    dietary_restrictions: list[str] = Field(default_factory=list, max_length=30)
    cutoff_at: datetime


class MatchAccept(BaseModel):
    listing_id: int
    request_id: int


class PriorityOverride(BaseModel):
    score: float = Field(ge=0, le=100)
    explanation: str = Field(min_length=8, max_length=500)


class DeliveryAssignment(BaseModel):
    volunteer_user_id: int


class MatchView(BaseModel):
    match_id: int
    listing_id: int
    request_id: int
    listing_title: str
    recipient_name: str
    score: float
    explanation: str
    portions: int


class ImageAnalysis(BaseModel):
    suggested_category: str
    confidence_score: float = Field(ge=0, le=1)
    estimated_portions: int = Field(ge=0)


class LocationUpdate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class DeliveryView(BaseModel):
    id: int
    status: str
    volunteer_user_id: int | None
    listing_id: int
    request_id: int
    listing_title: str = ""
    recipient_name: str = ""
    donor_latitude: float | None = None
    donor_longitude: float | None = None
    recipient_latitude: float | None = None
    recipient_longitude: float | None = None
    proof_uploaded: bool = False
    proof_uploaded_at: datetime | None = None


class OrganizationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    verification_status: str
    created_at: datetime
