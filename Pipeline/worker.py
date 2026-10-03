from celery import Celery, chain
import time
from database import SessionLocal
from models import ProcessedEmail

# 1. Initialize the Celery app FIRST
app = Celery('email_pipeline', broker='redis://localhost:6379/0')

# 2. Define the tasks
@app.task
def clean_email_text(raw_email):
    print(f"1. Cleaning email text for: {raw_email}")
    time.sleep(1) # Simulate parsing
    return f"Cleaned_{raw_email}"

@app.task
def run_ai_classification(cleaned_text):
    print(f"2. Running AI models on: {cleaned_text}")
    time.sleep(2) # Simulate AI processing
    return {"category": "Invoice", "priority": "High", "text": cleaned_text}

@app.task
def save_to_database(ai_results):
    print(f"3. Saving final results to DB: {ai_results}")
    
    db = SessionLocal()
    try:
        new_record = ProcessedEmail(
            original_subject="Invoice #99230",
            cleaned_text=ai_results.get("text"),
            category=ai_results.get("category"),
            priority=ai_results.get("priority")
        )
        db.add(new_record)
        db.commit()
        print("Database insertion successful!")
    except Exception as e:
        db.rollback()
        print(f"Database error: {e}")
    finally:
        db.close()
        
    return "Pipeline Complete"
