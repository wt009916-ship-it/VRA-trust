"""Only locally installed console code can enable management routes."""
import os
from pathlib import Path

def enabled():
    return os.environ.get('VRA_PUBLIC_BUILD') != '1' and (Path(__file__).parent/'private_console.py').is_file()
