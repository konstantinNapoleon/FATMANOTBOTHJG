import asyncio
from aiogram import Router, types
from aiogram.filters import Command
from asyncpg import Pool

from database import get_level_from_xp, update_last_action
from items import ITEMS

router = Router()

# --- СЛОВАРЬ БАНДЛ-ПРОМОКОДОВ ---
# Ключ: то, что вводит игрок (ФЕРМА)
# Значение: список "технических" кодов из базы данных
BUNDLE_PROMO_CODES = {
    "ФЕРМА": ["FERMA_COINS", "FERMA_WHEAT", "FERMA_TOMATO"],
    # Сюда можно добавлять новые бандлы, например:
    # "STARTERPACK": ["STARTER_XP", "STARTER_MONEY"],
}


async def activate_single_code(conn, user_id, promo_code_str):
    """
    Активирует один промокод. Возвращает текст награды или текст ошибки.
    """
    # 1. Найти промокод
    promo = await conn.fetchrow(
        "SELECT * FROM promo_codes WHERE code = $1",
        promo_code_str
    )

    if not promo:
        return "❌ Промокод не найден."

    if promo['uses_left'] <= 0:
        return "😔 К сожалению, этот промокод уже закончился."

    # 2. Проверить, использовал ли его игрок
    already_used = await conn.fetchval(
        "SELECT 1 FROM used_promo_codes WHERE user_id = $1 AND promo_code_id = $2",
        user_id, promo['id']
    )

    if already_used:
        return "🤔 Вы уже активировали этот промокод."

    # 3. Транзакция: выдать награду и пометить код как использованный
    try:
        async with conn.transaction():
            # Уменьшаем количество доступных активаций
            await conn.execute(
                "UPDATE promo_codes SET uses_left = uses_left - 1 WHERE id = $1",
                promo['id']
            )
            # Помечаем, что пользователь использовал код
            await conn.execute(
                "INSERT INTO used_promo_codes (user_id, promo_code_id) VALUES ($1, $2)",
                user_id, promo['id']
            )

            # Выдаем награду в зависимости от типа
            reward_type = promo['reward_type']
            reward_amount = promo['reward_amount']
            success_message = ""

            if reward_type == 'currency':
                reward_item = 'Фаркоин'
                await conn.execute(
                    '''
                    INSERT INTO inventory (user_id, item_name, amount)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, item_name)
                    DO UPDATE SET amount = inventory.amount + $3
                    ''', user_id, reward_item, reward_amount
                )
                emoji = ITEMS.get(reward_item, {}).get("emoji", "💰")
                success_message = f"• {reward_amount} {emoji} {reward_item}"

            elif reward_type == 'item':
                reward_item = promo['reward_item']
                await conn.execute(
                    '''
                    INSERT INTO inventory (user_id, item_name, amount)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, item_name)
                    DO UPDATE SET amount = inventory.amount + $3
                    ''', user_id, reward_item, reward_amount
                )
                item_name_rus = ITEMS.get(reward_item, {}).get("name", reward_item)
                emoji = ITEMS.get(reward_item, {}).get("emoji", "🎁")
                success_message = f"• {reward_amount} {emoji} {item_name_rus}"

            elif reward_type == 'xp':
                user = await conn.fetchrow("SELECT xp, level FROM users WHERE user_id = $1", user_id)
                if user:
                    new_xp = user['xp'] + reward_amount
                    new_level = get_level_from_xp(new_xp)
                    await conn.execute(
                        "UPDATE users SET xp = $1, level = $2 WHERE user_id = $3",
                        new_xp, new_level, user_id
                    )
                    success_message = f"• {reward_amount} ⭐ очков опыта"
                    if new_level > user['level']:
                        success_message += f"\n🎉 (Новый уровень: {new_level}!)"

            return success_message

    except Exception as e:
        print(f"Single promo activation error: {e}")
        # Если что-то пошло не так, транзакция откатится
        return "Произошла ошибка при активации промокода. Попробуйте позже."


@router.message(Command("promo"))
async def cmd_promo(message: types.Message, pool: Pool):
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) < 2:
        return await message.answer("Пожалуйста, укажите промокод. \nПример: `/promo ФЕРМА`")

    promo_code_input = args[1].upper()

    # --- ЛОГИКА ОБРАБОТКИ ---
    async with pool.acquire() as conn:
        # 1. Проверяем, является ли код бандлом
        if promo_code_input in BUNDLE_PROMO_CODES:
            technical_codes = BUNDLE_PROMO_CODES[promo_code_input]

            # --- ПРЕДВАРИТЕЛЬНАЯ ПРОВЕРКА ВСЕХ КОДОВ БАНДЛА ---
            can_activate_all = True
            for code_str in technical_codes:
                promo = await conn.fetchrow("SELECT * FROM promo_codes WHERE code = $1", code_str)
                if not promo or promo['uses_left'] <= 0:
                    can_activate_all = False
                    break

                already_used = await conn.fetchval(
                    "SELECT 1 FROM used_promo_codes WHERE user_id = $1 AND promo_code_id = $2",
                    user_id, promo['id']
                )
                if already_used:
                    return await message.answer("🤔 Вы уже активировали этот набор промокодов.")

            if not can_activate_all:
                return await message.answer("😔 К сожалению, этот промокод уже закончился.")
            # ----------------------------------------------------

            rewards_list = []
            # Запускаем активацию всех кодов из бандла
            tasks = [activate_single_code(conn, user_id, code) for code in technical_codes]
            results = await asyncio.gather(*tasks)

            for res in results:
                if res.startswith('•'):
                    rewards_list.append(res)

            if rewards_list:
                final_message = "✅ Промокод активирован! Вы получили:\n\n" + "\n".join(rewards_list)
                await message.answer(final_message)
                await update_last_action(pool, user_id, f"Активировал промокод: {promo_code_input}")
            else:
                await message.answer("Не удалось активировать промокод. Возможно, он уже использован или закончился.")

        # 2. Если это не бандл, обрабатываем как обычный код
        else:
            result = await activate_single_code(conn, user_id, promo_code_input)

            # Форматируем красивый ответ, если это не бандл
            if result.startswith('•'):
                # Убираем буллет-поинт и добавляем заголовок
                final_message = "✅ Промокод активирован!\n\nВы получили: " + result.replace('• ', '')
                await message.answer(final_message)
                await update_last_action(pool, user_id, f"Активировал промокод: {promo_code_input}")
            else:
                # Иначе просто выводим сообщение об ошибке
                await message.answer(result)
