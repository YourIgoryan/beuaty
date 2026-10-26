from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from app.config import settings

database_url = settings.database_url.strip()
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[int] = mapped_column(Integer)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Master(Base):
    __tablename__ = "masters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    specialty: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkExample(Base):
    __tablename__ = "work_examples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    username: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    master_id: Mapped[int | None] = mapped_column(ForeignKey("masters.id"), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(30), default="confirmed", index=True)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    client: Mapped[Client] = relationship()
    service: Mapped[Service] = relationship()
    master: Mapped[Master | None] = relationship()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        services = (await session.execute(select(Service))).scalars().all()
        if not services:
            session.add_all([
                Service(name="Женская стрижка", description="Стрижка и укладка", price=1800, duration_minutes=60),
                Service(name="Мужская стрижка", description="Стрижка машинкой или ножницами", price=1000, duration_minutes=45),
                Service(name="Окрашивание", description="Стоимость уточняется по длине волос", price=3500, duration_minutes=150),
                Service(name="Маникюр", description="Маникюр без покрытия", price=1500, duration_minutes=60),
            ])
        masters = (await session.execute(select(Master))).scalars().all()
        existing_names = {m.name for m in masters}
        for master in masters:
            if master.name == "Любой свободный мастер":
                master.active = False
        demo_masters = [
            Master(name="Анна", specialty="Стрижки и укладки"),
            Master(name="Мария", specialty="Окрашивание"),
            Master(name="Елена", specialty="Маникюр"),
        ]
        for master in demo_masters:
            if master.name not in existing_names:
                session.add(master)

        works = (await session.execute(select(WorkExample))).scalars().all()
        if not works:
            session.add_all([
                WorkExample(
                    title="Укладка и уход",
                    description="Демонстрационный пример. Замените на фото работ своего салона.",
                    image_url="https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?w=1000&auto=format&fit=crop&q=85",
                ),
                WorkExample(
                    title="Стиль и окрашивание",
                    description="Пример оформления портфолио мастера.",
                    image_url="https://images.unsplash.com/photo-1562322140-8baeececf3df?w=1000&auto=format&fit=crop&q=85",
                ),
                WorkExample(
                    title="Маникюр и детали",
                    description="Демонстрационное фото — добавьте реальные работы.",
                    image_url="https://images.unsplash.com/photo-1604654894610-df63bc536371?w=1000&auto=format&fit=crop&q=85",
                ),
            ])
        await session.commit()
