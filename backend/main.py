from fastapi import FastAPI

app = FastAPI(title="Aria Voice Agent", version="0.1.0")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "aria"}
