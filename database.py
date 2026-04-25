import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres.opjpqdbwpwigemahybig:234o789o56oA@aws-1-eu-north-1.pooler.supabase.com:6543/postgres")


def get_level_from_xp(xp: int) -> int:
    level = 1
    need = 20
    spent = 0

    while xp >= spent + need:
        spent += need
        level += 1
        need += 10

    return level


def get_xp_progress(xp: int):
    level = 1
    need = 20
    spent = 0

    while xp >= spent + need:
        spent += need
        level += 1
        need += 10

    current_xp = xp - spent
    return level, current_xp, need


async def create_pool():
    return await asyncpg.create_pool(
        DATABASE_URL,
        ssl="require",
        statement_cache_size=0,
        command_timeout=30,
        min_size=1,
        max_size=5
    )


async def db_start(pool):
    async with pool.acquire() as conn:
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            barn_level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            last_action TEXT DEFAULT 'Тишина на ферме...',
            created_at BIGINT DEFAULT 0
        );
        ''')

        await conn.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            user_id BIGINT,
            item_name TEXT,
            amount INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, item_name)
        );
        ''')

        await conn.execute('''
        CREATE TABLE IF NOT EXISTS fields (
            user_id BIGINT PRIMARY KEY,
            status TEXT DEFAULT 'empty',
            plant_type TEXT DEFAULT 'Ничего',
            last_watered BIGINT DEFAULT 0
        );
        ''')

        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS xp INTEGER DEFAULT 0;")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS level INTEGER DEFAULT 1;")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_action TEXT DEFAULT 'Тишина на ферме...';")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at BIGINT DEFAULT 0;")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS barn_level INTEGER DEFAULT 1;")


async def add_user(pool, user_id):
    async with pool.acquire() as conn:
        return await conn.fetchval('''
        INSERT INTO users (user_id, created_at)
        VALUES ($1, EXTRACT(EPOCH FROM NOW())::BIGINT)
        ON CONFLICT (user_id) DO NOTHING
        RETURNING user_id
        ''', user_id)


async def get_user(pool, user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1",
            user_id
        )


async def add_item(pool, user_id, item_name, amount):
    async with pool.acquire() as conn:
        await conn.execute('''
        INSERT INTO inventory (user_id, item_name, amount)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, item_name)
        DO UPDATE SET amount = inventory.amount + $3
        ''', user_id, item_name, amount)


async def get_inventory(pool, user_id):
    async with pool.acquire() as conn:
        return await conn.fetch('''
        SELECT item_name, amount FROM inventory
        WHERE user_id = $1 AND amount > 0
        ORDER BY item_name
        ''', user_id)


async def get_balance(pool, user_id):
    async with pool.acquire() as conn:
        value = await conn.fetchval('''
        SELECT amount FROM inventory
        WHERE user_id = $1 AND item_name = 'Фаркоин'
        ''', user_id)
        return value or 0


async def update_last_action(pool, user_id, action_text):
    async with pool.acquire() as conn:
        await conn.execute('''
        UPDATE users
        SET last_action = $1
        WHERE user_id = $2
        ''', action_text, user_id)


async def add_xp(pool, user_id, amount):
    async with pool.acquire() as conn:
        user = await conn.fetchrow('''
        SELECT xp, level FROM users
        WHERE user_id = $1
        ''', user_id)

        if not user:
            return None

        new_xp = user['xp'] + amount
        new_level = get_level_from_xp(new_xp)
        leveled_up = new_level > user['level']

        await conn.execute('''
        UPDATE users
        SET xp = $1, level = $2
        WHERE user_id = $3
        ''', new_xp, new_level, user_id)

        return {
            'old_level': user['level'],
            'new_level': new_level,
            'new_xp': new_xp,
            'leveled_up': leveled_up
        }


async def get_profile_data(pool, user_id):
    async with pool.acquire() as conn:
        user = await conn.fetchrow('''
        SELECT * FROM users
        WHERE user_id = $1
        ''', user_id)

        if not user:
            return None

        field = await conn.fetchrow('''
        SELECT status, plant_type, last_watered
        FROM fields
        WHERE user_id = $1
        ''', user_id)

        balance = await conn.fetchval('''
        SELECT amount FROM inventory
        WHERE user_id = $1 AND item_name = 'Фаркоин'
        ''', user_id)

        level, current_xp, need_xp = get_xp_progress(user['xp'])

        return {
            'user': user,
            'field': field,
            'balance': balance or 0,
            'level': level,
            'current_xp': current_xp,
            'need_xp': need_xp
        }




