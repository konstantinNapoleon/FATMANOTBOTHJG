import sqlite3
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from items import ITEMS

router = Router()

# Универсальная функция получения баланса
def get_balance(user_id):
  conn = sqlite3.connect('farm_bot.db')
  # Ищем любую вариацию Фаркоина и суммируем (на случай дублей)
  res = conn.execute(
    "SELECT SUM(amount) FROM inventory WHERE user_id = ? AND item_name LIKE '%Фаркоин%'",
    (user_id,)
  ).fetchone()
  conn.close()
  return res[0] if res[0] else 0

@router.message(Command("barn"))
async def cmd_barn(message: types.Message):
  user_id = message.from_user.id
  conn = sqlite3.connect('farm_bot.db')

  user = conn.execute("SELECT barn_level FROM users WHERE user_id = ?", (user_id,)).fetchone()
  items = conn.execute("SELECT item_name, amount FROM inventory WHERE user_id = ? AND amount > 0",
             (user_id,)).fetchall()
  conn.close()

  if not user:
    return await message.answer("Сначала напиши /start")

  barn_level = user[0]
  balance = 0
  inventory_list = []
  usage = 0

  for name, amount in items:
    # Проверяем на наличие слова Фаркоин в названии
    if "Фаркоин" in name:
      balance += amount # СУММИРУЕМ, а не заменяем
      continue

    item_data = ITEMS.get(name)
    if item_data:
      emoji = item_data.get("emoji", "📦")
      display_name = item_data.get("name", name)
    else:
      emoji = "📦"
      display_name = name

    usage += amount
    inventory_list.append(f"{emoji} | {display_name} **{amount} шт.**")

  capacity = barn_level * 100
  upgrade_cost = barn_level * 500
  inventory_text = "\n".join(inventory_list) if inventory_list else "💨 В амбаре пока пусто..."

  # Исправил разметку жирного шрифта (у тебя были лишние **)
  text = (
    f"🏘 **Ваш Амбар (Ур. {barn_level})**\n"
    f"📈 Заполнено: `{usage} / {capacity}` ед.\n"
    f"💰 В наличии: **{balance} 💷 Фаркоин**\n"
    f"--------------------------\n"
    f"{inventory_text}\n"
    f"--------------------------\n"
    f"🔧 Улучшить до Ур. {barn_level + 1} стоит **{upgrade_cost} 💷**"
  )

  kb = InlineKeyboardBuilder()
  kb.button(text="🆙 Улучшить", callback_data=f"barn_upgrade_{upgrade_cost}")
  await message.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("barn_upgrade_"))
async def process_upgrade(call: types.CallbackQuery):
  cost = int(call.data.split("_")[2])
  user_id = call.from_user.id
  current_balance = get_balance(user_id)

  if current_balance < cost:
    return await call.answer(f"❌ Нужно {cost} 💷, у вас {current_balance}", show_alert=True)

  conn = sqlite3.connect('farm_bot.db')
  # Списываем деньги (сначала пытаемся найти просто 'Фаркоин')
  conn.execute(
    "UPDATE inventory SET amount = amount - ? WHERE user_id = ? AND (item_name = 'Фаркоин' OR item_name = '💷 Фаркоин')",
    (cost, user_id)
  )
  conn.execute("UPDATE users SET barn_level = barn_level + 1 WHERE user_id = ?", (user_id,))
  conn.commit()
  conn.close()

  await call.answer("🏘 Амбар расширен!", show_alert=True)
  # Обновляем сообщение амбара
  await cmd_barn(call.message)