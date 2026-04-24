import asyncpg


DATABASE_URL = "postgresql://postgres.opjpqdbwpwigemahybig:234o789o56oA@aws-1-eu-north-1.pooler.supabase.com:6543/postgres"


async def create_pool():
    return await asyncpg.create_pool(
        DATABASE_URL,
        ssl="require",
        statement_cache_size=0,
        command_timeout=30,
        min_size=1,
        max_size=2
    )


async def db_start(pool):
    # Для надежности объединяем создание таблиц в один запрос
    async with pool.acquire() as conn:
        await conn.execute('''
   CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    barn_capacity INTEGER DEFAULT 50
   );

   CREATE TABLE IF NOT EXISTS inventory (
    user_id BIGINT,
    item_id TEXT,
    amount INTEGER,
    PRIMARY KEY (user_id, item_id)
   );

   CREATE TABLE IF NOT EXISTS fields (
    user_id BIGINT PRIMARY KEY,
    status TEXT DEFAULT 'empty',
    plant_type TEXT DEFAULT 'Ничего',
    last_watered BIGINT DEFAULT 0
   );
  ''')


async def add_user(pool, user_id):
    async with pool.acquire() as conn:
        return await conn.fetchval('''
   INSERT INTO users (user_id) 
   VALUES ($1) 
   ON CONFLICT (user_id) DO NOTHING
   RETURNING user_id
  ''', user_id)


async def get_user(pool, user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)


async def add_item(pool, user_id, item_id, amount):
    async with pool.acquire() as conn:
        await conn.execute('''
   INSERT INTO inventory (user_id, item_id, amount) 
   VALUES ($1, $2, $3)
   ON CONFLICT (user_id, item_id) 
   DO UPDATE SET amount = inventory.amount + $3
  ''', user_id, item_id, amount)


async def get_inventory(pool, user_id):
    async with pool.acquire() as conn:
        return await conn.fetch('''
   SELECT item_id, amount FROM inventory 
   WHERE user_id = $1 AND amount > 0
  ''', user_id)



