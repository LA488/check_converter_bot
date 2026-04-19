#!/usr/bin/env python3
"""
Startup script for Render.com deployment.
Sets up webhook and then starts Gunicorn.
"""
import asyncio
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from bot import on_startup, app

async def setup():
    """Setup webhook before starting Gunicorn."""
    print("🚀 Setting up webhook...")
    await on_startup()
    print("✅ Webhook setup complete!")

if __name__ == "__main__":
    # Run webhook setup
    asyncio.run(setup())

    # Start Gunicorn
    print("🔥 Starting Gunicorn...")
    os.execvp("gunicorn", [
        "gunicorn",
        "-w", "1",
        "-b", f"0.0.0.0:{os.environ.get('PORT', 10000)}",
        "bot:app"
    ])
