from dotenv import load_dotenv

load_dotenv(override=True)

from src.app import app

if __name__ == "__main__":
    import os

    import uvicorn

    try:
        uvicorn.run(
            app,
            host=os.getenv("SERVER_HOST") or "0.0.0.0",
            port=int(os.getenv("SERVER_PORT") or 8000),
        )
    except KeyboardInterrupt:
        pass
