"""Auto-loads .env file"""
from pathlib import Path
from dotenv import load_dotenv

# Load .env when config package is imported
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path, override=True)

from config.settings import settings, get_settings

__all__ = ['settings', 'get_settings']
