from datetime import datetime
import os

from fastapi import (
    FastAPI,
    Depends,
    HTTPException
)

from pydantic import BaseModel

from sqlalchemy.orm import Session

from groq import Groq

from database import (
    Base,
    engine,
    get_db
)

from models import (
    Client,
    FollowUp,
    CallLog
)
    
    



# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="FollowUpAI",
    description="AI-powered automated follow-up system",
    version="1.1.0"
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

    # -----------------------------------------------------
    # FIND FOLLOW-UP
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # FIND CLIENT
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # GENERATE SCRIPT
    # -----------------------------------------------------

    try:

        script = generate_followup_script(
            client
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

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

        # -------------------------------------------------
        # UPDATE STATUS
        # -------------------------------------------------

        followup.status = "processed"

        # -------------------------------------------------
        # STORE RESULT
        # -------------------------------------------------

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
    # SAVE DATABASE
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

# =========================================================
# TEST VOICE CALL - DRY RUN
# =========================================================

@app.post("/followups/{followup_id}/call-test")
def test_voice_call(
    followup_id: int,
    db: Session = Depends(get_db)
):

    # -----------------------------------------------------
    # FIND FOLLOW-UP
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # FIND CLIENT
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # GENERATE AI SCRIPT
    # -----------------------------------------------------

    try:

        script = generate_followup_script(
            client
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    # -----------------------------------------------------
    # DRY-RUN RESPONSE
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # FIND FOLLOW-UP
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # FIND CLIENT
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # CREATE LOG
    # -----------------------------------------------------

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
    
    
    
