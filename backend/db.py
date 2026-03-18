import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os

# -------------------------------------------------
# Load environment variables from .env
# -------------------------------------------------
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# -------------------------------------------------
# Database configuration
# -------------------------------------------------
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}

# -------------------------------------------------
# Connection helper
# -------------------------------------------------
def get_db_conn():
    """
    Returns a new PostgreSQL connection.
    Caller must close it.
    """
    return psycopg2.connect(
        **DB_CONFIG,
        cursor_factory=RealDictCursor
    )
