from datetime import datetime

from fastapi import (
    FastAPI,
    Depends,
    HTTPException
)

from pydantic import BaseModel

from sqlalchemy.orm import Session

from database import (
    Base,
    engine,
    get_db
)

from models import (
    Client,
    FollowUp
)



# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="FollowUpAI",
    description="AI-powered automated follow-up system",
    version="1.0.0"
)


# =========================================================
# CREATE DATABASE TABLES
# =========================================================

Base.metadata.create_all(
    bind=engine
)


# =========================================================
# REQUEST MODELS
# =========================================================

class ClientCreate(BaseModel):

    name: str

    phone: str

    product: str | None = None

    notes: str | None = None


class FollowUpCreate(BaseModel):

    client_id: int

    scheduled_at: datetime


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():

    return {
        "message": "FollowUpAI API is running 🚀"
    }


# =========================================================
# CREATE CLIENT
# =========================================================

@app.post("/clients")
def create_client(
    request: ClientCreate,
    db: Session = Depends(get_db)
):

    client = Client(
        name=request.name,
        phone=request.phone,
        product=request.product,
        notes=request.notes
    )

    db.add(client)

    db.commit()

    db.refresh(client)

    return {
        "status": "success",
        "client": {
            "id": client.id,
            "name": client.name,
            "phone": client.phone,
            "product": client.product,
            "notes": client.notes
        }
    }


# =========================================================
# GET CLIENTS
# =========================================================

@app.get("/clients")
def get_clients(
    db: Session = Depends(get_db)
):

    clients = db.query(
        Client
    ).all()

    return clients


# =========================================================
# CREATE FOLLOW-UP
# =========================================================

@app.post("/followups")
def create_followup(
    request: FollowUpCreate,
    db: Session = Depends(get_db)
):

    client = db.query(
        Client
    ).filter(
        Client.id == request.client_id
    ).first()

    if not client:

        raise HTTPException(
            status_code=404,
            detail="Client not found."
        )

    followup = FollowUp(
        client_id=request.client_id,
        scheduled_at=request.scheduled_at,
        status="scheduled"
    )

    db.add(followup)

    db.commit()

    db.refresh(followup)

    return {
        "status": "success",
        "followup": {
            "id": followup.id,
            "client_id": followup.client_id,
            "scheduled_at": followup.scheduled_at,
            "status": followup.status
        }
    }


# =========================================================
# GET FOLLOW-UPS
# =========================================================

@app.get("/followups")
def get_followups(
    db: Session = Depends(get_db)
):

    followups = db.query(
        FollowUp
    ).all()

    return followups

# =========================================================
# PROCESS DUE FOLLOW-UPS
# =========================================================

@app.post("/followups/process")
def process_followups(
    db: Session = Depends(get_db)
):

    # -----------------------------------------------------
    # CURRENT TIME
    # -----------------------------------------------------

    now = datetime.now()

    # -----------------------------------------------------
    # FIND DUE FOLLOW-UPS
    # -----------------------------------------------------

    due_followups = db.query(
        FollowUp
    ).filter(
        FollowUp.status == "scheduled",
        FollowUp.scheduled_at <= now
    ).all()

    processed = []

    # -----------------------------------------------------
    # PROCESS FOLLOW-UPS
    # -----------------------------------------------------

    for followup in due_followups:

        client = db.query(
            Client
        ).filter(
            Client.id == followup.client_id
        ).first()

        # Change status

        followup.status = "processed"

        processed.append(
            {
                "followup_id": followup.id,

                "client_id": followup.client_id,

                "client_name": (
                    client.name
                    if client
                    else None
                ),

                "phone": (
                    client.phone
                    if client
                    else None
                ),

                "product": (
                    client.product
                    if client
                    else None
                ),

                "scheduled_at": (
                    followup.scheduled_at
                ),

                "status": followup.status
            }
        )

    # -----------------------------------------------------
    # SAVE
    # -----------------------------------------------------

    db.commit()

    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    return {
        "status": "success",

        "processed_count": len(
            processed
        ),

        "processed_followups": processed
    }
    
