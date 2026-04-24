from aiogram import Router, types
from aiogram.filters import Command

router = Router()


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "📖 **СПРАВОЧНИК ФЕРМЕРА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚜 **ОСНОВНЫЕ КОМАНДЫ:**\n"
        "├ /start — Начать карьеру фермера\n"
        "├ /profile — Посмотреть свою статистику\n"
        "└ /help — Открыть это меню\n\n"

        "🌱 **РАБОТА НА ПОЛЕ:**\n"
        "├ /field — Ваше поле (вспашка, посадка, сбор)\n"
        "└ _Урожай растет 60 секунд. Не забывайте собирать!_\n\n"

        "🏘 **АМБАР И ХРАНЕНИЕ:**\n"
        "├ /barn — Просмотр инвентаря и веса\n"
        "└ _Там же можно расширить склад за 💷_\n\n"

        "🏪 **ТОРГОВЛЯ:**\n"
        "├ /market — Рынок «Золотая Нива»\n"
        "└ _Цены меняются каждые 5 минут. Продавай выгодно!_\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚒ *Удачной работы на земле!*"
    )

    await message.answer(help_text, parse_mode="Markdown")