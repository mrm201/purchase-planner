from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    runs = relationship("Run", back_populates="user")

class Run(Base):
    __tablename__ = "runs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    params_json = Column(Text)      # JSON string
    source_files = Column(Text)     # JSON string of filenames/hashes
    user = relationship("User", back_populates="runs")
    lines = relationship("RunLine", back_populates="run", cascade="all, delete-orphan")

class RunLine(Base):
    __tablename__ = "run_lines"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    sku = Column(String, index=True)
    item_name = Column(String)
    supplier = Column(String)
    demand = Column(Float)
    order_qty = Column(Float)
    unit_cost = Column(Float)
    total_cost = Column(Float)
    notes = Column(Text)
    metadata_json = Column(Text)    # optional JSON for MOQ/multiples/overrides
    run = relationship("Run", back_populates="lines")
