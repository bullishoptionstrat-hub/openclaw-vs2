import asyncio
import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from src.modules.market_structure_detector import MarketStructureDetector
from src.modules.fractal_validator import FractalValidator
from src.modules.algo_detection import AlgoDetector
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize modules
market_structure = MarketStructureDetector()
fractal_validator = FractalValidator()
algo_detector = AlgoDetector()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("⚡ AI Engine starting...")
    yield
    logger.info("⚡ AI Engine shutting down...")


app = FastAPI(title="Quantum Edge AI Engine", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "quantum-edge-ai-engine",
        "modules": ["market_structure", "fractal", "algo_detection", "options_flow", "macro"],
    }


@app.post("/analyze/structure")
async def analyze_structure(symbol: str, timeframe: str, candles: list):
    """Analyze market structure for BOS, CHoCH, FVG."""
    try:
        result = await market_structure.detect(symbol, timeframe, candles)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Structure analysis error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/analyze/fractal")
async def analyze_fractal(candles: list):
    """Validate 4-candle fractal patterns."""
    try:
        result = await fractal_validator.validate(candles)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Fractal analysis error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/analyze/algo")
async def analyze_algo_manipulation(symbol: str, candles: list):
    """Detect false breakouts, stop hunts, traps."""
    try:
        result = await algo_detector.detect(symbol, candles)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Algo detection error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/score/trade")
async def score_trade(confidence: dict):
    """
    Multi-confirmation trade validation.
    Input: {
        "structure": 0.85,
        "fractal": 0.90,
        "algo": 0.80,
        "options": 0.75,
        "macro": 0.70,
        "volume": 0.88
    }
    Output: Final score and recommendation
    """
    try:
        weights = {
            "structure": 0.25,
            "fractal": 0.20,
            "algo": 0.15,
            "options": 0.15,
            "macro": 0.15,
            "volume": 0.10,
        }

        final_score = sum(confidence.get(k, 0) * v for k, v in weights.items())

        return {
            "success": True,
            "final_score": final_score,
            "recommendation": "PASS" if final_score >= 0.70 else "WAIT",
            "breakdown": confidence,
        }
    except Exception as e:
        logger.error(f"Trade scoring error: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
