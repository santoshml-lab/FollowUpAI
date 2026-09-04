from fastapi.middleware.cors import CORSMiddleware
from fastapi import (
    FastAPI,
    Depends,
    HTTPException
)



from datetime import datetime, timedelta
import os

from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    Depends,
    HTTPException
)

from pydantic import BaseModel

from sqlalchemy.orm import Session

from groq import Groq

from apscheduler.schedulers.background import BackgroundScheduler

from database import (
    Base,
    engine,
    get_db,
    SessionLocal
)

from models import (
    Client,
    FollowUp,
    CallLog
)


# =========================================================
# AUTOMATIC FOLLOW-UP SCHEDULER
# =========================================================

scheduler = BackgroundScheduler()


def automatic_followup_check():

    db = SessionLocal()

    try:

        now = datetime.now()

        due_followups = db.query(
            FollowUp
        ).filter(
            FollowUp.status == "scheduled",
            FollowUp.scheduled_at <= now
        ).all()

        for followup in due_followups:

            client = db.query(
                Client
            ).filter(
                Client.id == followup.client_id
            ).first()

            if not client:
                continue

            # -------------------------------------------------
            # PROCESS FOLLOW-UP
            # -------------------------------------------------

            followup.status = "processed"

            print(
                f"Follow-up processed: "
                f"{followup.id} - {client.name}"
            )

        db.commit()

    except Exception as error:

        print(
            f"Scheduler error: {error}"
        )

        db.rollback()

    finally:

        db.close()


# =========================================================
# APP LIFESPAN
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    scheduler.start()

    print(
        "FollowUpAI scheduler started 🚀"
    )

    yield

    scheduler.shutdown()

    print(
        "FollowUpAI scheduler stopped."
    )


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="FollowUpAI",
    description="AI-powered automated follow-up system",
    version="1.2.0",
    lifespan=lifespan
)
# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# GROQ CLIENT
# =========================================================

groq_api_key = os.getenv("GROQ_API_KEY")

if not groq_api_key:

    raise RuntimeError(
        "GROQ_API_KEY environment variable is not set."
    )

groq_client = Groq(
    api_key=groq_api_key
)


# =========================================================
# CREATE DATABASE TABLES
# =========================================================

Base.metadata.create_all(
    bind=engine
)


# =========================================================
# SCHEDULER JOB
# =========================================================

