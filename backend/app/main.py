from fastapi import FastAPI

from app.routers.auth import router as auth_router
from app.routers.schools import router as schools_router
from app.routers.class_divisions import router as class_divisions_router
from app.routers.students import router as students_router
from app.routers.teaching_sessions import router as teaching_sessions_router
from app.routers.attendance import router as attendance_router
from app.routers.engagement import router as engagement_router

app = FastAPI(
    title="Project Vigyan API",
    version="0.1.0",
)

app.include_router(auth_router)
app.include_router(schools_router)
app.include_router(class_divisions_router)
app.include_router(students_router)
app.include_router(teaching_sessions_router)
app.include_router(attendance_router)
app.include_router(engagement_router)

@app.get("/")
def root():
    return {"message": "Project Vigyan API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}
