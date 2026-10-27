from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.routes import router
from app.config import BASE_DIR


app = FastAPI(title="Customer Support Chat")
app.include_router(router, prefix="/api")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")