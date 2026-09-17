from fastapi import FastAPI

app = FastAPI(
    title="Project Vigyan API",
    version="0.1.0",
)


@app.get("/")
def root():
    return {"message": "Project Vigyan API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}
