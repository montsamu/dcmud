
import asyncio
from enum import Enum, auto
from base64 import b64encode, b64decode
import bcrypt
# from pony.orm import db_session, select
from model import *
from telnetlib3 import create_server
from telnetlib3.telopt import WONT, DONT, ECHO, SGA, SUPPRESS_LOCAL_ECHO, DO, WILL

class ClientState(Enum):
    CONNECTING = auto() # -> CREATING or AUTHENTICATING
    CREATING = auto() # -> LOADED
    AUTHENTICATING = auto() # -> LOADED
    LOADED = auto() # -> CONNECTED
    CONNECTED = auto()
    DISCONNECTED = auto()

class Client:
    def __init__(self, engine, reader, writer):
        self.engine = engine
        self.reader = reader
        self.writer = writer
        self.state = ClientState.CONNECTING
        self.player = None
        self.engine.clients[str(id(self))] = self

    async def send(self, msg):
        self.writer.write(msg)
        await self.writer.drain()

    async def send_line(self, msg=""):
        await self.send(f"\r{msg}\r\n")

    async def send_lines(self, *msgs):
        await self.send_line("\r\n".join(msgs))

    async def read_line(self, mask_output=False):
        if mask_output:
            #print(self.writer.iac(DONT, ECHO))
            #print(self.writer.iac(DO, SUPPRESS_LOCAL_ECHO))
            print(self.writer.iac(WILL, ECHO))
            await self.writer.drain()
        msg = await self.reader.readline()
        if mask_output:
            #self.writer.iac(DONT, SUPPRESS_LOCAL_ECHO)
            self.writer.iac(WONT, ECHO)
            #self.writer.iac(DO, ECHO)
            await self.writer.drain()
        msg = msg.strip()
        return msg

    async def shell(self):
        await self.welcome_screen()
        print(f"Client {self} reached terminal state: {self.state}")
        self.reader.feed_eof()
        self.writer.close()

    async def welcome_screen(self):
        # TODO check for disconnect
        await self.send_line("\r\nW E L C O M E") # TODO center, etc.
        await self.send_lines(
            "",
            "  By what name are you called, traveller?",
            "",
            "  [ Enter a name. If known, you will be asked for your password.",
            "    If unknown, you will enter player creation. ]",
            "")
        await self.send("      Name: ")
        name = await self.read_line() # TODO timeout
        name = name.title()
        if not name:
            await self.send_line("No choice made. Goodbye!") # rename nameless and begone!
            self.state = ClientState.DISCONNECTED
        elif not self.engine.check_player_name_is_valid(name):
            await self.send_line("*** INVALID NAME ***")
            await self.welcome_screen()
        elif self.engine.check_player_name_is_available(name):
            await self.create_player(name)
        else:
            self.state = ClientState.AUTHENTICATING
            await self.send("\r  Password: ") # TODO align, etc.
            password = await self.read_line(mask_output=True) # TODO timeout
            player_def = self.engine.check_player_password(name, password)
            if player_def:
                self.player = await self.engine.load_player(self, player_def, player_def.last_room.id)
                await self.loop()
            else:
                await self.send_line("No matching player/password found.")
                await self.welcome_screen()

    async def create_player(self, name):
        self.state = ClientState.CREATING
        await self.send_line("\r\nC R E A T E   A   P L A Y E R") # TODO center, refactor
        await self.send_lines(
                "",
                f"  Welcome, '{name}'! We do not seem to have met before...",
                "",
                "   ...let me know a phrase by which I can recognize you?",
                "",
                "  [ Enter and confirm a password. ]"
                "",
                "")
        confirmed_password = None
        while not confirmed_password:
            await self.send("  Password: ") # TODO indent
            password = await self.read_line(mask_output=True) # TODO timeout
            if not self.engine.check_password_is_valid(password):
                await self.send_line("Invalid password. Try again?")
            else:
                await self.send("\r   Confirm: ") # TODO indent/align
                confirm_password = await self.read_line(mask_output=True) # TODO timeout
                if password != confirm_password:
                    await self.send_line("Confirm does not match. Try again.")
                else:
                    confirmed_password = password

        await self.select_race(name, confirmed_password)

    async def select_race(self, name, password):
        await self.send_line("\r\nS E L E C T   A   R A C E") # TODO center, refactor
        await self.send_lines(
                "",
                "",
                "  In this world there are races beyond those in your own. Choose one:",
                "")
        player_races = self.engine.get_player_races()
        for r in player_races:
            await self.send_line(f"  {r.name}: {r.description}")
        await self.send_line()
        selected_race = None
        while not selected_race:
            await self.send("  > ")
            selected_name = await self.read_line() # TODO timeout
            if not selected_name:
                await self.send_line("Please make a selection...")
            else:
                matching_races = [r.name for r in player_races if r.name == selected_name]
                if matching_races:
                    selected_race = matching_races[0]
                else:
                    await self.send_line("Invalid selection. Try again...")
        player_def = self.engine.create_player(name, password, selected_race) # TODO exception when someone else creates the name
        self.player = await self.engine.load_player(self, player_def)
        await self.loop()

    # TODO: select background...

    async def loop(self):
        await self.send_line(f"\r\nWelcome, {self.player.pdef.name}!")
        self.state = ClientState.CONNECTED
        # TODO: do_look
        await self.send_line(f"\r\nYou are in room {self.player.room.rdef.name}")
        while self.state == ClientState.CONNECTED:
            await self.send("\rCommand: ")
            msg = await self.read_line()
            if msg == "":
                self.state = ClientState.DISCONNECTED
            else:
                await self.handle(msg)

    async def handle(self, msg):
        # TODO: process commands
        if msg in ["n","s","e","w","u","d"]:
            door = self.engine.mob_find_door(self.player, msg)
            if door:
                self.player = await self.engine.client_player_transit_door(self, door)
            else:
                await self.send_line("You see no exit in that direction.")
        elif msg == "look":
            # TODO hand to engine to actually look
            await self.send_line(f"You are in room {self.player.room.rdef.name}.")
        elif msg == "quit":
            await self.send_line("Goodbye!")
            # TODO unload from room?
            self.state = ClientState.DISCONNECTED
        else:
             await self.send_line(f"No such command: {msg}")

