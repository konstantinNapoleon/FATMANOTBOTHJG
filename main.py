import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from database import create_pool, db_start
from handlers.farm import router as farm_router
from handlers.start import router as start_router
from handlers.ambar import router as ambart_router
from handlers.market import router as market_router
from handlers.help import router as help_router

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "8685862317:AAESwf50j_cQidI-UF9f1mL-fMu8AgZbnP8"
# =============================================

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__) # Исправлено на __name__


async def main():
  # 1. Создаем пул подключений к Supabase (PostgreSQL)
  # Убрали DATABASE_URL из аргументов, так как он прописан в database.py
  pool = await create_pool()

  # 2. Создаем таблицы
  await db_start(pool) # Исправлено с init_db на db_start
  logger.info("Подключение к Supabase установлено. База готова.")

  # 3. Инициализируем бота
  # Если вы не включили VPN, добавьте сюда session с прокси (как мы обсуждали ранее)
  bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
  )

  # 4. Прокидываем pool во все хэндлеры
  dp = Dispatcher(pool=pool)

  # 5. Подключаем роутеры
  dp.include_router(farm_router)
  dp.include_router(start_router)
  dp.include_router(ambart_router)
  dp.include_router(market_router)
  dp.include_router(help_router)

  # 6. Запускаем
  await bot.delete_webhook(drop_pending_updates=True)
  logger.info("🚀 Бот запущен!")

  try:
    await dp.start_polling(bot)
  finally:
    await pool.close() # Закрываем соединение при выключении бота
    await bot.session.close() # Корректно закрываем сессию бота


if __name__ == "__main__": # Исправлено с name == "main"
  try:
    asyncio.run(main())
  except (KeyboardInterrupt, SystemExit):
    logger.info("🛑 Бот остановлен вручную.")
  except Exception as e:
    logger.critical(f"Критическая ошибка: {e}", exc_info=True)




