from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from items import ITEMS

router = Router()


# Функция получения баланса теперь асинхронная и принимает pool
async def get_balance(pool, user_id):
    # Ищем любую вариацию Фаркоина
    res = await pool.fetchval(
        "SELECT SUM(amount) FROM inventory WHERE user_id = $1 AND item_name LIKE '%Фаркоин%'",
        user_id
    )
    return res if res else 0


@router.message(Command("barn"))
async def cmd_barn(message: types.Message, pool):  # Добавили pool как аргумент
    user_id = message.from_user.id

    # Получаем уровень амбара и инвентарь из PostgreSQL
    user = await pool.fetchrow("SELECT barn_level FROM users WHERE user_id = $1", user_id)
    items = await pool.fetch("SELECT item_name, amount FROM inventory WHERE user_id = $1 AND amount > 0", user_id)

    if not user:
        return await message.answer("Сначала напиши /start")

    barn_level = user['barn_level']
    balance = 0
    inventory_list = []
    usage = 0

    for item in items:
        name = item['item_name']
        amount = item['amount']

        # Проверяем на наличие слова Фаркоин в названии
        if "Фаркоин" in name:
            balance += amount
            continue

        item_data = ITEMS.get(name)
        if item_data:
            emoji = item_data.get("emoji", "📦")
            display_name = item_data.get("name", name)
        else:
            emoji = "📦"
            display_name = name

        usage += amount
        inventory_list.append(f"{emoji} | {display_name} {amount} шт.")

    capacity = barn_level * 100
    upgrade_cost = barn_level * 500
    inventory_text = "\n".join(inventory_list) if inventory_list else "💨 В амбаре пока пусто..."

    text = (
        f"🏘 *Ваш Амбар (Ур. {barn_level})*\n"
        f"📈 Заполнено: `{usage} / {capacity}` ед.\n"
        f"💰 В наличии: **{balance} 💷 Фаркоин**\n"
        f"--------------------------\n"
        f"{inventory_text}\n"
        f"--------------------------\n"
        f"🔧 Улучшить до Ур. {barn_level + 1} стоит {upgrade_cost} 💷"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="🆙 Улучшить", callback_data=f"barn_upgrade_{upgrade_cost}")
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("barn_upgrade_"))
async def process_upgrade(call: types.CallbackQuery, pool):  # Добавили pool
    cost = int(call.data.split("_")[2])
    user_id = call.from_user.id
    current_balance = await get_balance(pool, user_id)

    if current_balance < cost:
        return await call.answer(f"❌ Нужно {cost} 💷, у вас {current_balance}", show_alert=True)

    # Списываем деньги и повышаем уровень одним запросом (для безопасности)
    await pool.execute(
        "UPDATE inventory SET amount = amount - $1 WHERE user_id = $2 AND (item_name = 'Фаркоин' OR item_name = '💷 Фаркоин')",
        cost, user_id
    )
    await pool.execute("UPDATE users SET barn_level = barn_level + 1 WHERE user_id = $1", user_id)

    await call.answer("🏘 Амбар расширен!", show_alert=True)
    # Вызываем функцию отображения амбара заново, передавая pool
    await cmd_barn(call.message, pool)
git add .
