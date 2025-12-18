# app/config.py - Configuration Management (Ollama Edition)

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration - Ollama Free API"""
    
    # ===== OLLAMA CONFIGURATION (FREE LOCAL API) =====
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = "qwen2.5:3b"  # FREE - ~2.5GB download
    
    # ===== SUPABASE CONFIGURATION =====
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    
    # ===== SERVER CONFIGURATION =====
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"
    
    # ===== SESSION CONFIGURATION =====
    SESSION_TIMEOUT_SECONDS = 1800  # 30 minutes
    MAX_CONTEXT_MESSAGES = 10  # Limit context for faster inference
    
    @classmethod
    def validate(cls):
        """Validate required environment variables"""
        required = ["SUPABASE_URL", "SUPABASE_KEY"]
        missing = [var for var in required if not getattr(cls, var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {missing}")
        
        print(f"✓ Config validated")
        print(f"  - Ollama: {cls.OLLAMA_URL}")
        print(f"  - Model: {cls.OLLAMA_MODEL}")
        print(f"  - Supabase: {cls.SUPABASE_URL[:30]}...")