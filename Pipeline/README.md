# AI Email Processing Pipeline (Background Tasks)

This module handles the asynchronous background processing of incoming
emails using Celery, Redis, and PostgreSQL. It is designed to parse
emails, run AI classification models, and save the extracted
intelligence to the database without blocking the FastAPI frontend.

## Prerequisites

To run this pipeline locally, you must have the following running in
your WSL/Linux environment:

-   **Redis:** Acts as the message broker.

    ``` bash
    sudo service redis-server start
    ```

-   **PostgreSQL:** Acts as the primary database.

    ``` bash
    sudo service postgresql start
    ```

## Setup Instructions

### 1. Create the virtual environment and install dependencies

``` bash
python3 -m venv venv
source venv/bin/activate
pip install celery redis sqlalchemy psycopg2-binary
```

### 2. Initialize the database

Ensure PostgreSQL is running, then create the `ai_email_db` database.
Run the database script to generate the tables:

``` bash
python database.py
```

### 3. Start the Celery worker

Open a dedicated terminal, activate the virtual environment, and boot
the worker:

``` bash
celery -A worker worker --loglevel=info
```

## Triggering the Pipeline

To send an email through the pipeline, import the task chain and use
`.delay()`:

``` python
from worker import clean_email_text, run_ai_classification, save_to_database
from celery import chain

pipeline = chain(
    clean_email_text.s("Raw Email Data"),
    run_ai_classification.s(),
    save_to_database.s()
)
pipeline.delay()
```