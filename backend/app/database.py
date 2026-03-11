from sqlmodel import SQLModel, create_engine

DATABASE_URL = "postgresql://postgres:postgres@postgres:5432/cab_booking"

engine = create_engine(DATABASE_URL, echo=True)