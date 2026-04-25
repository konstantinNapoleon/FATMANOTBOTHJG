import time
import random
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from items import ITEMS
from database import get_inventory, add_xp, update_last_action

router = Router()


def get_current_price(item_id):
    seed = int(time.time() // 300)
    stable = sum(ord(char) for char in item_id)
    random.seed(seed + stable)
    return random.randint(20, 50)


def get_item_id_by_emoji(emoji: str):
    for item_id, item_data in ITEMS.items():
        if item_data.get("emoji") == emoji:
            return item_id
    return None


def parse_sell_args(text: str):
    parts = text.strip().split()
    if len(parts) < 2:
        return None, None

    emoji = parts[1]
    amount = None

    if len(parts) >= 3:
        amount = parts[2]

    return emoji, amount


async def get_market_ui(pool, user_id):
    items = await get_inventory(pool, user_id)
    user_inventory = {record["item_name"]: record["amount"] for record in items} if items else {}

    market_text = (
        "🚜 ЛАВКА «ЗОЛОТАЯ НИВА»\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🕒 Цены обновлены: сейчас\n\n"
    )

    for item_id, item_data in ITEMS.items():
        if item_data.get("type") != "crop":
            continue

        price = get_current_price(item_id)
        name = item_data["name"]
        emoji = item_data["emoji"]
        amount = user_inventory.get(item_id, 0)
        total_value = amount * price

        market_text += (
            f"{emoji} {name}\n"
            f"├ Цена: {price} 💷 за шт.\n"
            f"└ В амбаре: {amount} шт.\n"
            f"💰 Итого: {total_value} 💷\n\n"
        )

    market_text += (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "❗️Чтобы продать что-то пишите /sell [эмодзи] [кол-во]\n\n"
        "❗️Чтобы продать все /sell [эмодзи]\n\n"
        "⚒️ Удачного сбора урожая, фермер!"
    )

    return market_text


@router.message(Command("market"))
async def cmd_market(message: types.Message, pool):
    text = await get_market_ui(pool, message.from_user.id)
    await message.answer(text)


@router.message(Command("price"))
async def cmd_price(message: types.Message):
    parts = message.text.strip().split()

    if len(parts) < 2:
        await message.answer("❌ Использование: /price [эмодзи]")
        return

    emoji = parts[1]
    item_id = get_item_id_by_emoji(emoji)

    if not item_id:
        await message.answer("❌ Не удалось распознать товар по эмодзи.")
        return

    item_data = ITEMS.get(item_id)
    if item_data.get("type") != "crop":
        await message.answer("❌ Для этого предмета биржа сегодня молчит.")
        return

    price = get_current_price(item_id)

    await message.answer(
        f"📈 Текущий курс:\n"
        f"{item_data['emoji']} | {item_data['name']}\n"
        f"Цена: {price} 💷 за шт."
    )


@router.message(Command("sell"))
async def cmd_sell(message: types.Message, pool):
    user_id = message.from_user.id
    emoji, amount_raw = parse_sell_args(message.text)

    if not emoji:
        await message.answer("🌾 Укажите товар так: /sell [эмодзи] [кол-во]")
        return

    item_id = get_item_id_by_emoji(emoji)

    if not item_id:
        await message.answer("🧺 Я не нашёл такой товар на прилавке. Проверьте эмодзи из маркета.")
        return

    item_data = ITEMS.get(item_id)
    if item_data.get("type") != "crop":
        await message.answer("🚫 Этот предмет не принимается в лавке.")
        return

    current_price = get_current_price(item_id)

    async with pool.acquire() as conn:
        res = await conn.fetchrow(
            '''
            SELECT item_name, amount
            FROM inventory
            WHERE user_id = $1 AND item_name = $2
            ''',
            user_id, item_id
        )

    if not res or res["amount"] <= 0:
        await message.answer("🌫️ В амбаре такого товара сейчас нет.")
        return

    available_amount = res["amount"]

    if amount_raw is None:
        sell_amount = available_amount
    else:
        try:
            sell_amount = int(amount_raw)
        except ValueError:
            await message.answer("🔢 Количество нужно указывать числом.")
            return

        if sell_amount <= 0:
            await message.answer("⚖️ Нельзя продать ноль или меньше.")
            return

        if sell_amount > available_amount:
            await message.answer(f"📦 У вас в амбаре только {available_amount} шт.")
            return

    kb = InlineKeyboardBuilder()
    kb.button(
        text="Да",
        callback_data=f"sellcheck_yes:{item_id}:{sell_amount}:{current_price}:{user_id}"
    )
    kb.button(
        text="Нет",
        callback_data=f"sellcheck_no:{user_id}"
    )
    kb.adjust(2)

    text = (
        "🧾 Лавочник пересчитал мешки и уточняет:\n\n"
        "Вы действительно хотите продать:\n"
        f"{item_data['emoji']} {sell_amount} шт.\n"
        f"по прайсу: {current_price}\n\n"
        "Сказать торговцу продолжать?"
    )

    await message.answer(text, reply_markup=kb.as_markup())


def is_owner(callback_data: str, user_id: int) -> bool:
    return int(callback_data.split(":")[-1]) == user_id


@router.callback_query(F.data.startswith("sellcheck_no:"))
async def sellcheck_no(call: types.CallbackQuery):
    if not is_owner(call.data, call.from_user.id):
        await call.answer("Это не ваша сделка.", show_alert=True)
        return

    await call.message.edit_text("🛑 Торг был отменён!")
    await call.answer()


@router.callback_query(F.data.startswith("sellcheck_yes:"))
async def sellcheck_yes(call: types.CallbackQuery):
    if not is_owner(call.data, call.from_user.id):
        await call.answer("Это не ваша сделка.", show_alert=True)
        return

    _, item_id, sell_amount, price, owner_id = call.data.split(":")
    sell_amount = int(sell_amount)
    price = int(price)

    item_data = ITEMS.get(item_id, {"emoji": "📦", "name": item_id})
    total_profit = sell_amount * price

    kb = InlineKeyboardBuilder()
    kb.button(
        text="Подтвердить",
        callback_data=f"sellfinal_yes:{item_id}:{sell_amount}:{price}:{owner_id}"
    )
    kb.button(
        text="Отменить",
        callback_data=f"sellfinal_no:{owner_id}"
    )
    kb.adjust(2)

    text = (
        "💼 Сделка почти на столе:\n\n"
        f"Вы продаете {item_data['emoji']} {sell_amount} шт.\n"
        f"Итого: {total_profit}\n\n"
        "Подтвердить окончательно?"
    )

    await call.message.edit_text(text, reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("sellfinal_no:"))
async def sellfinal_no(call: types.CallbackQuery):
    if not is_owner(call.data, call.from_user.id):
        await call.answer("Это не ваша сделка.", show_alert=True)
        return

    await call.message.edit_text("📭 Продажа была отменена!")
    await call.answer()


@router.callback_query(F.data.startswith("sellfinal_yes:"))
async def sellfinal_yes(call: types.CallbackQuery, pool):
    if not is_owner(call.data, call.from_user.id):
        await call.answer("Это не ваша сделка.", show_alert=True)
        return

    user_id = call.from_user.id
    _, item_id, sell_amount, old_price, _owner_id = call.data.split(":")
    sell_amount = int(sell_amount)
    old_price = int(old_price)

    item_data = ITEMS.get(item_id, {"emoji": "📦", "name": item_id})
    current_price = get_current_price(item_id)

    if current_price != old_price:
        await call.message.edit_text(
            "📈 Пока вы торговались, курс изменился.\nПопробуйте снова через /sell."
        )
        await call.answer()
        return

    async with pool.acquire() as conn:
        res = await conn.fetchrow(
            '''
            SELECT amount
            FROM inventory
            WHERE user_id = $1 AND item_name = $2
            ''',
            user_id, item_id
        )

        if not res or res["amount"] < sell_amount:
            await call.message.edit_text(
                "📦 В амбаре уже недостаточно товара для этой сделки."
            )
            await call.answer()
            return

        total_profit = sell_amount * current_price

        async with conn.transaction():
            await conn.execute(
                '''
                UPDATE inventory
                SET amount = amount - $1
                WHERE user_id = $2 AND item_name = $3
                ''',
                sell_amount, user_id, item_id
            )

            await conn.execute(
                '''
                DELETE FROM inventory
                WHERE user_id = $1 AND item_name = $2 AND amount <= 0
                ''',
                user_id, item_id
            )

            await conn.execute(
                '''
                INSERT INTO inventory (user_id, item_name, amount)
                VALUES ($1, 'Фаркоин', $2)
                ON CONFLICT (user_id, item_name)
                DO UPDATE SET amount = inventory.amount + $2
                ''',
                user_id, total_profit
            )

    sold_xp = max(1, sell_amount // 5)
    xp_result = await add_xp(pool, user_id, sold_xp)
    await update_last_action(
        pool,
        user_id,
        f"Продал {item_data['emoji']} {item_data['name']} x{sell_amount} за {total_profit} 💷"
    )

    success_text = (
        "✅ СДЕЛКА СОВЕРШЕНА!\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Товар: {item_data['emoji']} {item_data['name']}\n"
        f"⚖️ Объем: {sell_amount} шт.\n"
        f"📈 Курс: {current_price} 💷/шт.\n\n"
        f"💰 Получено: +{total_profit} 💷\n"
        f"⭐ Опыт: +{sold_xp} XP\n"
    )

    if xp_result and xp_result.get("leveled_up"):
        success_text += f"🎉 Новый уровень: {xp_result['new_level']}\n"

    success_text += (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💵 Деньги доставлены в ваш амбар."
    )

    await call.message.edit_text(success_text)
    await call.answer()