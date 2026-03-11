from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import SQLModel, Session, select
from math import sqrt
import stripe
import os
import json

from fastapi.responses import FileResponse
from reportlab.pdfgen import canvas
from fastapi.middleware.cors import CORSMiddleware

from .redis_client import redis_client
from .database import engine
from .auth import hash_password, verify_password, create_access_token, get_current_user
from rate_limiter import rate_limiter

from .models import (
    User,
    Ride,
    Driver,
    RideStatus,
    EstimateRequest,
    RideRequest,
    RideStatusUpdate,
    UserCreate,
    Review,
    ReviewCreate,
    PromoCode
)

# ===============================
# APP INIT
# ===============================

app = FastAPI()

SQLModel.metadata.create_all(engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================
# STRIPE CONFIG
# ===============================

stripe.api_key = os.getenv(
    "STRIPE_SECRET_KEY",
    "sk_test_key_here"
)

STRIPE_WEBHOOK_SECRET = os.getenv(
    "STRIPE_WEBHOOK_SECRET",
    "whsec_key_here"
)

# ===============================
# STARTUP
# ===============================

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

# ===============================
# WEBSOCKET MANAGER
# ===============================

class ConnectionManager:

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print("WebSocket connected")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print("WebSocket disconnected")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()

# ===============================
# GENERIC WEBSOCKET
# ===============================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    await manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"Message: {data}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ===============================
# AUTH REGISTER
# ===============================

@app.post("/auth/register")
def register(user: UserCreate):

    with Session(engine) as session:

        existing_user = session.exec(
            select(User).where(User.email == user.email)
        ).first()

        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed_pw = hash_password(user.password)

        new_user = User(
            name=user.name,
            email=user.email,
            hashed_password=hashed_pw
        )

        session.add(new_user)
        session.commit()
        session.refresh(new_user)

        return {"message": "User registered successfully"}

# ===============================
# AUTH LOGIN
# ===============================

@app.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(),
    dep=Depends(rate_limiter)
    ):

    with Session(engine) as session:

        db_user = session.exec(
            select(User).where(User.email == form_data.username)
        ).first()

        if not db_user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not verify_password(form_data.password, db_user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        access_token = create_access_token(
            data={"sub": str(db_user.id)}
        )

        return {
            "access_token": access_token,
            "token_type": "bearer"
        }

# ===============================
# STRIPE WEBHOOK
# ===============================
from .tasks import send_receipt_email
@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            STRIPE_WEBHOOK_SECRET
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Webhook verification failed")

    event_type = event["type"]
    payment_intent = event["data"]["object"]

    ride_id = payment_intent.get("metadata", {}).get("ride_id")

    if ride_id:

        with Session(engine) as session:

            ride = session.get(Ride, int(ride_id))

            if ride:

                if event_type == "payment_intent.succeeded":

                    ride.status = "paid"
                    session.commit()

                    send_receipt_email.delay("user@email.com",ride_id)
                    await manager.broadcast(
                        f"Ride {ride_id} payment successful"
                    )

                elif event_type == "payment_intent.payment_failed":

                    ride.status = "payment_failed"
                    session.commit()

                    await manager.broadcast(
                        f"Ride {ride_id} payment failed"
                    )

    return {"status": "success"}

# ===============================
# DRIVER CRUD
# ===============================

@app.post("/drivers")
def create_driver(driver: Driver):

    with Session(engine) as session:
        session.add(driver)
        session.commit()
        session.refresh(driver)
        return driver

@app.get("/drivers")
def get_drivers():

    with Session(engine) as session:
        return session.exec(select(Driver)).all()

@app.put("/drivers/{driver_id}/availability")
def update_driver_availability(driver_id: int, is_available: bool):

    with Session(engine) as session:

        driver = session.get(Driver, driver_id)

        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")

        driver.is_available = is_available
        session.commit()
        session.refresh(driver)

        return driver

# ===============================
# USERS
# ===============================

@app.get("/users")
def get_users():

    with Session(engine) as session:
        return session.exec(select(User)).all()

# ===============================
# DRIVER LOCATION WEBSOCKET
# ===============================

@app.websocket("/ws/driver_location")
async def driver_location_websocket(websocket: WebSocket):

    await manager.connect(websocket)

    try:
        while True:

            data = json.loads(await websocket.receive_text())

            driver_id = data["driver_id"]
            lat = data["lat"]
            lng = data["lng"]

            # Store location in Redis GEO
            redis_client.geoadd(
                "drivers_geo",
                (lng, lat, driver_id)
            )

            print(f"Driver {driver_id} stored in Redis")

            # Broadcast location update
            await manager.broadcast(json.dumps({
                "type": "driver_location",
                "driver_id": driver_id,
                "lat": lat,
                "lng": lng
            }))

    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ===============================
# NEARBY DRIVERS
# ===============================

@app.get("/drivers/nearby")
def get_nearby_drivers(lat: float, lng: float):

    drivers = redis_client.georadius(
        "drivers_geo",
        lng,
        lat,
        5,
        unit="km",
        withcoord=True
    )

    result = []

    for driver in drivers:

        driver_id = driver[0]
        coordinates = driver[1]

        result.append({
            "driver_id": driver_id,
            "lat": coordinates[1],
            "lng": coordinates[0]
        })

    return result

# ===============================
# ACTIVE DRIVERS
# ===============================

@app.get("/drivers/active")
def get_active_drivers():

    drivers = redis_client.zrange("drivers_geo", 0, -1)

    return drivers

# ===============================
# RIDE ESTIMATION
# ===============================

PRICE_PER_KM = 10

@app.post("/estimate")
def estimate_ride(data: EstimateRequest):

    distance = sqrt(
        (data.pickup_lat - data.drop_lat) ** 2 +
        (data.pickup_lng - data.drop_lng) ** 2
    ) * 111

    estimated_price = distance * PRICE_PER_KM

    return {
        "distance_km": round(distance, 2),
        "estimated_price": round(estimated_price, 2)
    }

# ===============================
# REQUEST RIDE
# ===============================

@app.post("/rides/request")
def request_ride(
    data: RideRequest,
    current_user: User = Depends(get_current_user),
    dep=Depends(rate_limiter)
):

    distance = sqrt(
        (data.pickup_lat - data.drop_lat) ** 2 +
        (data.pickup_lng - data.drop_lng) ** 2
    ) * 111

    estimated_price = distance * PRICE_PER_KM

    with Session(engine) as session:

        drivers = session.exec(
            select(Driver).where(Driver.is_available == True)
        ).all()

        if not drivers:
            raise HTTPException(status_code=404, detail="No drivers available")

        nearest_driver = min(
            drivers,
            key=lambda d: sqrt(
                (d.lat - data.pickup_lat) ** 2 +
                (d.lng - data.pickup_lng) ** 2
            )
        )

        nearest_driver.is_available = False

        ride = Ride(
            user_id=current_user.id,
            driver_id=nearest_driver.id,
            pickup_lat=data.pickup_lat,
            pickup_lng=data.pickup_lng,
            drop_lat=data.drop_lat,
            drop_lng=data.drop_lng,
            distance_km=round(distance, 2),
            estimated_price=round(estimated_price, 2),
            status="assigned"
        )

        session.add(ride)
        session.commit()
        session.refresh(ride)

        return ride

# ===============================
# UPDATE RIDE STATUS
# ===============================

@app.patch("/rides/{ride_id}/status")
async def update_ride_status(
    ride_id: int,
    status_data: RideStatusUpdate,
    current_user: User = Depends(get_current_user)
):

    with Session(engine) as session:

        ride = session.get(Ride, ride_id)

        if not ride:
            raise HTTPException(status_code=404, detail="Ride not found")

        ride.status = status_data.status

        session.commit()
        session.refresh(ride)

        # Send real-time update
        await manager.broadcast(
            f"Ride {ride_id} status updated to {status_data.status}"
        )

        return ride

# ===============================
# PAYMENT INTENT
# ===============================

@app.post("/rides/{ride_id}/pay")
def create_payment_intent(
    ride_id: int,
    current_user: User = Depends(get_current_user)
):

    with Session(engine) as session:

        ride = session.get(Ride, ride_id)

        if not ride:
            raise HTTPException(status_code=404, detail="Ride not found")

        user = session.get(User, current_user.id)

        ride_price = ride.estimated_price

        # Wallet deduction
        wallet_used = min(user.wallet_balance, ride_price)

        user.wallet_balance -= wallet_used

        remaining_amount = ride_price - wallet_used

        session.add(user)
        session.commit()

        # If wallet fully covers ride
        if remaining_amount == 0:
            return {
                "message": "Paid fully with wallet"
            }

        # Otherwise create Stripe payment
        intent = stripe.PaymentIntent.create(
            amount=int(remaining_amount * 100),
            currency="inr"
        )

        return {
            "wallet_used": wallet_used,
            "stripe_amount": remaining_amount,
            "client_secret": intent.client_secret
        }

# ===============================
# RIDE QUERIES
# ===============================

@app.get("/rides")
def get_rides(dep=Depends(rate_limiter)):

    with Session(engine) as session:
        return session.exec(select(Ride)).all()

@app.get("/rides/{ride_id}")
def get_ride(ride_id: int):

    with Session(engine) as session:

        ride = session.get(Ride, ride_id)

        if not ride:
            raise HTTPException(status_code=404, detail="Ride not found")

        return ride
    
#USER RIDE HISTORY

@app.get("/users/me/rides")
def get_my_rides(current_user: User = Depends(get_current_user)):

    with Session(engine) as session:

        rides = session.exec(
            select(Ride).where(Ride.user_id == current_user.id)
        ).all()

        return rides
    
#DRIVER RIDE HISTORY

@app.get("/drivers/{driver_id}/rides")
def get_driver_rides(driver_id: int):

    with Session(engine) as session:

        rides = session.exec(
            select(Ride).where(Ride.driver_id == driver_id)
        ).all()

        return rides
    
#RIDE RECEIPT ENDPOINT


@app.get("/rides/{ride_id}/receipt/pdf")
def generate_receipt_pdf(ride_id: int):

    with Session(engine) as session:

        ride = session.get(Ride, ride_id)

        if not ride:
            raise HTTPException(status_code=404, detail="Ride not found")

        pdf_file = f"receipt_{ride.id}.pdf"

        c = canvas.Canvas(pdf_file)

        c.setFont("Helvetica", 16)
        c.drawString(200, 800, "Cab Ride Receipt")

        c.setFont("Helvetica", 12)

        c.drawString(100, 750, f"Ride ID: {ride.id}")
        c.drawString(100, 720, f"User ID: {ride.user_id}")
        c.drawString(100, 690, f"Driver ID: {ride.driver_id}")
        c.drawString(100, 660, f"Distance: {ride.distance_km} km")
        c.drawString(100, 630, f"Price: ₹{ride.estimated_price}")
        c.drawString(100, 600, f"Status: {ride.status.value}")

        c.save()

        return FileResponse(
            pdf_file,
            media_type="application/pdf",
            filename=pdf_file
        )

#DRIVER RATING ENDPOINT

@app.get("/drivers/{driver_id}/rating")
def driver_rating(driver_id: int):

    with Session(engine) as session:

        reviews = session.exec(
            select(Review).where(Review.reviewed_user_id == driver_id)
        ).all()

        if not reviews:
            return {"rating": 0, "count": 0}

        avg = sum(r.rating for r in reviews) / len(reviews)

        return {
            "rating": round(avg, 2),
            "count": len(reviews)
        }
    
#REVIEWS ENDPOINT

@app.post("/reviews")
def create_review(
    review: ReviewCreate,
    current_user: User = Depends(get_current_user)
):

    with Session(engine) as session:

        db_review = Review(
            ride_id=review.ride_id,
            reviewer_id=current_user.id,
            reviewed_user_id=review.reviewed_user_id,
            rating=review.rating,
            comment=review.comment
        )

        session.add(db_review)
        session.commit()
        session.refresh(db_review)

        return db_review
    
#WALLET API
    
@app.get("/wallet")
def get_wallet(current_user: User = Depends(get_current_user)):

    with Session(engine) as session:

        user = session.get(User, current_user.id)

        return {"wallet_balance": user.wallet_balance}
    
#WALLET TOPUP API

class WalletTopup(SQLModel):
    amount: float

@app.post("/wallet/topup")
def wallet_topup(
    data: WalletTopup,
    current_user: User = Depends(get_current_user)
):

    with Session(engine) as session:

        user = session.get(User, current_user.id)

        user.wallet_balance += data.amount

        session.add(user)
        session.commit()
        return {"wallet_balance": user.wallet_balance}

#PROMO CODE API

class PromoApply(SQLModel):
    code: str  

@app.post("/promo/apply")
def apply_promo(data: PromoApply):

    with Session(engine) as session:

        promo = session.exec(
            select(PromoCode).where(PromoCode.code == data.code, PromoCode.active == True)
        ).first()
        if not promo or not promo.active:
            raise HTTPException(status_code=404, detail="Invalid promo code")

        return {"discount": promo.discount_amount}
    
#BACKEND WEBSOCKET ENDPOINT

@app.websocket("/ws/{ride_id}")
async def websocket_endpoint(websocket: WebSocket, ride_id: int):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Ride {ride_id} update: {data}")
    except WebSocketDisconnect:
        print("Client disconnected")

# ===============================
# ROOT
# ===============================

@app.get("/")
def root():
    return {"message": "Cab Booking Backend Running 🚀"}