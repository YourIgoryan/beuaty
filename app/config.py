from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    admin_ids: str = Field(default="", alias="ADMIN_IDS")
    salon_name: str = Field(default="Beauty Studio", alias="SALON_NAME")
    salon_description: str = Field(default="Уход, красота и хорошее настроение", alias="SALON_DESCRIPTION")
    salon_address: str = Field(default="Адрес уточняется", alias="SALON_ADDRESS")
    salon_phone: str = Field(default="", alias="SALON_PHONE")
    timezone: str = Field(default="Europe/Moscow", alias="TIMEZONE")
    database_url: str = Field(default="sqlite+aiosqlite:///./beauty_salon.db", alias="DATABASE_URL")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    booking_days_ahead: int = Field(default=21, alias="BOOKING_DAYS_AHEAD")
    open_time: str = Field(default="10:00", alias="OPEN_TIME")
    close_time: str = Field(default="20:00", alias="CLOSE_TIME")
    slot_step_minutes: int = Field(default=30, alias="SLOT_STEP_MINUTES")
    reminder_minutes: int = Field(default=120, alias="REMINDER_MINUTES")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

    @property
    def admin_id_set(self) -> set[int]:
        result: set[int] = set()
        for item in self.admin_ids.split(","):
            item = item.strip()
            if item.isdigit():
                result.add(int(item))
        return result


settings = Settings()
