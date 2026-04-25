import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from database import create_pool, db_start
from handlers.farm import router as farm_router
from handlers.start import router as start_router
from handlers.ambar import router as ambar_router
from handlers.market import router as market_router
from handlers.help import router as help_router
from handlers.profile import router as profile_router

BOT_TOKEN = "8685862317:AAESwf50j_cQidI-UF9f1mL-fMu8AgZbnP8"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    pool = await create_pool()
    await db_start(pool)
    logger.info("Подключение к Supabase установлено. База готова.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )

    dp = Dispatcher()
    dp["pool"] = pool

    dp.include_router(start_router)
    dp.include_router(farm_router)
    dp.include_router(profile_router)
    dp.include_router(ambar_router)
    dp.include_router(market_router)
    dp.include_router(help_router)

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🚀 Бот запущен!")

    try:
        await dp.start_polling(bot)
    finally:
        await pool.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Бот остановлен вручную.")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)




