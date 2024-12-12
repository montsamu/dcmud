import asyncio
from engine import Engine
from model import *

if __name__=="__main__":
    for rname in ["elf","human","dwarf"]:
        r = Race(name=rname, description=f"a simple {rname}", playable=True)
    engine = Engine()
    asyncio.run(engine.run())
