from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import os

try:
    from normalizer import normalize_csv
    from detector import analyze_transactions
    from models import AnalysisResponse
except ImportError:
    from .normalizer import normalize_csv
    from .detector import analyze_transactions
    from .models import AnalysisResponse


app = FastAPI(
    title="LeakAI API",
    description="Deterministic Financial Anomaly & Leak Detection Engine",
    version="1.0.0"
)

# Enable CORS for local Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEMO_CSV_PATH = os.path.join(os.path.dirname(__file__), "demo_transactions.csv")

@app.get("/")
def read_root():
    return {"status": "online", "system": "LeakAI Engine v1.0"}

@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_file(file: UploadFile = File(...)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")
    
    try:
        contents = await file.read()
        norm_df = normalize_csv(contents)
        summary, transactions = analyze_transactions(norm_df)
        
        return AnalysisResponse(
            summary=summary,
            transactions=transactions,
            filename=file.filename,
            processed_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to process CSV: {str(e)}")

@app.get("/api/demo", response_model=AnalysisResponse)
def run_demo():
    if not os.path.exists(DEMO_CSV_PATH):
        raise HTTPException(status_code=404, detail="Demo CSV file not found.")
    
    try:
        with open(DEMO_CSV_PATH, "rb") as f:
            contents = f.read()
        norm_df = normalize_csv(contents)
        summary, transactions = analyze_transactions(norm_df)
        
        return AnalysisResponse(
            summary=summary,
            transactions=transactions,
            filename="demo_transactions.csv",
            processed_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Demo execution failed: {str(e)}")
