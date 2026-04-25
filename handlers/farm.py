import time
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from asyncpg import Pool

from items import ITEMS
from database import add_xp, update_last_action

router = Router()

GROW_TIME = 60


def build_field_keyboard(status: str, user_level: int, owner_id: int, growing_ready: bool = False):
    kb = InlineKeyboardBuilder()

    if status == "empty":
        kb.button(text="🚜 Вспахать", callback_data=f"farm_plow:{owner_id}")

    elif status == "plowed":
        for item_name, item_data in ITEMS.items():
            if item_data.get("type") != "crop":
                continue

            required_level = item_data.get("level_required", 1)
            emoji = item_data.get("emoji", "🌱")

            if user_level >= required_level:
                kb.button(
                    text=f"{emoji} {item_name}",
                    callback_data=f"farm_plant:{item_name}:{owner_id}"
                )
            else:
                kb.button(
                    text=f"🔒 {emoji} {item_name}",
                    callback_data=f"farm_locked:{item_name}:{owner_id}"
                )

    elif status == "growing":
        if growing_ready:
            kb.button(text="🧺 Собрать урожай", callback_data=f"farm_harvest:{owner_id}")
        else:
            kb.button(text="🔄 Обновить статус", callback_data=f"farm_refresh:{owner_id}")

    kb.button(text="❌ Закрыть", callback_data=f"farm_close:{owner_id}")
    kb.adjust(1)
    return kb


async def get_user_level(pool: Pool, user_id: int) -> int:
    row = await pool.fetchrow("SELECT level FROM users WHERE user_id = $1", user_id)
    if not row:
        return 1
    return row["level"] or 1


def ensure_owner(callback_data: str, caller_id: int):
    owner_id = int(callback_data.split(":")[-1])
    return owner_id == caller_id, owner_id


@router.message(Command("field"))
async def cmd_field(message: types.Message, pool: Pool):
    user_id = message.from_user.id

    f = await pool.fetchrow(
        "SELECT status, plant_type, last_watered FROM fields WHERE user_id=$1",
        user_id
    )

    if not f:
        return await message.answer("Сначала напиши /start")

    status = f["status"]
    plant = f["plant_type"]
    last_watered = f["last_watered"]
    now = int(time.time())
    user_level = await get_user_level(pool, user_id)

    if status == "empty":
        field_map = "🌿🌿🌿🌿🌿🌿🌿🌿🌿🌿\n🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
        text = f"{field_map}\n\nПоле заросло сорняками. Нужно его вспахать."
        kb = build_field_keyboard(status, user_level, user_id)

    elif status == "plowed":
        field_map = "🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
        text = (
            f"{field_map}\n\n"
            f"Поле вспахано. Что посадим?\n"
            f"⭐ Ваш уровень: {user_level}"
        )
        kb = build_field_keyboard(status, user_level, user_id)

    elif status == "growing":
        elapsed = now - last_watered
        if elapsed < GROW_TIME:
            time_left = GROW_TIME - elapsed
            field_map = "🌱🌱🌱🌱🌱🌱🌱🌱🌱🌱\n🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
            text = (
                f"{field_map}\n\n"
                f"Растет: **{plant}**.\n"
                f"⏳ Урожай будет готов через {time_left} сек."
            )
            kb = build_field_keyboard(status, user_level, user_id, growing_ready=False)
        else:
            item_data = ITEMS.get(plant, {"emoji": "📦"})
            emoji = item_data.get("emoji", "📦")
            field_map = f"{emoji * 10}\n🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
            text = f"{field_map}\n\nУрожай **{plant}** созрел! Пора собирать."
            kb = build_field_keyboard(status, user_level, user_id, growing_ready=True)

    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("farm_close:"))
async def close_field(call: types.CallbackQuery):
    is_owner, _ = ensure_owner(call.data, call.from_user.id)
    if not is_owner:
        await call.answer("Это не ваше поле.", show_alert=True)
        return

    await call.message.delete()
    await call.answer()


@router.callback_query(F.data.startswith("farm_plow:"))
async def process_plow(call: types.CallbackQuery, pool: Pool):
    is_owner, owner_id = ensure_owner(call.data, call.from_user.id)
    if not is_owner:
        await call.answer("Это не ваше поле.", show_alert=True)
        return

    await pool.execute("UPDATE fields SET status='plowed' WHERE user_id=$1", owner_id)
    await update_last_action(pool, owner_id, "Вспахал поле 🚜")
    await call.answer("Поле вспахано!")
    await update_field_ui(call, pool, owner_id)


@router.callback_query(F.data.startswith("farm_locked:"))
async def process_locked_plant(call: types.CallbackQuery):
    parts = call.data.split(":")
    plant = parts[1]
    owner_id = int(parts[2])

    if call.from_user.id != owner_id:
        await call.answer("Это не ваше поле.", show_alert=True)
        return

    item_data = ITEMS.get(plant, {})
    required_level = item_data.get("level_required", 1)
    await call.answer(f"Эта культура откроется на {required_level} уровне.", show_alert=True)


