import asyncio
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import SessionLocal, Service, Master, Client, Booking, WorkExample, init_db

bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


class BookingFlow(StatesGroup):
    service = State()
    master = State()
    day = State()
    slot = State()
    phone = State()


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
        for row in rows
    ])


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [("✂️ Услуги и цены", "services"), ("📅 Записаться", "book")],
        [("🗓 Мои записи", "my_bookings"), ("📍 Контакты", "contacts")],
        [("🖼 Примеры работ", "portfolio"), ("👥 Наши мастера", "masters_public")],
    ]
    if is_admin:
        rows.append([("⚙️ Панель администратора", "admin")])
    return kb(rows)


def local_now() -> datetime:
    return datetime.now(ZoneInfo(settings.timezone)).replace(tzinfo=None, second=0, microsecond=0)


async def get_or_create_client(message: Message) -> Client:
    async with SessionLocal() as session:
        client = (await session.execute(select(Client).where(Client.telegram_id == message.from_user.id))).scalar_one_or_none()
        if client is None:
            client = Client(telegram_id=message.from_user.id,
                            name=(message.from_user.full_name or "Клиент")[:200],
                            username=(message.from_user.username or "")[:100])
            session.add(client)
            await session.commit()
            await session.refresh(client)
        else:
            client.name = (message.from_user.full_name or client.name)[:200]
            client.username = (message.from_user.username or client.username)[:100]
            await session.commit()
        return client


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await get_or_create_client(message)
    text = (f"<b>✨ {settings.salon_name}</b>\n{settings.salon_description}\n\n"
            "Выберите, что хотите сделать. Запись займёт всего пару минут.")
    await message.answer(text, reply_markup=main_menu(message.from_user.id in settings.admin_id_set))


