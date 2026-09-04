from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey
)

from sqlalchemy.orm import relationship

from database import Base


# =========================================================
# CLIENT MODEL
# =========================================================

class Client(Base):

    __tablename__ = "clients"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String,
        nullable=False
    )

    phone = Column(
        String,
        nullable=False
    )

    product = Column(
        String,
        nullable=True
    )

    notes = Column(
        String,
        nullable=True
    )

    followups = relationship(
        "FollowUp",
        back_populates="client",
        cascade="all, delete-orphan"
    )


# =========================================================
# FOLLOW-UP MODEL
# =========================================================

class FollowUp(Base):

    __tablename__ = "followups"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    client_id = Column(
        Integer,
        ForeignKey("clients.id"),
        nullable=False
    )

    scheduled_at = Column(
        DateTime,
        nullable=False
    )

    status = Column(
        String,
        default="scheduled"
    )

    client = relationship(
        "Client",
        back_populates="followups"
    )
