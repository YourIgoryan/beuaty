from fastapi import FastAPI
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal, Service, init_db

app = FastAPI(title=f"{settings.salon_name} API", version="0.1.0")

@app.on_event("startup")
async def startup() -> None:
    await init_db()

@app.get("/health")
async def health():
    return {"status": "ok", "service": "beauty-salon-bot"}

@app.get("/api/services")
async def services():
    async with SessionLocal() as session:
        items = (await session.execute(select(Service).where(Service.active.is_(True)).order_by(Service.id))).scalars().all()
        return [{"id": s.id, "name": s.name, "description": s.description, "price": s.price,
                 "duration_minutes": s.duration_minutes} for s in items]
