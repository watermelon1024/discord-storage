import os

from dotenv import load_dotenv

from src.app import app

load_dotenv(override=True)

if __name__ == "__main__":
    import uvicorn

    try:
        uvicorn.run(
            app,
            host=os.getenv("SERVER_HOST") or "0.0.0.0",
            port=int(os.getenv("SERVER_PORT") or 8000),
        )
    except KeyboardInterrupt:
        pass