scheduler.add_job(
    automatic_followup_check,
    "interval",
    seconds=60,
    id="followup_checker",
    replace_existing=True
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
# GENERATE AI FOLLOW-UP SCRIPT
# =========================================================

def generate_followup_script(
    client
):

    prompt = f"""
You are an AI customer follow-up assistant.

Create a short, polite and professional
phone-call script for the following client.

Client name: {client.name}
Product: {client.product or "Not specified"}
Notes: {client.notes or "No additional notes"}

Requirements:

- Keep it natural and conversational.
- Keep it concise.
- Clearly identify that this is an automated assistant.
- Do not pressure the customer.
- Do not make false promises.
- Do not ask for passwords, OTPs, PINs,
  bank credentials, or other sensitive information.
- If the customer does not want further contact,
  politely acknowledge their request.
"""

    try:

        response = groq_client.chat.completions.create(

            model="openai/gpt-oss-20b",

            messages=[
                {
                    "role": "system",

                    "content": (
                        "You generate safe, concise "
                        "customer follow-up scripts."
                    )
                },

                {
                    "role": "user",

                    "content": prompt
                }
            ],

            temperature=0.3
        )

        content = (
            response.choices[0]
            .message
            .content
        )

        if not content:

            return (
                "Unable to generate "
                "a follow-up script."
            )

        return content.strip()

    except Exception as error:

        raise RuntimeError(
            f"AI script generation error: {error}"
        )


# =========================================================
# GENERATE FOLLOW-UP SCRIPT
# =========================================================

@app.post(
    "/followups/{followup_id}/script"
)
def generate_script(
    followup_id: int,
    db: Session = Depends(get_db)
):

    followup = db.query(
        FollowUp
    ).filter(
        FollowUp.id == followup_id
    ).first()

    if not followup:

        raise HTTPException(
            status_code=404,
            detail="Follow-up not found."
        )

    client = db.query(
        Client
    ).filter(
        Client.id == followup.client_id
    ).first()

    if not client:

        raise HTTPException(
            status_code=404,
            detail="Client not found."
        )

    try:

        script = generate_followup_script(
            client
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    return {

        "status": "success",

        "followup_id": followup.id,

        "client": {

            "id": client.id,

            "name": client.name,

            "product": client.product
        },

        "script": script
    }


# =========================================================
# PROCESS DUE FOLLOW-UPS
# =========================================================

@app.post("/followups/process")
def process_followups(
    db: Session = Depends(get_db)
):

    now = datetime.now()

    due_followups = db.query(
        FollowUp
    ).filter(
        FollowUp.status == "scheduled",
        FollowUp.scheduled_at <= now
    ).all()

    processed = []

    for followup in due_followups:

        client = db.query(
            Client
        ).filter(
            Client.id == followup.client_id
        ).first()

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

    db.commit()

    return {

        "status": "success",

        "processed_count": len(
            processed
        ),

        "processed_followups": processed
    }


# =========================================================
# TEST VOICE CALL - DRY RUN
# =========================================================

@app.post("/followups/{followup_id}/call-test")
def test_voice_call(
    followup_id: int,
    db: Session = Depends(get_db)
):

    followup = db.query(
        FollowUp
    ).filter(
        FollowUp.id == followup_id
    ).first()

    if not followup:

        raise HTTPException(
            status_code=404,
            detail="Follow-up not found."
        )

    client = db.query(
        Client
    ).filter(
        Client.id == followup.client_id
    ).first()

    if not client:

        raise HTTPException(
            status_code=404,
            detail="Client not found."
        )

    try:

        script = generate_followup_script(
            client
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    return {

        "status": "success",

        "mode": "dry_run",

        "message": (
            "Voice call was NOT placed. "
            "This is a test only."
        ),

        "call": {

            "followup_id": followup.id,

            "client_id": client.id,

            "client_name": client.name,

            "phone": client.phone,

            "product": client.product,

            "script": script
        }
    }


# =========================================================
# CREATE CALL LOG
# =========================================================

@app.post("/followups/{followup_id}/call-log")
def create_call_log(
    followup_id: int,
    db: Session = Depends(get_db)
):

    followup = db.query(
        FollowUp
    ).filter(
        FollowUp.id == followup_id
    ).first()

    if not followup:

        raise HTTPException(
            status_code=404,
            detail="Follow-up not found."
        )

    client = db.query(
        Client
    ).filter(
        Client.id == followup.client_id
    ).first()

    if not client:

        raise HTTPException(
            status_code=404,
            detail="Client not found."
        )

    call_log = CallLog(
        followup_id=followup.id,
        phone=client.phone,
        status="queued",
        outcome=None
    )

    db.add(call_log)

    db.commit()

    db.refresh(call_log)

    return {

        "status": "success",

        "message": "Call queued in test mode.",

        "call_log": {

            "id": call_log.id,

            "followup_id": call_log.followup_id,

            "phone": call_log.phone,

            "status": call_log.status,

            "outcome": call_log.outcome,

            "created_at": call_log.created_at
        }
    }


# =========================================================
# UPDATE CALL STATUS
# =========================================================

@app.patch("/call-logs/{call_log_id}")
def update_call_log(
    call_log_id: int,
    status: str,
    outcome: str | None = None,
    db: Session = Depends(get_db)
):

    call_log = db.query(
        CallLog
    ).filter(
        CallLog.id == call_log_id
    ).first()

    if not call_log:

        raise HTTPException(
            status_code=404,
            detail="Call log not found."
        )

    call_log.status = status

    if outcome is not None:

        call_log.outcome = outcome

    db.commit()

    db.refresh(call_log)

    return {

        "status": "success",

        "call_log": {

            "id": call_log.id,

            "followup_id": call_log.followup_id,

            "phone": call_log.phone,

            "status": call_log.status,

            "outcome": call_log.outcome
        }
    }


# =========================================================
# GET CALL LOGS
# =========================================================

@app.get("/call-logs")
def get_call_logs(
    db: Session = Depends(get_db)
):

    call_logs = db.query(
        CallLog
    ).all()

    return call_logs


# =========================================================
# AUTO SCHEDULE FOLLOW-UP
# =========================================================

@app.post(
    "/followups/auto-schedule/{client_id}"
)
def auto_schedule_followup(
    client_id: int,
    db: Session = Depends(get_db)
):

    client = db.query(
        Client
    ).filter(
        Client.id == client_id
    ).first()

    if not client:

        raise HTTPException(
            status_code=404,
            detail="Client not found."
        )

    existing = db.query(
        FollowUp
    ).filter(
        FollowUp.client_id == client_id,
        FollowUp.status == "scheduled"
    ).first()

    if existing:

        return {

            "status": "already_scheduled",

            "message": (
                "Client already has a "
                "scheduled follow-up."
            ),

            "followup": {

                "id": existing.id,

                "client_id": existing.client_id,

                "scheduled_at": (
                    existing.scheduled_at
                ),

                "status": existing.status
            }
        }

    scheduled_time = (
        datetime.now()
        + timedelta(days=1)
    )

    followup = FollowUp(
        client_id=client_id,
        scheduled_at=scheduled_time,
        status="scheduled"
    )

    db.add(followup)

    db.commit()

    db.refresh(followup)

    return {

        "status": "success",

        "message": (
            "Follow-up automatically scheduled."
        ),

        "followup": {

            "id": followup.id,

            "client_id": followup.client_id,

            "client_name": client.name,

            "product": client.product,

            "scheduled_at": (
                followup.scheduled_at
            ),

            "status": followup.status
        }
    }
    
    
    
