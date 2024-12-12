import asyncio
from engine import Engine
from model import *

if __name__=="__main__":
    for dirname in ["north","south","east","west","up","down"]:
        direction = Direction(name=dirname)
    for rname in ["elf","human","dwarf"]:
        r = Race(name=rname, description=f"a simple {rname}", playable=True)
    area1 = Area(name='The City of Chiiron')
    room1 = Room(area=area1, name="Fountain Square")
    room2 = Room(area=area1, name="Another Room")
    room1.doors[Direction['west']] = Door(destination=room2)
    room2.doors[Direction['east']] = Door(destination=room1)
    engine = Engine()
    asyncio.run(engine.run())
