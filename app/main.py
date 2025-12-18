# app/main.py - Application Entry Point

from app.routes import app
from app.config import Config
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def startup():
    """Startup routine"""
    try:
        Config.validate()
        logger.info("✓ Configuration validated")
        logger.info(f"🚀 Starting Realtime AI Backend")
        logger.info(f"   Model: {Config.OLLAMA_MODEL}")
        logger.info(f"   Ollama URL: {Config.OLLAMA_URL}")
        logger.info(f"   Server: {Config.HOST}:{Config.PORT}")
    except Exception as e:
        logger.error(f"✗ Startup failed: {e}")
        raise


if __name__ == "__main__":
    import asyncio
    
    # Run startup
    asyncio.run(startup())
    
    # Start server
    logger.info(f"📡 Starting server on {Config.HOST}:{Config.PORT}")
    logger.info(f"🌐 Open http://localhost:{Config.PORT} in your browser")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
