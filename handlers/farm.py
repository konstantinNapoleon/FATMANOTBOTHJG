import time
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from asyncpg import Pool

# ИМПОРТИРУЕМ СЛОВАРЬ (убедись, что файл items.py в той же папке или доступен)
from items import ITEMS

router = Router()

# Время роста в секундах (например, 60 секунд)
GROW_TIME = 60


@router.message(Command("field"))
async def cmd_field(message: types.Message, pool: Pool):
    user_id = message.from_user.id

    # Запрос к PostgreSQL
    f = await pool.fetchrow("SELECT status, plant_type, last_watered FROM fields WHERE user_id=$1", user_id)

    if not f:
        return await message.answer("Сначала напиши /start")

    # В asyncpg данные возвращаются как словарь
    status = f['status']
    plant = f['plant_type']
    last_watered = f['last_watered']

    kb = InlineKeyboardBuilder()
    now = int(time.time())

    # --- ВИЗУАЛИЗАЦИЯ ---
    if status == 'empty':
        field_map = "🌿🌿🌿🌿🌿🌿🌿🌿🌿🌿\n🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
        text = f"{field_map}\n\nПоле заросло сорняками. Нужно его вспахать."
        kb.button(text="🚜 Вспахать", callback_data="farm_plow")

    elif status == 'plowed':
        field_map = "🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
        text = f"{field_map}\n\nПоле вспахано. Что посадим?"
        kb.button(text="🌱 Пшеница", callback_data="farm_plant_Пшеница")
        kb.button(text="🍅 Томаты", callback_data="farm_plant_Томаты")

    elif status == 'growing':
        elapsed = now - last_watered
        if elapsed < GROW_TIME:
            # СТАДИЯ РОСТА
            time_left = GROW_TIME - elapsed
            field_map = "🌱🌱🌱🌱🌱🌱🌱🌱🌱🌱\n🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
            text = f"{field_map}\n\nРастет: **{plant}**.\n⏳ Урожай будет готов через {time_left} сек."
            kb.button(text="🔄 Обновить статус", callback_data="farm_refresh")
        else:
            # СТАДИЯ ГОТОВНОСТИ (Берем эмодзи из словаря ITEMS)
            item_data = ITEMS.get(plant, {"emoji": "📦"})
            emoji = item_data.get("emoji", "📦")

            field_map = f"{emoji * 10}\n🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
            text = f"{field_map}\n\nУрожай **{plant}** созрел! Пора собирать."
            kb.button(text="🧺 Собрать урожай", callback_data="farm_harvest")

    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


# --- ОБРАБОТКА ДЕЙСТВИЙ ---

@router.callback_query(F.data == "farm_plow")
async def process_plow(call: types.CallbackQuery, pool: Pool):
    await pool.execute("UPDATE fields SET status='plowed' WHERE user_id=$1", call.from_user.id)
    await call.answer("Поле вспахано!")
    await update_field_ui(call, pool)


@router.callback_query(F.data.startswith("farm_plant_"))
async def process_plant(call: types.CallbackQuery, pool: Pool):
    plant = call.data.split("_")[2]
    await pool.execute(
        "UPDATE fields SET status='growing', plant_type=$1, last_watered=$2 WHERE user_id=$3",
        plant, int(time.time()), call.from_user.id
    )
    await call.answer(f"Вы посадили {plant}!")
    await update_field_ui(call, pool)


@router.callback_query(F.data == "farm_harvest")
async def process_harvest(call: types.CallbackQuery, pool: Pool):
    user_id = call.from_user.id

    # Узнаем что росло
    f = await pool.fetchrow("SELECT plant_type FROM fields WHERE user_id=$1", user_id)
    plant = f['plant_type'] if f else "Ничего"

    # Добавляем в инвентарь (10 штук). Синтаксис PostgreSQL для конфликтов немного отличается
    await pool.execute("""
        INSERT INTO inventory (user_id, item_name, amount) 
        VALUES ($1, $2, 10) 
        ON CONFLICT(user_id, item_name) DO UPDATE SET amount = inventory.amount + 10
    """, user_id, plant)

    # Очищаем поле
    await pool.execute("UPDATE fields SET status='empty', plant_type='Ничего' WHERE user_id=$1", user_id)
    await call.answer(f"Собрано 10 ед. {plant}!")
    await update_field_ui(call, pool)


@router.callback_query(F.data == "farm_refresh")
async def process_refresh(call: types.CallbackQuery, pool: Pool):
    await update_field_ui(call, pool)


# Функция для обновления сообщения (интерфейса)
async def update_field_ui(call: types.CallbackQuery, pool: Pool):
    user_id = call.from_user.id
    f = await pool.fetchrow("SELECT status, plant_type, last_watered FROM fields WHERE user_id=$1", user_id)

    status = f['status']
    plant = f['plant_type']
    last_watered = f['last_watered']

    kb = InlineKeyboardBuilder()
    now = int(time.time())

    if status == 'empty':
        field_map = "🌿🌿🌿🌿🌿🌿🌿🌿🌿🌿\n🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
        text = f"{field_map}\n\nПоле заросло сорняками."
        kb.button(text="🚜 Вспахать", callback_data="farm_plow")
    elif status == 'plowed':
        field_map = "🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
        text = f"{field_map}\n\nПоле вспахано. Что посадим?"
        kb.button(text="🌱 Пшеница", callback_data="farm_plant_Пшеница")
        kb.button(text="🍅 Томаты", callback_data="farm_plant_Томаты")
    elif status == 'growing':
        elapsed = now - last_watered
        if elapsed < GROW_TIME:
            time_left = GROW_TIME - elapsed
            field_map = "🌱🌱🌱🌱🌱🌱🌱🌱🌱🌱\n🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
            text = f"{field_map}\n\nРастет: {plant}.\n⏳ Готовность через {time_left} сек."
            kb.button(text="🔄 Обновить", callback_data="farm_refresh")
        else:
            item_data = ITEMS.get(plant, {"emoji": "📦"})
            emoji = item_data.get("emoji", "📦")
            field_map = f"{emoji * 10}\n🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
            text = f"{field_map}\n\nУрожай созрел!"
            kb.button(text="🧺 Собрать", callback_data="farm_harvest")

    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    except:
        pass  # Если текст не изменился

