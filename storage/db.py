from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

engine = create_engine("sqlite:///purchase_saas.db", future=True)
SessionLocal = sessionmaker(bind=engine, future=True)

def init_db():
    Base.metadata.create_all(bind=engine)