@dp.message(Command("cancel"))
async def cancel_flow(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено. Возвращаю вас в меню.", reply_markup=main_menu(message.from_user.id in settings.admin_id_set))


@dp.callback_query(F.data == "home")
async def go_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(f"<b>✨ {settings.salon_name}</b>\n{settings.salon_description}\n\nВыберите действие:", reply_markup=main_menu(callback.from_user.id in settings.admin_id_set))
    await callback.answer()


@dp.callback_query(F.data == "contacts")
async def contacts(callback: CallbackQuery):
    phone = f"\n☎️ {settings.salon_phone}" if settings.salon_phone else ""
    await callback.message.edit_text(f"<b>📍 {settings.salon_name}</b>\n{settings.salon_address}{phone}\n\nДля записи нажмите кнопку ниже.",
                                     reply_markup=kb([[('📅 Записаться', 'book')], [('⬅️ В меню', 'home')]]))
    await callback.answer()


@dp.callback_query(F.data == "portfolio")
async def portfolio(callback: CallbackQuery):
    async with SessionLocal() as session:
        works = (await session.execute(select(WorkExample).where(WorkExample.active.is_(True)).order_by(WorkExample.id))).scalars().all()
    await callback.answer()
    if not works:
        await callback.message.answer("Портфолио пока пустое. Скоро здесь появятся примеры работ.")
        return
    await callback.message.answer(f"<b>🖼 Примеры работ · {settings.salon_name}</b>\nДемонстрационные фото можно заменить на реальные работы салона.")
    for work in works:
        try:
            await bot.send_photo(callback.from_user.id, photo=work.image_url,
                                 caption=f"<b>{work.title}</b>\n{work.description}")
        except Exception as exc:
            print(f"Portfolio image {work.id} could not be sent: {exc}")
            await callback.message.answer(f"<b>{work.title}</b>\n{work.description}\n{work.image_url}")
    await callback.message.answer("Выберите следующий шаг:", reply_markup=kb([[('📅 Записаться', 'book')], [('⬅️ В меню', 'home')]]))


@dp.callback_query(F.data == "masters_public")
async def masters_public(callback: CallbackQuery):
    async with SessionLocal() as session:
        masters = (await session.execute(select(Master).where(Master.active.is_(True)).order_by(Master.id))).scalars().all()
    if not masters:
        text = "Информация о мастерах скоро появится."
    else:
        text = "<b>👥 Наши мастера</b>\n\n" + "\n\n".join(
            f"<b>{m.name}</b>\n{m.specialty or 'Специализация уточняется'}" for m in masters)
    await callback.message.edit_text(text, reply_markup=kb([[('📅 Записаться', 'book')], [('🖼 Примеры работ', 'portfolio')], [('⬅️ В меню', 'home')]]))
    await callback.answer()


@dp.callback_query(F.data == "services")
async def services(callback: CallbackQuery):
    async with SessionLocal() as session:
        items = (await session.execute(select(Service).where(Service.active.is_(True)).order_by(Service.id))).scalars().all()
    if not items:
        text = "Пока нет доступных услуг. Напишите администратору, чтобы уточнить детали."
    else:
        parts = ["<b>✂️ Услуги и цены</b>\n"]
        for service in items:
            parts.append(f"<b>{service.name}</b> — {service.price:,} ₽\n⏱ {service.duration_minutes} мин."
                         .replace(',', ' ') + (f"\n{service.description}" if service.description else ""))
        text = "\n\n".join(parts)
    await callback.message.edit_text(text, reply_markup=kb([[('📅 Записаться', 'book')], [('⬅️ В меню', 'home')]]))
    await callback.answer()


@dp.callback_query(F.data == "book")
async def begin_booking(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with SessionLocal() as session:
        items = (await session.execute(select(Service).where(Service.active.is_(True)).order_by(Service.id))).scalars().all()
    if not items:
        await callback.answer("Услуги пока не добавлены", show_alert=True)
        return
    rows = [[(f"{s.name} · {s.price:,} ₽".replace(',', ' '), f"svc:{s.id}")] for s in items]
    rows.append([("⬅️ В меню", "home")])
    await state.set_state(BookingFlow.service)
    await callback.message.edit_text("<b>Шаг 1 из 4 · Выберите услугу</b>", reply_markup=kb(rows))
    await callback.answer()


@dp.callback_query(BookingFlow.service, F.data.startswith("svc:"))
async def choose_service(callback: CallbackQuery, state: FSMContext):
    service_id = int(callback.data.split(':')[1])
    async with SessionLocal() as session:
        service = await session.get(Service, service_id)
        masters = (await session.execute(select(Master).where(Master.active.is_(True)).order_by(Master.id))).scalars().all()
    if not service or not service.active or not masters:
        await callback.answer("Услуга или мастер больше недоступны. Начните запись заново.", show_alert=True)
        await state.clear()
        return
    await state.update_data(service_id=service.id)
    rows = [[(f"{m.name} · {m.specialty}" if m.specialty else m.name, f"master:{m.id}")] for m in masters]
    rows.append([("Неважно, кто свободен", "master:any")])
    rows.append([("⬅️ Назад", "book"), ("Отмена", "home")])
    await state.set_state(BookingFlow.master)
    await callback.message.edit_text(f"<b>Шаг 2 из 4 · Выберите мастера</b>\n\n{service.name} · {service.price:,} ₽".replace(',', ' '), reply_markup=kb(rows))
    await callback.answer()


@dp.callback_query(BookingFlow.master, F.data.startswith("master:"))
async def choose_master(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(':', 1)[1]
    await state.update_data(master_id=None if value == 'any' else int(value))
    today = local_now().date()
    rows = []
    for offset in range(settings.booking_days_ahead + 1):
        d = today + timedelta(days=offset)
        if d.weekday() < 7:
            label = "Сегодня" if offset == 0 else "Завтра" if offset == 1 else d.strftime('%d.%m · %a')
            rows.append([(label, f"day:{d.isoformat()}")])
    rows.append([("⬅️ Назад", "book"), ("Отмена", "home")])
    await state.set_state(BookingFlow.day)
    await callback.message.edit_text("<b>Шаг 3 из 4 · Выберите дату</b>", reply_markup=kb(rows))
    await callback.answer()


async def available_slots(service_id: int, master_id: int | None, day: date) -> list[datetime]:
    async with SessionLocal() as session:
        service = await session.get(Service, service_id)
        if service is None:
            return []
        stmt = select(Booking).where(
            Booking.status == 'confirmed',
            Booking.starts_at < datetime.combine(day, time(23, 59)),
            Booking.ends_at > datetime.combine(day, time(0, 0)),
        )
        bookings = (await session.execute(stmt)).scalars().all()
        if master_id is not None:
            bookings = [b for b in bookings if b.master_id == master_id]
        else:
            masters = (await session.execute(select(Master).where(Master.active.is_(True)))).scalars().all()
            available_master_ids = {m.id for m in masters}
            if not available_master_ids:
                return []
    start_h, start_m = map(int, settings.open_time.split(':'))
    end_h, end_m = map(int, settings.close_time.split(':'))
    cursor = datetime.combine(day, time(start_h, start_m))
    closing = datetime.combine(day, time(end_h, end_m))
    now = local_now()
    slots: list[datetime] = []
    step = max(15, settings.slot_step_minutes)
    while cursor + timedelta(minutes=service.duration_minutes) <= closing:
        end = cursor + timedelta(minutes=service.duration_minutes)
        overlapping = [b for b in bookings if cursor < b.ends_at and end > b.starts_at]
        if master_id is not None:
            has_capacity = not overlapping
        else:
            busy_master_ids = {b.master_id for b in overlapping if b.master_id is not None}
            if any(b.master_id is None for b in overlapping):
                busy_master_ids = set(available_master_ids)
            has_capacity = bool(available_master_ids - busy_master_ids)
        if cursor > now and has_capacity:
            slots.append(cursor)
        cursor += timedelta(minutes=step)
    return slots


@dp.callback_query(BookingFlow.day, F.data.startswith("day:"))
async def choose_day(callback: CallbackQuery, state: FSMContext):
    day = date.fromisoformat(callback.data.split(':', 1)[1])
    data = await state.get_data()
    slots = await available_slots(data['service_id'], data.get('master_id'), day)
    if not slots:
        await callback.answer("На эту дату свободного времени нет. Выберите другой день.", show_alert=True)
        return
    rows = []
    for i in range(0, len(slots), 3):
        rows.append([(slot.strftime('%H:%M'), f"slot:{slot.isoformat()}") for slot in slots[i:i + 3]])
    rows.append([("⬅️ Назад", "book"), ("Отмена", "home")])
    await state.update_data(day=day.isoformat())
    await state.set_state(BookingFlow.slot)
    await callback.message.edit_text(f"<b>Шаг 4 из 4 · Выберите время</b>\n{day.strftime('%d.%m.%Y')}", reply_markup=kb(rows))
    await callback.answer()


@dp.callback_query(BookingFlow.slot, F.data.startswith("slot:"))
async def choose_slot(callback: CallbackQuery, state: FSMContext):
    start = datetime.fromisoformat(callback.data.split(':', 1)[1])
    data = await state.get_data()
    async with SessionLocal() as session:
        service = await session.get(Service, data['service_id'])
        master = await session.get(Master, data['master_id']) if data.get('master_id') else None
    await state.update_data(starts_at=start.isoformat())
    await state.set_state(BookingFlow.phone)
    await callback.message.edit_text("Почти готово! Для подтверждения записи нужен ваш номер телефона.")
    contact_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером телефона", request_contact=True)],
                  [KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Поделитесь контактом или введите номер",
    )
    await callback.message.answer(
        "Нажмите кнопку ниже, чтобы отправить номер, привязанный к Telegram. Можно также ввести номер вручную, например +7 900 123-45-67.",
        reply_markup=contact_keyboard,
    )
    await callback.answer()


async def show_booking_preview(message: Message, state: FSMContext, phone: str) -> None:
    data = await state.get_data()
    start = datetime.fromisoformat(data['starts_at'])
    async with SessionLocal() as session:
        client = (await session.execute(select(Client).where(Client.telegram_id == message.from_user.id))).scalar_one_or_none()
        if client is None:
            client = Client(telegram_id=message.from_user.id, name=message.from_user.full_name or "Клиент",
                            username=message.from_user.username or "")
            session.add(client)
        client.phone = phone[:50]
        await session.commit()
        service = await session.get(Service, data['service_id'])
        master = await session.get(Master, data['master_id']) if data.get('master_id') else None
    if service is None:
        await state.clear()
        await message.answer("Услуга больше недоступна. Начните запись заново.", reply_markup=ReplyKeyboardRemove())
        return
    text = (f"<b>Проверьте запись</b>\n\nУслуга: {service.name}\nМастер: {master.name if master else 'Любой свободный'}\n"
            f"Дата: {start.strftime('%d.%m.%Y')}\nВремя: {start.strftime('%H:%M')}\nТелефон: {phone}\n"
            f"Стоимость: {service.price:,} ₽".replace(',', ' '))
    await state.update_data(phone=phone)
    await message.answer(text, reply_markup=ReplyKeyboardRemove())
    await message.answer("Всё верно?", reply_markup=kb([[('✅ Подтвердить запись', 'confirm_booking')], [('⬅️ В меню', 'home')]]))


@dp.message(BookingFlow.phone, F.contact)
async def receive_phone_contact(message: Message, state: FSMContext):
    contact = message.contact
    if contact.user_id and contact.user_id != message.from_user.id:
        await message.answer("Пожалуйста, отправьте именно свой контакт через кнопку или введите номер вручную.")
        return
    await show_booking_preview(message, state, contact.phone_number)


@dp.message(BookingFlow.phone, F.text)
async def receive_phone_text(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if value.lower() == "отмена":
        await state.clear()
        await message.answer("Запись отменена.", reply_markup=ReplyKeyboardRemove())
        await message.answer("Главное меню", reply_markup=main_menu(message.from_user.id in settings.admin_id_set))
        return
    digits = ''.join(ch for ch in value if ch.isdigit())
    if len(digits) < 7 or len(digits) > 15:
        await message.answer("Не удалось распознать номер. Введите номер с кодом страны, например +7 900 123-45-67, или нажмите кнопку отправки контакта.")
        return
    await show_booking_preview(message, state, value)


@dp.callback_query(F.data == "confirm_booking")
async def confirm_booking(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('starts_at'):
        await callback.answer("Сессия записи истекла. Начните заново.", show_alert=True)
        await state.clear()
        return
    start = datetime.fromisoformat(data['starts_at'])
    async with SessionLocal() as session:
        client = (await session.execute(select(Client).where(Client.telegram_id == callback.from_user.id))).scalar_one_or_none()
        if client is None:
            client = Client(telegram_id=callback.from_user.id, name=callback.from_user.full_name or "Клиент", username=callback.from_user.username or "")
            session.add(client)
            await session.flush()
        service = await session.get(Service, data['service_id'])
        if service is None:
            await callback.answer("Услуга больше недоступна", show_alert=True)
            await state.clear()
            return
        master_id = data.get('master_id')
        # Re-check availability at commit time; for "any master", allocate a specific free master.
        end = start + timedelta(minutes=service.duration_minutes)
        stmt = select(Booking).where(Booking.status == 'confirmed', Booking.starts_at < end, Booking.ends_at > start)
        overlapping = (await session.execute(stmt)).scalars().all()
        if master_id is not None:
            conflict = next((b for b in overlapping if b.master_id == master_id or b.master_id is None), None)
            if conflict:
                await callback.answer("Это время уже заняли. Начните запись заново.", show_alert=True)
                await state.clear()
                return
        else:
            masters = (await session.execute(select(Master).where(Master.active.is_(True)).order_by(Master.id))).scalars().all()
            busy_ids = {b.master_id for b in overlapping if b.master_id is not None}
            if any(b.master_id is None for b in overlapping):
                busy_ids = {m.id for m in masters}
            free_master = next((m for m in masters if m.id not in busy_ids), None)
            if free_master is None:
                await callback.answer("Это время уже заняли. Выберите другой слот.", show_alert=True)
                await state.clear()
                return
            master_id = free_master.id
        booking = Booking(client_id=client.id, service_id=service.id, master_id=master_id,
                          starts_at=start, ends_at=end, status='confirmed')
        session.add(booking)
        await session.commit()
        booking_id = booking.id
        master = await session.get(Master, master_id) if master_id else None
        admin_ids = settings.admin_id_set
        client_name = client.name
        client_phone = client.phone
        service_name = service.name
        price = service.price
    await state.clear()
    await callback.message.edit_text(
        f"<b>Запись №{booking_id} подтверждена!</b>\n\n{service_name}\n{start.strftime('%d.%m.%Y')} в {start.strftime('%H:%M')}\nМастер: {master.name if master else 'Не назначен'}\nТелефон: {client_phone}\nСтоимость: {price:,} ₽\n\nЖдём вас!".replace(',', ' '),
        reply_markup=kb([[('🗓 Мои записи', 'my_bookings')], [('⬅️ В меню', 'home')]]))
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, f"🆕 <b>Новая запись №{booking_id}</b>\nКлиент: {client_name} (@{callback.from_user.username or 'нет username'})\nТелефон: {client_phone or 'не указан'}\nУслуга: {service_name}\nДата: {start.strftime('%d.%m.%Y %H:%M')}\nМастер: {master.name if master else 'Не назначен'}")
        except Exception:
            pass
    await callback.answer()


@dp.callback_query(F.data == "my_bookings")
async def my_bookings(callback: CallbackQuery):
    async with SessionLocal() as session:
        client = (await session.execute(select(Client).where(Client.telegram_id == callback.from_user.id))).scalar_one_or_none()
        bookings = []
        if client:
            bookings = (await session.execute(select(Booking).options(selectinload(Booking.service), selectinload(Booking.master))
                          .where(Booking.client_id == client.id, Booking.status == 'confirmed', Booking.starts_at >= local_now())
                          .order_by(Booking.starts_at))).scalars().all()
    if not bookings:
        text = "У вас пока нет предстоящих записей."
        rows = [[('📅 Записаться', 'book')], [('⬅️ В меню', 'home')]]
    else:
        text = "<b>🗓 Ваши записи</b>\n\n" + "\n\n".join(
            f"№{b.id} · {b.service.name}\n{b.starts_at.strftime('%d.%m.%Y в %H:%M')}\nМастер: {b.master.name if b.master else 'Любой свободный'}"
            for b in bookings)
        rows = [[(f"❌ Отменить №{b.id}", f"cancel_booking:{b.id}")] for b in bookings]
        rows.append([('📅 Новая запись', 'book')])
        rows.append([('⬅️ В меню', 'home')])
    await callback.message.edit_text(text, reply_markup=kb(rows))
    await callback.answer()


@dp.callback_query(F.data.startswith("cancel_booking:"))
async def cancel_booking(callback: CallbackQuery):
    booking_id = int(callback.data.split(':')[1])
    async with SessionLocal() as session:
        client = (await session.execute(select(Client).where(Client.telegram_id == callback.from_user.id))).scalar_one_or_none()
        booking = await session.get(Booking, booking_id)
        if not client or not booking or booking.client_id != client.id or booking.status != 'confirmed':
            await callback.answer("Не удалось отменить запись", show_alert=True)
            return
        booking.status = 'cancelled'
        await session.commit()
    await callback.answer("Запись отменена")
    await my_bookings(callback)


async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id not in settings.admin_id_set:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("<b>⚙️ Панель администратора</b>\n\nВыберите раздел:", reply_markup=kb([
        [('📋 Записи на сегодня', 'admin_today')],
        [('✂️ Услуги и цены', 'admin_services')],
        [('👥 Мастера', 'admin_masters')],
        [('⬅️ В меню', 'home')],
    ]))
    await callback.answer()


@dp.callback_query(F.data == "admin")
async def admin_open(callback: CallbackQuery):
    await admin_panel(callback)


@dp.callback_query(F.data == "admin_today")
async def admin_today(callback: CallbackQuery):
    if callback.from_user.id not in settings.admin_id_set:
        await callback.answer("Нет доступа", show_alert=True)
        return
    today = local_now().date()
    start, end = datetime.combine(today, time.min), datetime.combine(today, time.max)
    async with SessionLocal() as session:
        bookings = (await session.execute(select(Booking).options(selectinload(Booking.client), selectinload(Booking.service), selectinload(Booking.master))
                      .where(Booking.starts_at >= start, Booking.starts_at <= end, Booking.status == 'confirmed')
                      .order_by(Booking.starts_at))).scalars().all()
    if not bookings:
        text = "На сегодня подтверждённых записей нет."
    else:
        text = "<b>📋 Записи на сегодня</b>\n\n" + "\n\n".join(
            f"<b>{b.starts_at.strftime('%H:%M')} · №{b.id}</b>\n{b.service.name} — {b.service.price:,} ₽\nКлиент: {b.client.name}\nТелефон: {b.client.phone or 'не указан'}\nМастер: {b.master.name if b.master else 'Не назначен'}".replace(',', ' ')
            for b in bookings)
    await callback.message.edit_text(text, reply_markup=kb([[('⬅️ К панели', 'admin')], [('⬅️ В меню', 'home')]]))
    await callback.answer()


@dp.callback_query(F.data == "admin_services")
async def admin_services(callback: CallbackQuery):
    if callback.from_user.id not in settings.admin_id_set:
        await callback.answer("Нет доступа", show_alert=True)
        return
    async with SessionLocal() as session:
        services = (await session.execute(select(Service).order_by(Service.id))).scalars().all()
    text = "<b>✂️ Услуги</b>\n\n" + "\n".join(f"{'✅' if s.active else '⏸'} {s.name} — {s.price} ₽ · {s.duration_minutes} мин. (ID {s.id})" for s in services)
    text += "\n\nДля изменения списка услуг отредактируйте таблицу services в базе данных. В следующей версии можно добавить управление из самого бота."
    await callback.message.edit_text(text, reply_markup=kb([[('⬅️ К панели', 'admin')], [('⬅️ В меню', 'home')]]))
    await callback.answer()


@dp.callback_query(F.data == "admin_masters")
async def admin_masters(callback: CallbackQuery):
    if callback.from_user.id not in settings.admin_id_set:
        await callback.answer("Нет доступа", show_alert=True)
        return
    async with SessionLocal() as session:
        masters = (await session.execute(select(Master).order_by(Master.id))).scalars().all()
    text = "<b>👥 Мастера</b>\n\n" + "\n".join(f"{'✅' if m.active else '⏸'} {m.name} — {m.specialty or 'специализация не указана'} (ID {m.id})" for m in masters)
    text += "\n\nДобавление и редактирование мастеров пока выполняется через базу данных."
    await callback.message.edit_text(text, reply_markup=kb([[('⬅️ К панели', 'admin')], [('⬅️ В меню', 'home')]]))
    await callback.answer()


@dp.message(Command("admin"))
async def admin_command(message: Message):
    if message.from_user.id not in settings.admin_id_set:
        await message.answer("У вас нет доступа к панели администратора.")
        return
    await message.answer("<b>⚙️ Панель администратора</b>", reply_markup=kb([
        [('📋 Записи на сегодня', 'admin_today')], [('✂️ Услуги и цены', 'admin_services')], [('👥 Мастера', 'admin_masters')]
    ]))


async def reminder_loop():
    # Send each reminder once, when the appointment enters the configured reminder window.
    while True:
        try:
            now = local_now()
            window_end = now + timedelta(minutes=settings.reminder_minutes)
            async with SessionLocal() as session:
                due = (await session.execute(
                    select(Booking).options(selectinload(Booking.client), selectinload(Booking.service))
                    .where(Booking.status == 'confirmed', Booking.reminder_sent.is_(False),
                           Booking.starts_at > now, Booking.starts_at <= window_end)
                )).scalars().all()
                for booking in due:
                    try:
                        await bot.send_message(
                            booking.client.telegram_id,
                            f"⏰ <b>Напоминаем о записи в {settings.salon_name}</b>\n\n"
                            f"{booking.service.name}\n{booking.starts_at.strftime('%d.%m.%Y в %H:%M')}\n"
                            f"Адрес: {settings.salon_address}"
                        )
                        booking.reminder_sent = True
                    except Exception:
                        # Mark only after successful delivery so a temporary Telegram failure can retry.
                        continue
                await session.commit()
        except Exception as exc:
            print(f"Reminder loop error: {exc}")
        await asyncio.sleep(60)


async def main():
    await init_db()
    reminder_task = asyncio.create_task(reminder_loop())
    try:
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
