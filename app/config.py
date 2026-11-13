import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
MAX_STEPS = int(os.getenv("MAX_STEPS", "6"))
MAX_ROWS = int(os.getenv("MAX_ROWS", "200"))
DB_PATH = os.getenv("DB_PATH", "data/demo.db")
