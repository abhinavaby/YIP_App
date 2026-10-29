import base64
import json
import logging
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .live import live_connections
from .models import Delivery, FoodListing, Match, MealRequest, Organization, PointEntry, User, utcnow
from .schemas import (
    DeliveryView,
    DeliveryAssignment,
    ImageAnalysis,
    ListingCreate,
    ListingView,
    LocationUpdate,
    LoginInput,
    MatchAccept,
    MatchView,
    OrganizationView,
    PriorityOverride,
    RegisterInput,
    RequestCreate,
    TokenView,
    UserView,
)
from .security import ALGORITHM, create_access_token, get_current_user, hash_password, require_roles, verify_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("foodbridge")
Base.metadata.create_all(bind=engine)
app = FastAPI(title="FoodBridge API", version="0.1.0", description="Food rescue, matching, and delivery coordination.")
origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def as_user_view(user: User) -> UserView:
    return UserView(id=user.id, name=user.full_name, email=user.email, role=user.role, organization_id=user.organization_id)


def require_verified_organization(db: Session, user: User, kind: str) -> Organization:
    organization = db.get(Organization, user.organization_id) if user.organization_id else None
    if organization is None or organization.kind != kind:
        raise HTTPException(status_code=403, detail=f"A {kind} organization account is required.")
    if organization.verification_status != "verified":
        raise HTTPException(status_code=403, detail="Your organization must be verified before using this feature.")
    return organization


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/register", response_model=UserView, status_code=201)
def register(payload: RegisterInput, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    organization = None
    if payload.role in ("donor", "recipient"):
        organization = Organization(
            name=payload.organization_name or "",
            kind=payload.role,
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
        db.add(organization)
        db.flush()
    user = User(
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        organization_id=organization.id if organization else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return as_user_view(user)


@app.post("/api/auth/login", response_model=TokenView)
def login(payload: LoginInput, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return TokenView(access_token=create_access_token(user))


@app.get("/api/auth/me", response_model=UserView)
def current_account(user: User = Depends(get_current_user)):
    return as_user_view(user)


@app.get("/api/listings", response_model=list[ListingView])
def list_listings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(FoodListing).order_by(FoodListing.created_at.desc()).limit(100)
    if user.role == "donor":
        query = query.where(FoodListing.donor_organization_id == user.organization_id)
    listings = db.scalars(query).all()
    return [
        ListingView(
            id=item.id,
            title=item.title,
            category=item.category,
            portions=item.portions,
            status=item.status,
            pickup_deadline=item.pickup_deadline,
            donor_name=item.donor.name,
            latitude=item.latitude if item.latitude is not None else item.donor.latitude,
            longitude=item.longitude if item.longitude is not None else item.donor.longitude,
        )
        for item in listings
    ]


@app.get("/api/network/locations")
def network_locations(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    organizations = db.scalars(
        select(Organization).where(Organization.verification_status == "verified")
    ).all()
    locations = [
        {
            "id": f"organization-{org.id}",
            "name": org.name,
            "kind": org.kind,
            "latitude": org.latitude,
            "longitude": org.longitude,
        }
        for org in organizations
        if org.kind in ("donor", "recipient") and org.latitude is not None and org.longitude is not None
    ]
    deliveries = db.scalars(select(Delivery).where(Delivery.status.in_(("claimed", "en_route")))).all()
    routes = []
    for delivery in deliveries:
        latitude, longitude = delivery.volunteer_latitude, delivery.volunteer_longitude
        if latitude is None or longitude is None:
            continue
        volunteer = delivery.volunteer
        locations.append({
            "id": f"volunteer-{volunteer.id}",
            "name": volunteer.full_name,
            "kind": "volunteer",
            "latitude": latitude,
            "longitude": longitude,
        })
        donor = delivery.match.listing.donor
        recipient = delivery.match.request.recipient
        points = [[latitude, longitude]]
        if donor.latitude is not None and donor.longitude is not None:
            points.insert(0, [donor.latitude, donor.longitude])
        if recipient.latitude is not None and recipient.longitude is not None:
            points.append([recipient.latitude, recipient.longitude])
        if len(points) > 1:
            routes.append({"id": delivery.id, "points": points})
    return {"locations": locations, "routes": routes}


@app.post("/api/listings", response_model=ListingView, status_code=201)
async def create_listing(
    payload: ListingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("donor")),
):
    organization = require_verified_organization(db, user, "donor")
    listing = FoodListing(
        donor_organization_id=organization.id,
        title=payload.title,
        category=payload.category,
        portions=payload.portions,
        prepared_at=payload.prepared_at,
        pickup_deadline=payload.pickup_deadline,
        packaging=payload.packaging,
        storage=payload.storage,
        allergens_json=json.dumps(payload.allergens),
        safety_confirmed=payload.safety_confirmed,
        latitude=organization.latitude,
        longitude=organization.longitude,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    await live_connections.publish("listing.created", {"listing_id": listing.id, "status": listing.status})
    return ListingView(
        id=listing.id, title=listing.title, category=listing.category, portions=listing.portions,
        status=listing.status, pickup_deadline=listing.pickup_deadline, donor_name=organization.name,
        latitude=listing.latitude, longitude=listing.longitude,
    )


@app.post("/api/requests", status_code=201)
async def create_request(
    payload: RequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("recipient")),
):
    organization = require_verified_organization(db, user, "recipient")
    meal_request = MealRequest(
        recipient_organization_id=organization.id,
        meals_needed=payload.meals_needed,
        dietary_restrictions_json=json.dumps(payload.dietary_restrictions),
        cutoff_at=payload.cutoff_at,
    )
    db.add(meal_request)
    db.commit()
    db.refresh(meal_request)
    await live_connections.publish("request.created", {"request_id": meal_request.id})
    return {"id": meal_request.id, "status": meal_request.status}


def distance_km(listing: FoodListing, request: MealRequest) -> float | None:
    donor, recipient = listing.donor, request.recipient
    if donor.latitude is None or donor.longitude is None or recipient.latitude is None or recipient.longitude is None:
        return None
    lat1, lat2 = math.radians(donor.latitude), math.radians(recipient.latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(recipient.longitude - donor.longitude)
    arc = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(arc), math.sqrt(1 - arc))


def score_match(listing: FoodListing, request: MealRequest) -> tuple[float, str]:
    now = datetime.now(timezone.utc)
    deadline = listing.pickup_deadline
    cutoff = request.cutoff_at
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    hours_left = max(0.1, (deadline - now).total_seconds() / 3600)
    urgency = max(0, min(1, (12 - hours_left) / 12))
    portion_ratio = min(listing.portions, request.meals_needed) / max(listing.portions, request.meals_needed)
    distance = distance_km(listing, request)
    transit_score = max(0, 1 - (distance or 8) / 25)
    expiry_score = max(0, min(1, (cutoff - now).total_seconds() / (24 * 3600)))
    allergens = {item.casefold() for item in json.loads(listing.allergens_json)}
    restrictions = {item.casefold() for item in json.loads(request.dietary_restrictions_json)}
    conflicts = allergens.intersection(restrictions)
    allergen_score = 0 if conflicts else 1
    score = 100 * (0.32 * urgency + 0.32 * portion_ratio + 0.2 * transit_score + 0.08 * expiry_score + 0.08 * allergen_score)
    distance_text = f"{distance:.1f} km" if distance is not None else "nearby"
    explanation = (
        f"{listing.portions} portions for a {request.meals_needed}-meal need; estimated {distance_text} away. "
        + ("Dietary restrictions match." if not conflicts else f"Review restriction conflict: {', '.join(sorted(conflicts))}.")
    )
    return round(score, 1), explanation


async def explain_match(listing: FoodListing, request: MealRequest, score: float, fallback: str) -> str:
    prompt = (
        "In one short sentence, explain this food rescue match using only these facts. "
        "Do not claim a dietary fit when a restriction conflicts. "
        f"Listing: {listing.title}; portions: {listing.portions}; category: {listing.category}. "
        f"Recipient: {request.recipient.name}; meals needed: {request.meals_needed}; "
        f"restrictions: {request.dietary_restrictions_json}; score: {score}/100. "
        f"Calculated facts: {fallback}"
    )
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.post(
                f"{settings.ollama_url.rstrip('/')}/api/generate",
                json={"model": settings.ollama_text_model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            message = response.json().get("response", "").strip()
            return message[:500] if message else fallback
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("Ollama match explanation unavailable: %s", exc)
        return f"Local AI explanation unavailable. {fallback}"


@app.get("/api/match/prioritize", response_model=list[MatchView])
async def prioritize_matches(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = utcnow()
    listings = db.scalars(select(FoodListing).where(FoodListing.status == "available", FoodListing.pickup_deadline > now)).all()
    requests_query = select(MealRequest).where(MealRequest.status == "open", MealRequest.cutoff_at > now)
    if user.role == "recipient":
        requests_query = requests_query.where(MealRequest.recipient_organization_id == user.organization_id)
    requests = db.scalars(requests_query).all()
    candidates: list[tuple[float, FoodListing, MealRequest, str]] = []
    for listing in listings:
        for meal_request in requests:
            score, rationale = score_match(listing, meal_request)
            candidates.append((score, listing, meal_request, rationale))
    candidates.sort(key=lambda item: item[0], reverse=True)
    result: list[MatchView] = []
    for score, listing, meal_request, fallback in candidates[:20]:
        existing = db.scalar(select(Match).where(Match.listing_id == listing.id, Match.request_id == meal_request.id))
        rationale = existing.explanation if existing else await explain_match(listing, meal_request, score, fallback)
        if existing:
            existing.score = score
            existing.explanation = rationale
        else:
            db.add(Match(listing_id=listing.id, request_id=meal_request.id, score=score, explanation=rationale))
            db.flush()
        result.append(MatchView(
            match_id=existing.id if existing else db.scalar(
                select(Match.id).where(Match.listing_id == listing.id, Match.request_id == meal_request.id)
            ),
            listing_id=listing.id,
            request_id=meal_request.id,
            listing_title=listing.title,
            recipient_name=meal_request.recipient.name,
            score=score,
            explanation=rationale,
            portions=listing.portions,
        ))
    db.commit()
    return result


@app.post("/api/matches/accept", response_model=DeliveryView, status_code=201)
async def accept_match(
    payload: MatchAccept,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("recipient", "admin")),
):
    listing = db.get(FoodListing, payload.listing_id)
    meal_request = db.get(MealRequest, payload.request_id)
    if listing is None or meal_request is None or listing.status != "available" or meal_request.status != "open":
        raise HTTPException(status_code=409, detail="This food listing or meal request is no longer available.")
    if user.role == "recipient" and user.organization_id != meal_request.recipient_organization_id:
        raise HTTPException(status_code=403, detail="You can only accept matches for your organization.")
    match = db.scalar(select(Match).where(Match.listing_id == listing.id, Match.request_id == meal_request.id))
    if match is None:
        score, rationale = score_match(listing, meal_request)
        match = Match(listing_id=listing.id, request_id=meal_request.id, score=score, explanation=rationale)
        db.add(match)
        db.flush()
    match.status = "accepted"
    listing.status = "matched"
    meal_request.status = "matched"
    delivery = db.scalar(select(Delivery).where(Delivery.match_id == match.id))
    if delivery is None:
        delivery = Delivery(match_id=match.id, status="available")
        db.add(delivery)
    db.commit()
    db.refresh(delivery)
    await live_connections.publish("match.accepted", {"delivery_id": delivery.id, "listing_id": listing.id})
    return DeliveryView(id=delivery.id, status=delivery.status, volunteer_user_id=delivery.volunteer_user_id, listing_id=listing.id, request_id=meal_request.id)


@app.patch("/api/admin/matches/{match_id}/priority")
async def override_match_priority(
    match_id: int,
    payload: PriorityOverride,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    match = db.get(Match, match_id)
    if match is None or match.status not in ("recommended", "accepted"):
        raise HTTPException(status_code=404, detail="Active match not found.")
    match.score = payload.score
    match.explanation = payload.explanation
    db.commit()
    await live_connections.publish("match.priority_overridden", {"match_id": match.id, "score": match.score})
    return {"id": match.id, "score": match.score, "explanation": match.explanation}


@app.post("/api/admin/listings/{listing_id}/safety-reject")
async def reject_listing_safety(
    listing_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    listing = db.get(FoodListing, listing_id)
    if listing is None or listing.status in ("completed", "safety_rejected"):
        raise HTTPException(status_code=404, detail="Active food listing not found.")
    delivery = db.scalar(
        select(Delivery).join(Match).where(Match.listing_id == listing.id, Delivery.status.in_(("claimed", "en_route")))
    )
    if delivery is not None:
        raise HTTPException(status_code=409, detail="A food listing on an active volunteer route cannot be safety-rejected.")
    delivery = db.scalar(
        select(Delivery).join(Match).where(Match.listing_id == listing.id, Delivery.status == "available")
    )
    if delivery is not None:
        delivery.status = "cancelled"
        delivery.match.status = "rejected"
        delivery.match.request.status = "open"
    listing.status = "safety_rejected"
    db.commit()
    await live_connections.publish("listing.safety_rejected", {"listing_id": listing.id})
    return {"id": listing.id, "status": listing.status}


@app.post("/api/admin/deliveries/{delivery_id}/assign", response_model=DeliveryView)
async def assign_delivery(
    delivery_id: int,
    payload: DeliveryAssignment,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    delivery = db.get(Delivery, delivery_id)
    volunteer = db.get(User, payload.volunteer_user_id)
    if delivery is None or delivery.status not in ("available", "claimed", "en_route"):
        raise HTTPException(status_code=404, detail="Active delivery not found.")
    if volunteer is None or volunteer.role != "volunteer" or not volunteer.is_active:
        raise HTTPException(status_code=422, detail="A valid active volunteer account is required.")
    delivery.volunteer_user_id = volunteer.id
    delivery.status = "claimed"
    delivery.claimed_at = utcnow()
    delivery.reassignment_count += 1
    delivery.emergency_cancel_count += 1
    db.commit()
    await live_connections.publish("delivery.reassigned", {"delivery_id": delivery.id, "volunteer_id": volunteer.id})
    return DeliveryView(id=delivery.id, status=delivery.status, volunteer_user_id=volunteer.id, listing_id=delivery.match.listing_id, request_id=delivery.match.request_id)


@app.get("/api/deliveries", response_model=list[DeliveryView])
def list_deliveries(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Delivery).where(Delivery.status.in_(("available", "claimed", "en_route")))
    if user.role == "volunteer":
        query = query.where((Delivery.status == "available") | (Delivery.volunteer_user_id == user.id))
    elif user.role == "donor":
        query = query.join(Match).join(FoodListing).where(FoodListing.donor_organization_id == user.organization_id)
    elif user.role == "recipient":
        query = query.join(Match).join(MealRequest).where(MealRequest.recipient_organization_id == user.organization_id)
    result = []
    for delivery in db.scalars(query).all():
        donor = delivery.match.listing.donor
        recipient = delivery.match.request.recipient
        result.append(DeliveryView(
            id=delivery.id,
            status=delivery.status,
            volunteer_user_id=delivery.volunteer_user_id,
            listing_id=delivery.match.listing_id,
            request_id=delivery.match.request_id,
            listing_title=delivery.match.listing.title,
            recipient_name=recipient.name,
            donor_latitude=donor.latitude,
            donor_longitude=donor.longitude,
            recipient_latitude=recipient.latitude,
            recipient_longitude=recipient.longitude,
            proof_uploaded=bool(delivery.proof_photo_path),
            proof_uploaded_at=delivery.proof_uploaded_at,
        ))
    return result


@app.post("/api/deliveries/{delivery_id}/claim", response_model=DeliveryView)
async def claim_delivery(
    delivery_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("volunteer")),
):
    delivery = db.get(Delivery, delivery_id)
    if delivery is None or delivery.status != "available":
        raise HTTPException(status_code=409, detail="This delivery is no longer available.")
    delivery.volunteer_user_id = user.id
    delivery.status = "claimed"
    delivery.claimed_at = utcnow()
    db.commit()
    await live_connections.publish("delivery.claimed", {"delivery_id": delivery.id, "volunteer_id": user.id})
    return DeliveryView(id=delivery.id, status=delivery.status, volunteer_user_id=user.id, listing_id=delivery.match.listing_id, request_id=delivery.match.request_id)


@app.post("/api/deliveries/{delivery_id}/cancel", response_model=DeliveryView)
async def cancel_delivery(
    delivery_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("volunteer")),
):
    delivery = db.get(Delivery, delivery_id)
    if delivery is None or delivery.volunteer_user_id != user.id or delivery.status not in ("claimed", "en_route"):
        raise HTTPException(status_code=409, detail="This delivery cannot be cancelled by your account.")
    delivery.volunteer_user_id = None
    delivery.status = "available"
    delivery.claimed_at = None
    delivery.reassignment_count += 1
    delivery.volunteer_latitude = None
    delivery.volunteer_longitude = None
    db.commit()
    await live_connections.publish("delivery.reassigned", {"delivery_id": delivery.id, "reason": "emergency_cancel"})
    return DeliveryView(id=delivery.id, status=delivery.status, volunteer_user_id=None, listing_id=delivery.match.listing_id, request_id=delivery.match.request_id)


@app.patch("/api/deliveries/{delivery_id}/location")
async def update_location(
    delivery_id: int,
    payload: LocationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("volunteer")),
):
    delivery = db.get(Delivery, delivery_id)
    if delivery is None or delivery.volunteer_user_id != user.id:
        raise HTTPException(status_code=404, detail="Active delivery not found.")
    delivery.volunteer_latitude = payload.latitude
    delivery.volunteer_longitude = payload.longitude
    delivery.status = "en_route"
    db.commit()
    await live_connections.publish("delivery.location", {"delivery_id": delivery.id, **payload.model_dump()})
    return {"status": delivery.status}


@app.post("/api/deliveries/{delivery_id}/proof")
async def upload_proof(
    delivery_id: int,
    image: Annotated[UploadFile, File()],
    latitude: float,
    longitude: float,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("volunteer")),
):
    delivery = db.get(Delivery, delivery_id)
    if delivery is None or delivery.volunteer_user_id != user.id or delivery.status not in ("claimed", "en_route"):
        raise HTTPException(status_code=404, detail="Active delivery not found.")
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Proof must be a JPEG, PNG, or WebP image.")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise HTTPException(status_code=422, detail="Latitude or longitude is out of range.")
    content = await image.read(8 * 1024 * 1024 + 1)
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Proof image must be 8 MB or smaller.")
    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[image.content_type]
    directory = Path(settings.upload_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{uuid.uuid4().hex}{suffix}"
    destination.write_bytes(content)
    delivery.proof_photo_path = str(destination)
    delivery.proof_uploaded_at = utcnow()
    delivery.proof_latitude = latitude
    delivery.proof_longitude = longitude
    db.commit()
    await live_connections.publish("delivery.proof_uploaded", {"delivery_id": delivery.id})
    return {"status": "proof_uploaded"}


@app.post("/api/deliveries/{delivery_id}/complete", response_model=DeliveryView)
async def complete_delivery(
    delivery_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("volunteer")),
):
    delivery = db.get(Delivery, delivery_id)
    if delivery is None or delivery.volunteer_user_id != user.id or delivery.status not in ("claimed", "en_route"):
        raise HTTPException(status_code=409, detail="This delivery cannot be completed by your account.")
    if not delivery.proof_photo_path:
        raise HTTPException(status_code=400, detail="Upload proof of delivery before completing the handover.")
    delivery.status = "completed"
    delivery.completed_at = utcnow()
    delivery.match.listing.status = "completed"
    delivery.match.request.status = "fulfilled"
    db.add(PointEntry(volunteer_user_id=user.id, delivery_id=delivery.id, points=50, reason="Completed food rescue delivery"))
    db.commit()
    await live_connections.publish("delivery.completed", {"delivery_id": delivery.id})
    return DeliveryView(id=delivery.id, status=delivery.status, volunteer_user_id=user.id, listing_id=delivery.match.listing_id, request_id=delivery.match.request_id)


@app.get("/api/volunteers/me/points")
def volunteer_points(db: Session = Depends(get_db), user: User = Depends(require_roles("volunteer"))):
    entries = db.scalars(select(PointEntry).where(PointEntry.volunteer_user_id == user.id).order_by(PointEntry.created_at.desc())).all()
    return {"total": sum(entry.points for entry in entries), "entries": [{"points": e.points, "reason": e.reason, "created_at": e.created_at} for e in entries]}


@app.get("/api/admin/organizations/pending", response_model=list[OrganizationView])
def pending_organizations(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    return db.scalars(select(Organization).where(Organization.verification_status == "pending").order_by(Organization.created_at)).all()


@app.post("/api/admin/organizations/{organization_id}/verify", response_model=OrganizationView)
async def verify_organization(
    organization_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found.")
    organization.verification_status = "verified"
    db.commit()
    db.refresh(organization)
    await live_connections.publish("organization.verified", {"organization_id": organization.id})
    return organization


@app.get("/api/admin/metrics")
def admin_metrics(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    meals_saved = db.scalar(select(func.coalesce(func.sum(FoodListing.portions), 0)).where(FoodListing.status == "completed")) or 0
    supported = db.scalar(select(func.count()).select_from(Organization).where(Organization.verification_status == "verified", Organization.kind == "recipient")) or 0
    completed = db.scalar(select(func.count()).select_from(Delivery).where(Delivery.status == "completed")) or 0
    rescinded = db.scalar(select(func.count()).select_from(Delivery).where(Delivery.emergency_cancel_count > 0)) or 0
    safety_rejections = db.scalar(select(func.count()).select_from(FoodListing).where(FoodListing.status == "safety_rejected")) or 0
    pending = db.scalar(select(func.count()).select_from(Organization).where(Organization.verification_status == "pending")) or 0
    return {
        "meals_saved": meals_saved,
        "recipient_organizations_supported": supported,
        "completed_deliveries": completed,
        "rescinded_deliveries": rescinded,
        "safety_rejections": safety_rejections,
        "pending_verifications": pending,
    }


@app.post("/api/ai/analyze-image", response_model=ImageAnalysis)
async def analyze_image(
    image: Annotated[UploadFile, File()],
    _: User = Depends(require_roles("donor")),
):
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, or WebP food photo.")
    content = await image.read(8 * 1024 * 1024 + 1)
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be 8 MB or smaller.")
    prompt = (
        "Analyze this food image for a food donation listing. Estimate portions conservatively. "
        "Reply only with JSON: {\"suggested_category\":\"short food name/category\","
        "\"confidence_score\":0.0,\"estimated_portions\":0}. "
        "Use confidence_score between 0 and 1 and a non-negative integer portion estimate."
    )
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.ollama_url.rstrip('/')}/api/generate",
                json={
                    "model": settings.ollama_vision_model,
                    "prompt": prompt,
                    "images": [base64.b64encode(content).decode("ascii")],
                    "stream": False,
                    "format": "json",
                },
            )
            response.raise_for_status()
            raw = response.json()["response"]
            parsed = json.loads(raw)
            return ImageAnalysis.model_validate(parsed)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.exception("Local Ollama image analysis failed")
        raise HTTPException(status_code=503, detail="Local image analysis is unavailable. Check that Ollama and the configured vision model are running.") from exc


def websocket_user(token: str | None, db: Session) -> User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None


@app.websocket("/ws/updates")
async def updates(socket: WebSocket, token: str | None = None):
    with SessionLocal() as db:
        user = websocket_user(token, db)
    if user is None or not user.is_active:
        await socket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await live_connections.connect(socket)
    try:
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        await live_connections.disconnect(socket)
