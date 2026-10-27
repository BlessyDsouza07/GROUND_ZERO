from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler
from .db import Base, engine, SessionLocal
from .models import Event, Source
from .service import refresh, freshness_status
from .config import ADMIN_API_KEY, REFRESH_INTERVAL_MINUTES, MAX_EVENT_AGE_HOURS

scheduler = BackgroundScheduler(timezone="UTC")

def db_dep():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def scheduled_refresh():
    db = SessionLocal()
    try:
        refresh(db)
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    scheduled_refresh()  # live collection on startup; no seed loader
    scheduler.add_job(scheduled_refresh, "interval", minutes=REFRESH_INTERVAL_MINUTES, id="live_refresh", replace_existing=True)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)

app = FastAPI(title="Ground Zero Live Mangaluru Events", version="2.0.0", lifespan=lifespan)

@app.get("/health")
def health(db: Session = Depends(db_dep)):
    return {"status":"ok", "event_count": db.query(Event).count(), "live_refresh":"enabled", "seed_data":False}

@app.get("/events")
def events(db: Session = Depends(db_dep)):
    rows = db.query(Event).order_by(Event.start_at.asc()).all()
    return [{**{c.name:getattr(e,c.name) for c in Event.__table__.columns}, "freshness":freshness_status(e, MAX_EVENT_AGE_HOURS)} for e in rows]

@app.get("/events/today")
def today(db: Session = Depends(db_dep)):
    now = datetime.now(timezone.utc)
    rows = db.query(Event).filter(Event.start_at >= now.replace(hour=0,minute=0,second=0,microsecond=0)).filter(Event.start_at < now.replace(hour=0,minute=0,second=0,microsecond=0).replace(hour=23,minute=59,second=59)).all()
    return rows

@app.get("/events/upcoming")
def upcoming(db: Session = Depends(db_dep)):
    now = datetime.now(timezone.utc)
    return db.query(Event).filter(Event.start_at >= now, Event.status=="ACTIVE").order_by(Event.start_at.asc()).all()

@app.get("/events/date/{date_str}")
def by_date(date_str: str, db: Session = Depends(db_dep)):
    try:
        day = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, "Use YYYY-MM-DD")
    return db.query(Event).filter(Event.start_at >= day).filter(Event.start_at < day.replace(hour=23,minute=59,second=59)).order_by(Event.start_at.asc()).all()

@app.get("/events/{event_id}")
def event(event_id: int, db: Session = Depends(db_dep)):
    e = db.get(Event, event_id)
    if not e: raise HTTPException(404, "Event not found")
    return e

@app.get("/sources")
def sources(db: Session = Depends(db_dep)):
    return db.query(Source).all()

@app.get("/sources/health")
def source_health(db: Session = Depends(db_dep)):
    return db.query(Source).all()

@app.post("/admin/refresh")
def admin_refresh(x_admin_key: str | None = Header(default=None), db: Session = Depends(db_dep)):
    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(401, "Invalid admin key")
    return refresh(db)
