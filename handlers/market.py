import time
import random
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from items import ITEMS
from database import get_inventory, get_user

router = Router()


def get_current_price(item_id):
    seed = int(time.time() // 300)
    random.seed(seed + hash(item_id))
    return random.randint(20, 50)


# 1. Функция отрисовки ГЛАВНОГО меню рынка
async def get_market_ui(pool, user_id):
    items = await get_inventory(pool, user_id)

    kb = InlineKeyboardBuilder()
    market_text = (
        "🚜 **ЛАВКА «ЗОЛОТАЯ НИВА»**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🕒 Цены обновлены: *сейчас*\n\n"
    )

    crops_found = False
    if items:
        for record in items:
            item_id = record['item_name']
            amount = record['amount']
            item_data = ITEMS.get(item_id)

            if item_data and item_data.get("type") == "crop":
                crops_found = True
                price = get_current_price(item_id)
                name = item_data['name']
                emoji = item_data['emoji']
                total_value = amount * price

                market_text += (
                    f"{emoji} **{name}**\n"
                    f"├ Цена: `{price} 💷` за шт.\n"
                    f"└ В амбаре: `{amount} шт.`\n"
                    f"💰 Итого: **{total_value} 💷**\n\n"
                )
                kb.button(text=f"💰 Продать {name}", callback_data=f"sell_{item_id}_{price}")

    if not crops_found:
        market_text += "❌ *В амбаре пусто...*\nПосейте что-нибудь на /field!\n\n"

    market_text += "━━━━━━━━━━━━━━━━━━━━\n"
    market_text += "⚒ *Удачного сбора урожая, фермер!*"

    # Кнопка перехода в Амбар
    kb.button(text="🏘 Перейти в Амбар", callback_data="market_to_barn")

    kb.adjust(1)
    return market_text, kb.as_markup()


# Команда /market
@router.message(Command("market"))
async def cmd_market(message: types.Message, pool):
    text, reply_markup = await get_market_ui(pool, message.from_user.id)
    await message.answer(text, reply_markup=reply_markup, parse_mode="Markdown")


# 2. Обработка продажи и показ "Чека"
@router.callback_query(F.data.startswith("sell_"))
async def process_sell(call: types.CallbackQuery, pool):
    data = call.data.split("_")
    item_id = data[1]
    price_at_click = int(data[2])
    user_id = call.from_user.id
    current_price = get_current_price(item_id)

    if current_price != price_at_click:
        await call.answer(f"⚠️ Курс изменился!", show_alert=True)
        text, reply_markup = await get_market_ui(pool, user_id)
        await call.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        return

    async with pool.acquire() as conn:
        res = await conn.fetchrow('''
            SELECT item_name, amount FROM inventory 
            WHERE user_id = $1 AND item_name = $2
        ''', user_id, item_id)

        if not res or res['amount'] <= 0:
            await call.answer("❌ В амбаре этого нет!", show_alert=True)
            return

        db_item_name = res['item_name']
        amount = res['amount']
        total_profit = amount * current_price

        # Списываем предмет (обнуляем) и начисляем Фаркоины в одной транзакции
        async with conn.transaction():
            await conn.execute('''
                UPDATE inventory SET amount = 0 
                WHERE user_id = $1 AND item_name = $2
            ''', user_id, db_item_name)

            await conn.execute('''
                INSERT INTO inventory (user_id, item_name, amount) 
                VALUES ($1, 'Фаркоин', $2) 
                ON CONFLICT(user_id, item_name) 
                DO UPDATE SET amount = inventory.amount + $2
            ''', user_id, total_profit)

    item_data = ITEMS.get(item_id, {"emoji": "📦", "name": item_id})
    success_text = (
        "✅ **СДЕЛКА СОВЕРШЕНА!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Товар: {item_data['emoji']} **{item_data['name']}**\n"
        f"⚖️ Объем: `{amount} шт.`\n"
        f"📈 Курс: `{current_price} 💷/шт.`\n\n"
        f"💰 Получено: **+{total_profit} 💷**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💵 Деньги доставлены в ваш амбар."
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад в лавку", callback_data="market_back")
    await call.message.edit_text(success_text, reply_markup=kb.as_markup(), parse_mode="Markdown")


# 3. Обработка кнопки "Назад в лавку"
@router.callback_query(F.data == "market_back")
async def process_market_back(call: types.CallbackQuery, pool):
    text, reply_markup = await get_market_ui(pool, call.from_user.id)
    try:
        await call.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    except:
        pass


# 4. Переход в Амбар из Маркета
@router.callback_query(F.data == "market_to_barn")
async def process_go_to_barn(call: types.CallbackQuery, pool):
    user_id = call.from_user.id

    user = await get_user(pool, user_id)
    items = await get_inventory(pool, user_id)

    barn_level = user['barn_level'] if user else 1
    balance = 0
    inventory_list = []
    usage = 0

    if items:
        for record in items:
            name = record['item_name']
            amount = record['amount']

            if "Фаркоин" in name:
                balance += amount
                continue

            item_data = ITEMS.get(name, {"emoji": "📦", "name": name})
            usage += amount
            inventory_list.append(f"{item_data['emoji']} | {item_data['name']} **{amount} шт.**")

    capacity = barn_level * 100
    inventory_text = "\n".join(inventory_list) if inventory_list else "💨 В амбаре пока пусто..."

    text = (
        f"🏘 **Ваш Амбар (Ур. {barn_level})**\n"
        f"📈 Заполнено: `{usage} / {capacity}` ед.\n"
        f"💰 В наличии: **{balance} 💷 Фаркоин**\n"
        f"--------------------------\n"
        f"{inventory_text}\n"
        f"--------------------------\n"
        f"🛍 _Вы перешли из лавки_"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Вернуться в Лавку", callback_data="market_back")

    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")