@router.callback_query(F.data.startswith("farm_plant:"))
async def process_plant(call: types.CallbackQuery, pool: Pool):
    parts = call.data.split(":")
    plant = parts[1]
    owner_id = int(parts[2])

    if call.from_user.id != owner_id:
        await call.answer("Это не ваше поле.", show_alert=True)
        return

    user_level = await get_user_level(pool, owner_id)
    item_data = ITEMS.get(plant)

    if not item_data:
        await call.answer("Культура не найдена.", show_alert=True)
        return

    required_level = item_data.get("level_required", 1)
    if user_level < required_level:
        await call.answer(f"Нужен {required_level} уровень.", show_alert=True)
        return

    await pool.execute(
        "UPDATE fields SET status='growing', plant_type=$1, last_watered=$2 WHERE user_id=$3",
        plant, int(time.time()), owner_id
    )

    await update_last_action(pool, owner_id, f"Посадил {item_data.get('emoji', '🌱')} {plant}")
    xp_result = await add_xp(pool, owner_id, 2)

    if xp_result and xp_result["leveled_up"]:
        await call.answer(f"Вы посадили {plant}! Новый уровень: {xp_result['new_level']} 🎉")
    else:
        await call.answer(f"Вы посадили {plant}!")

    await update_field_ui(call, pool, owner_id)


@router.callback_query(F.data.startswith("farm_harvest:"))
async def process_harvest(call: types.CallbackQuery, pool: Pool):
    is_owner, owner_id = ensure_owner(call.data, call.from_user.id)
    if not is_owner:
        await call.answer("Это не ваше поле.", show_alert=True)
        return

    f = await pool.fetchrow("SELECT plant_type FROM fields WHERE user_id=$1", owner_id)
    plant = f["plant_type"] if f else "Ничего"

    if plant == "Ничего":
        await call.answer("🌱 На этой грядке пусто!", show_alert=True)
        return await update_field_ui(call, pool, owner_id)

    await pool.execute(
        """
        INSERT INTO inventory (user_id, item_name, amount)
        VALUES ($1, $2, 10)
        ON CONFLICT(user_id, item_name) DO UPDATE
        SET amount = inventory.amount + 10
        """,
        owner_id, plant
    )

    await pool.execute(
        "UPDATE fields SET status='empty', plant_type='Ничего' WHERE user_id=$1",
        owner_id
    )

    item_data = ITEMS.get(plant, {"emoji": "🌾"})
    await update_last_action(pool, owner_id, f"Собрал урожай: 10 {item_data.get('emoji', '🌾')} {plant}")
    xp_result = await add_xp(pool, owner_id, 5)

    if xp_result and xp_result["leveled_up"]:
        await call.answer(f"Собрано 10 ед. {plant}! Новый уровень: {xp_result['new_level']} 🎉")
    else:
        await call.answer(f"Собрано 10 ед. {plant}!")

    await update_field_ui(call, pool, owner_id)


@router.callback_query(F.data.startswith("farm_refresh:"))
async def process_refresh(call: types.CallbackQuery, pool: Pool):
    is_owner, owner_id = ensure_owner(call.data, call.from_user.id)
    if not is_owner:
        await call.answer("Это не ваше поле.", show_alert=True)
        return

    await update_field_ui(call, pool, owner_id)
    await call.answer()


async def update_field_ui(call: types.CallbackQuery, pool: Pool, user_id: int):
    f = await pool.fetchrow(
        "SELECT status, plant_type, last_watered FROM fields WHERE user_id=$1",
        user_id
    )

    if not f:
        return

    status = f["status"]
    plant = f["plant_type"]
    last_watered = f["last_watered"]
    now = int(time.time())
    user_level = await get_user_level(pool, user_id)

    if status == "empty":
        field_map = "🌿🌿🌿🌿🌿🌿🌿🌿🌿🌿\n🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
        text = f"{field_map}\n\nПоле заросло сорняками. Нужно его вспахать."
        kb = build_field_keyboard(status, user_level, user_id)

    elif status == "plowed":
        field_map = "🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
        text = (
            f"{field_map}\n\n"
            f"Поле вспахано. Что посадим?\n"
            f"⭐ Ваш уровень: {user_level}"
        )
        kb = build_field_keyboard(status, user_level, user_id)

    elif status == "growing":
        elapsed = now - last_watered
        if elapsed < GROW_TIME:
            time_left = GROW_TIME - elapsed
            field_map = "🌱🌱🌱🌱🌱🌱🌱🌱🌱🌱\n🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
            text = (
                f"{field_map}\n\n"
                f"Растет: **{plant}**.\n"
                f"⏳ Урожай будет готов через {time_left} сек."
            )
            kb = build_field_keyboard(status, user_level, user_id, growing_ready=False)
        else:
            item_data = ITEMS.get(plant, {"emoji": "📦"})
            emoji = item_data.get("emoji", "📦")
            field_map = f"{emoji * 10}\n🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫"
            text = f"{field_map}\n\nУрожай **{plant}** созрел! Пора собирать."
            kb = build_field_keyboard(status, user_level, user_id, growing_ready=True)

    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    except:
        pass

