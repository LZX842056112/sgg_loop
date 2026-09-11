from fastapi import FastAPI

app = FastAPI(title="My FastAPI")


@app.get("/")
async def root():
    return {"message": "Hello World"}
