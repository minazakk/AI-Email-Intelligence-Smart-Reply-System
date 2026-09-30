from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "postgresql+psycopg2://faizan:admin123@localhost/ai_email_db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Import the models so SQLAlchemy knows they exist before creating tables
import models 

if __name__ == "__main__":
    try:
        # This command creates any tables that don't already exist
        Base.metadata.create_all(bind=engine)
        print("Successfully connected and created tables in ai_email_db")
    except Exception as e:
        print(f"Connection failed: {e}")
