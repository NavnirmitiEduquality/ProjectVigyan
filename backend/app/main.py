from fastapi import FastAPI

from app.routers.auth import router as auth_router

app = FastAPI(
    title="Project Vigyan API",
    version="0.1.0",
)

app.include_router(auth_router)

@app.get("/")
def root():
    return {"message": "Project Vigyan API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}
