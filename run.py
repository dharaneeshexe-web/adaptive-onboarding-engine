import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import app object directly — bypasses uvicorn's string-based importer
from main import app
import uvicorn

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
