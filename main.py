import asyncio
from engine import Engine

if __name__=="__main__":
    engine = Engine()
    asyncio.run(engine.run())
