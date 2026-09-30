from sqlalchemy import Column, Integer, String, Text
from database import Base

class ProcessedEmail(Base):
    __tablename__ = "processed_emails"

    id = Column(Integer, primary_key=True, index=True)
    original_subject = Column(String, index=True)
    cleaned_text = Column(Text)
    category = Column(String)
    priority = Column(String)
