from aiogram import Router, types
from aiogram.filters import CommandStart
from database import add_user, add_item


router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message, pool):  # Добавили pool в аргументы
    user_id = message.from_user.id

    # 1. Регистрируем пользователя через функцию из database.py
    await add_user(pool, user_id)

    # 2. Регистрируем поле (так как в database.py пока нет отдельной функции, пишем запрос тут)
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO fields (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
            user_id
        )

    # 3. Выдаем 100 Фаркоинов через функцию add_item
    # Используем "💷 Фаркоин" как item_id
    await add_item(pool, user_id, "💷 Фаркоин", 100)

    await message.answer(
        "🚜 <b>Добро пожаловать в ферму 2026!</b>\n\n"
        "Вам выдано 100 💷 Фаркоинов в амбар.\n"
        "Используйте /profile, чтобы посмотреть статистику.")