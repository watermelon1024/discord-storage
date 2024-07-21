import os

from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    import uvicorn

    from src.app import app

    try:
        uvicorn.run(
            app,
            host=os.getenv("SERVER_HOST") or "127.0.0.1",
            port=int(os.getenv("SERVER_PORT") or 8000),
        )
    except KeyboardInterrupt:
        pass
