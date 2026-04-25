from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import get_profile_data

router = Router()


def get_field_status_text(field):
    if not field:
        return "Пустует"

    status = field.get("status") if hasattr(field, "get") else field["status"]
    plant_type = field.get("plant_type") if hasattr(field, "get") else field["plant_type"]

    if status == "empty":
        return "Пустует"
    if status == "growing":
        return f"Растёт {plant_type}"
    if status == "ready":
        return f"Созрело: {plant_type}"

    return f"{status} — {plant_type}"


@router.message(Command("profile"))
async def cmd_profile(message: types.Message, pool):
    data = await get_profile_data(pool, message.from_user.id)

    if not data:
        await message.answer("Ферма ещё не создана.")
        return

    user = data["user"]
    balance = data["balance"]
    level = data["level"]
    current_xp = data["current_xp"]
    need_xp = data["need_xp"]
    barn_level = user["barn_level"]
    last_action = user["last_action"]
    field_status = get_field_status_text(data["field"])

    farmer_name = message.from_user.first_name or "Фермер"

    text = (
        "🌾 МОЯ ФЕРМА\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👨‍🌾 Фермер: {farmer_name}\n"
        f"⭐ Уровень: {level}\n"
        f"📘 Опыт: {current_xp} / {need_xp}\n"
        f"💷 Баланс: {balance}\n"
        f"🏚 Амбар: {barn_level} ур.\n\n"
        "🌱 Поле:\n"
        f"└ {field_status}\n\n"
        "🕓 Последнее действие:\n"
        f"└ {last_action}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚒️ Хозяйство живёт и развивается!"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="Закрыть", callback_data=f"close_profile:{message.from_user.id}")
    kb.adjust(1)

    await message.answer(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("close_profile:"))
async def close_profile(call: types.CallbackQuery):
    owner_id = int(call.data.split(":")[1])

    if call.from_user.id != owner_id:
        await call.answer("Это не ваш профиль.", show_alert=True)
        return

    await call.message.delete()
    await call.answer()