class Engine:
    def __init__(self):
        self.running = False
        self.shutdown = False
        self.server = None
        self.clients = {}

    # TODO: check mob can see the door, it is not hidden, etc.
    def mob_find_door(self, mob, direction):
            room = Room.get(id=mob.room.id)
            for door in room.doors:
                if door.ddef.direction.name == direction:
                    return door
            else:
                return None

    # TODO: improve by providing direction names etc. from previous session
    async def client_player_transit_door(self, client, door):
            cplayer = Player.get(id=client.player.id)
            door = Door.get(id=door.id)
            for player in door.room.mobs.filter(lambda mob: isinstance(mob, Player)):
                if player.id == client.player.id:
                    await client.send_line(f"You leave {door.ddef.direction.long_name}.")
                else:
                    # TODO check blind, hiding, sneaking, etc.
                    # mobs/rooms/objects with leaving triggers should happen FIRST
                    # out of move points, etc. happens before this method is called
                    pclient = self.clients[player.client_id]
                    await pclient.send_line(f"{client.player.pdef.name} leaves {door.ddef.direction.long_name}.")
            cplayer.room = Room.get(rdef=door.ddef.destination)
            cplayer.pdef.last_room = cplayer.room.rdef
            for player in cplayer.room.mobs.filter(lambda mob: isinstance(mob, Player)):
                if player.id == cplayer.id:
                    # TODO: do_look
                    await client.send_line(f"\r\nYou are in room {cplayer.room.rdef.name}")
                else:
                    pclient = self.clients[player.client_id]
                    await pclient.send_line(f"{cplayer.pdef.name} arrives from {door.ddef.direction.arrives_opposite_long_name}.")
            return cplayer

    def check_password_is_valid(self, password):
        return len(password) > 1 and len(password) < 128

    def check_player_name_is_valid(self, name):
        return len(name) > 1 and len(name) < 32 and name.isalpha() and name.isascii()

    def check_player_name_is_available(self, name):
            return not PlayerDefinition.exists(name=name)

    def check_player_password(self, name, password):
        pd = PlayerDefinition.get(name=name)
        if pd:
            if bcrypt.checkpw(password.encode('utf-8'), b64decode(pd.password)):
                return pd
        return None

    def get_player_races(self):
            return Race.select(playable=True)[:] # return slice out of session

    # TODO: check to see if player is already active (linkdead, left logged in another terminal, etc.)
    async def load_player(self, client, player_def, to_room_id=None):
            if to_room_id: # player_def.last_room:
                room = Room.get(rdef=RoomDefinition.get(id=to_room_id))
            else:
                adef = Area.get(name='The City of Chiiron')
                rdef = Room.get(adef=adef, name='Fountain Square')
                # room = Room.get(rdef=rdef)
            cplayer = Player(mdef=PlayerDefinition.get(id=player_def.id), room=room, client_id = str(id(client))) # throws error if still loaded...
            cplayer.pdef.last_room = room.rdef
            # TODO: mob or room triggers on 'arriving' players?
            for player in room.mobs.filter(lambda mob: isinstance(mob, Player)):
                if player.id == cplayer.id:
                    # TODO: do_look
                    await client.send_line(f"\r\nYou are in room {cplayer.room.rdef.name}")
                else:
                    pclient = self.clients[player.client_id]
                    await pclient.send_line(f"{cplayer.pdef.name} appears out of nowhere.") # TODO: bamfin?
            return cplayer

    def create_player(self, name, password, race):
            return PlayerDefinition(name=name, password=b64encode(bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())).decode('utf-8'), race=Race[race])

    async def shell(self, reader, writer):
        writer.iac(WONT, ECHO)
        writer.iac(WONT, SGA)
        client = Client(self, reader, writer)
        await client.shell()
        del self.clients[str(id(client))]
        # TODO where to remove Player instance, and notify of disappear?

    async def mload(self, room, mreset):
            mob = Mob(room=room, mdef=mreset.mdef, mreset=mreset)
            return mob

    async def oload(self, room, oreset):
            obj = Object(owner=room, odef=oreset.odef, oreset=oreset)
            return obj

    async def run(self):
        self.running = True
        self.server = await create_server(port=6023, shell=self.shell)
        # TODO: each area/room has a tickcount to reset?

        while not self.shutdown:
            print("TICK")
            print("CLIENTS:", len(self.clients.keys()))
            for client_id, client in self.clients.items():
                print(client_id, client, client.state)
                # check resets/triggers
                for area in Area.all(): # select(a for a in Area):
                    print(f"Area: {area.adef.name}")
                    for room in area.rooms:
                        print(f"  Room: {room.rdef.name}")
                        for obj in room.inventory:
                            print(f"    Obj: {obj}")
                        for mob in room.mobs:
                            print(f"    Mob: {mob}")
                        # TODO: open/shut doors if reset tick?
                        # TODO: logic for WHEN to mload/oload...
                        for mreset in room.rdef.mresets:
                            if not mreset.mob:
                                await self.mload(room, mreset)
                        for oreset in room.rdef.oresets:
                            if not oreset.obj:
                                await self.oload(room, oreset)
                # process event queue

            await asyncio.sleep(1)

