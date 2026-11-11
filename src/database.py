"""Database connection, models, and service functions for IEPCI Quote Assistant.
Uses SQLite locally (stored at data/quotes.db) via SQLAlchemy.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# ---------------------------------------------------------------- Database Path & Engine
BASE_DIR = Path(__file__).resolve().parent.parent
DB_DIR = BASE_DIR / "data"
DB_PATH = DB_DIR / "quotes.db"

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ---------------------------------------------------------------- Tables / Models
class CatalogueItem(Base):
    """Stores all supplier catalogue rows (ABB, Schneider, Lucy, Siemens, etc.)."""
    __tablename__ = "catalogue_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier = Column(String(100), nullable=False)
    source_sheet = Column(String(100))
    category = Column(String(100))
    part_code = Column(String(100), nullable=False)
    part_code_key = Column(String(100), index=True, nullable=False)
    description = Column(Text)
    rating_a = Column(Float, nullable=True)
    poles = Column(Integer, nullable=True)
    breaking_capacity = Column(String(50), nullable=True)
    specs = Column(Text, nullable=True)
    price_inr = Column(Float, nullable=True)
    price_status = Column(String(50), default="ok")
    stocked = Column(String(50), nullable=True)
    page = Column(String(50), nullable=True)


class RFQRecord(Base):
    """Stores RFQ metadata (Customer, RFQ #, dates, status)."""
    __tablename__ = "rfqs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rfq_number = Column(String(100), index=True)
    customer_name = Column(String(200))
    rfq_date = Column(String(50), nullable=True)
    due_date = Column(String(50), nullable=True)
    currency = Column(String(20), default="INR")
    source_filename = Column(String(255))
    status = Column(String(50), default="DRAFT")  # DRAFT, IN_REVIEW, APPROVED, SENT
    notes = Column(Text, nullable=True)
    header_json = Column(Text, nullable=True)      # Stores all header fields safely
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = relationship("QuoteLineItem", back_populates="rfq", cascade="all, delete-orphan")


class QuoteLineItem(Base):
    """Stores each line item belonging to an RFQ."""
    __tablename__ = "quote_line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False, index=True)
    item_no = Column(Integer)
    raw_description = Column(Text)
    raw_part_code = Column(String(100), nullable=True)
    cleaned_part_code = Column(String(100), nullable=True)

    matched_catalogue_id = Column(Integer, ForeignKey("catalogue_items.id"), nullable=True)
    matched_supplier = Column(String(100), nullable=True)
    matched_part_code = Column(String(100), nullable=True)
    matched_description = Column(Text, nullable=True)

    quantity = Column(Float, default=1.0)
    unit = Column(String(50), default="Nos")
    list_price_inr = Column(Float, nullable=True)
    discount_pct = Column(Float, default=0.0)
    unit_rate_inr = Column(Float, nullable=True)
    total_amount_inr = Column(Float, nullable=True)

    is_rate_approved = Column(Boolean, default=False)
    review_status = Column(String(50), default="PENDING")
    review_notes = Column(Text, nullable=True)

    rfq = relationship("RFQRecord", back_populates="items")
    matched_item = relationship("CatalogueItem")


def init_db():
    """Create all tables in SQLite if they don't already exist."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    # Ensure header_json column exists
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE rfqs ADD COLUMN header_json TEXT"))
            conn.commit()
        except Exception:
            pass


# ---------------------------------------------------------------- Service Helpers
def save_rfq_record(
    header: dict,
    lines_df: pd.DataFrame,
    filename: str = "",
    status: str = "DRAFT",
    rfq_id: Optional[int] = None,
) -> int:
    """Save an RFQ and all its line items to SQLite. Updates if rfq_id is provided."""
    session = SessionLocal()
    try:
        if rfq_id:
            record = session.query(RFQRecord).filter_by(id=rfq_id).first()
            if not record:
                record = RFQRecord()
                session.add(record)
            else:
                # Remove old items to replace with updated ones
                session.query(QuoteLineItem).filter_by(rfq_id=rfq_id).delete()
        else:
            record = RFQRecord()
            session.add(record)

        record.customer_name = header.get("customer_name", "") or ""
        record.rfq_number = header.get("rfq_number", "") or ""
        record.rfq_date = header.get("rfq_date", "") or ""
        record.due_date = header.get("due_date", "") or ""
        record.currency = header.get("currency", "INR") or "INR"
        record.source_filename = filename or ""
        record.status = status
        record.header_json = json.dumps(header)
        session.flush()

        if lines_df is not None and not lines_df.empty:
            for idx, row in lines_df.iterrows():
                item = QuoteLineItem(
                    rfq_id=record.id,
                    item_no=int(row.get("line_no", idx + 1) or idx + 1) if str(row.get("line_no", "")).isdigit() else idx + 1,
                    raw_description=str(row.get("description", "")),
                    raw_part_code=str(row.get("part_code", "")),
                    cleaned_part_code=str(row.get("part_code_key", "")),
                    matched_supplier=str(row.get("make", "") or row.get("supplier", "")),
                    quantity=float(row.get("qty", 1.0) or 1.0) if pd.notna(row.get("qty")) and str(row.get("qty")).replace(".", "", 1).isdigit() else 1.0,
                    unit=str(row.get("unit", "Nos")),
                    list_price_inr=float(row.get("list_price_inr")) if pd.notna(row.get("list_price_inr")) else None,
                    unit_rate_inr=float(row.get("unit_rate")) if pd.notna(row.get("unit_rate")) else None,
                    is_rate_approved=bool(row.get("price_approved", False)),
                    review_status=str(row.get("price_note", "")),
                    review_notes=json.dumps(row.to_dict(), default=str),
                )
                session.add(item)

        session.commit()
        return record.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def list_saved_rfqs() -> List[dict]:
    """Return all saved RFQs with summary counts for display in tables."""
    session = SessionLocal()
    try:
        records = session.query(RFQRecord).order_by(RFQRecord.updated_at.desc()).all()
        result = []
        for r in records:
            total_items = len(r.items)
            approved_count = sum(1 for it in r.items if it.is_rate_approved)
            subtotal = sum(
                (it.quantity or 1.0) * (it.unit_rate_inr or 0.0)
                for it in r.items
                if it.is_rate_approved and it.unit_rate_inr
            )
            result.append({
                "id": r.id,
                "rfq_number": r.rfq_number or "Untitled RFQ",
                "customer_name": r.customer_name or "Unknown Customer",
                "filename": r.source_filename or "",
                "status": r.status or "DRAFT",
                "items_count": total_items,
                "approved_count": approved_count,
                "subtotal_inr": subtotal,
                "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M") if r.updated_at else "",
            })
        return result
    finally:
        session.close()


def load_rfq_record(rfq_id: int) -> Tuple[dict, pd.DataFrame, str]:
    """Retrieve an RFQ by ID. Returns (header, lines_df, filename)."""
    session = SessionLocal()
    try:
        record = session.query(RFQRecord).filter_by(id=rfq_id).first()
        if not record:
            return {}, pd.DataFrame(), ""

        header = json.loads(record.header_json) if record.header_json else {
            "customer_name": record.customer_name,
            "rfq_number": record.rfq_number,
            "rfq_date": record.rfq_date,
            "due_date": record.due_date,
            "currency": record.currency,
        }

        items = session.query(QuoteLineItem).filter_by(rfq_id=rfq_id).order_by(QuoteLineItem.item_no).all()
        rows = []
        for it in items:
            if it.review_notes:
                try:
                    row_dict = json.loads(it.review_notes)
                    rows.append(row_dict)
                    continue
                except Exception:
                    pass
            rows.append({
                "line_no": it.item_no,
                "description": it.raw_description,
                "part_code": it.raw_part_code,
                "make": it.matched_supplier,
                "qty": it.quantity,
                "unit": it.unit,
                "list_price_inr": it.list_price_inr,
                "unit_rate": it.unit_rate_inr,
                "price_approved": it.is_rate_approved,
                "price_note": it.review_status,
            })

        df = pd.DataFrame(rows) if rows else pd.DataFrame()
        return header, df, record.source_filename
    finally:
        session.close()


def delete_rfq_record(rfq_id: int) -> bool:
    """Delete an RFQ draft and its line items."""
    session = SessionLocal()
    try:
        record = session.query(RFQRecord).filter_by(id=rfq_id).first()
        if record:
            session.delete(record)
            session.commit()
            return True
        return False
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    sample_header = {"customer_name": "Test Customer Ltd", "rfq_number": "TEST-001"}
    sample_lines = pd.DataFrame([
        {"line_no": 1, "description": "MCCB 100A 3P", "qty": 2, "unit": "Nos", "unit_rate": 5000.0, "price_approved": True}
    ])
    saved_id = save_rfq_record(sample_header, sample_lines, filename="test.pdf")
    rfqs = list_saved_rfqs()
    # Clean up test record
    delete_rfq_record(saved_id)