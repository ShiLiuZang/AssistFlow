"""运行 python -m scripts.vectorize_kb；失败后重跑只处理 pending。"""
import asyncio
from app.kb.dualwrite import vectorize_pending


async def main():
    count = await vectorize_pending()
    print(f"本次完成向量化：{count} 条")


if __name__ == "__main__":
    asyncio.run(main())
