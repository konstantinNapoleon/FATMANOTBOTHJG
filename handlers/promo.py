from aiogram import Router, types
from aiogram.filters import Command
from asyncpg import Pool

from database import get_level_from_xp, update_last_action
from items import ITEMS

router = Router()


@router.message(Command("promo"))
async def cmd_promo(message: types.Message, pool: Pool):
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) < 2:
        return await message.answer("Пожалуйста, укажите промокод. \nПример: `/promo WELCOME`")

    promo_code_str = args[1].upper()

    async with pool.acquire() as conn:
        # 1. Найти промокод
        promo = await conn.fetchrow(
            "SELECT * FROM promo_codes WHERE code = $1",
            promo_code_str
        )

        if not promo:
            return await message.answer("❌ Промокод не найден.")

        if promo['uses_left'] <= 0:
            return await message.answer("😔 К сожалению, этот промокод уже закончился.")

        # 2. Проверить, использовал ли его игрок
        already_used = await conn.fetchval(
            "SELECT 1 FROM used_promo_codes WHERE user_id = $1 AND promo_code_id = $2",
            user_id, promo['id']
        )

        if already_used:
            return await message.answer("🤔 Вы уже активировали этот промокод.")

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
                    success_message = f"✅ Промокод активирован!\n\nНа ваш счёт зачислено {reward_amount} {emoji} {reward_item}."

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
                    emoji = ITEMS.get(reward_item, {}).get("emoji", "🎁")
                    success_message = f"✅ Промокод активирован!\n\nВы получили: {reward_amount} {emoji} {reward_item}."

                elif reward_type == 'xp':
                    user = await conn.fetchrow("SELECT xp, level FROM users WHERE user_id = $1", user_id)
                    if user:
                        new_xp = user['xp'] + reward_amount
                        new_level = get_level_from_xp(new_xp)
                        await conn.execute(
                            "UPDATE users SET xp = $1, level = $2 WHERE user_id = $3",
                            new_xp, new_level, user_id
                        )
                        success_message = f"✅ Промокод активирован!\n\nВы получили {reward_amount} ⭐ очков опыта!"
                        if new_level > user['level']:
                            success_message += f"\n\n🎉 Поздравляем с достижением {new_level} уровня!"

                await message.answer(success_message)
                await update_last_action(pool, user_id, f"Активировал промокод: {promo_code_str}")

        except Exception as e:
            # Если что-то пошло не так, транзакция откатится
            await message.answer("Произошла ошибка при активации промокода. Попробуйте позже.")
            print(f"Promo activation error: {e}")