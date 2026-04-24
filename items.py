# items.py

ITEMS = {
  "Фаркоин": {
    "name": "Фаркоин",
    "emoji": "💷",
    "type": "currency"
  },
  "Пшеница": {
    "name": "Пшеница",
    "emoji": "🌾",
    "type": "crop"
  },
  "Томаты": {
    "name": "Томаты",
    "emoji": "🍅",
    "type": "crop"
  },
  "Картофель": {
    "name": "Картофель",
    "emoji": "🥔",
    "type": "crop"
  },
  "Хлеб": {
    "name": "Хлеб",
    "emoji": "🍞",
    "type": "food" # Можно продать или съесть в будущем
  },
  "Томатная паста": {
    "name": "Томатная паста",
    "emoji": "🥫",
    "type": "food"
  }
}


# Функция для поиска данных предмета по его названию или ID
def get_item_data(item_id):
  return ITEMS.get(item_id, {"name": item_id, "emoji": "📦", "type": "unknown"})