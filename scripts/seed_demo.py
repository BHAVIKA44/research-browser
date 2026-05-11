import asyncio
from sqlalchemy import text
from app.db.session import engine


async def main():
    async with engine.begin() as conn:
        await conn.execute(text("select 1"))
    print("seed complete")


if __name__ == "__main__":
    asyncio.run(main())
