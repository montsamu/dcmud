from dataclasses import dataclass, field, Field, fields, InitVar
from typing import ForwardRef, Optional, ClassVar, Any, cast
from functools import partial
from collections import defaultdict
from time import sleep
from random import randint

kwdataclass = partial(dataclass, kw_only=True)

_objects = defaultdict(list)

_ids = defaultdict(int)

# TODO: better check (use index as it should exist...)
# TODO: better init after loading the objects? at least go to first empty...
def next_id(dc):
    _ids[dc] += 1
    if [obj for obj in _objects[dc] if getattr(obj, globals().get(dc).pk) == _ids[dc]]:
        return next_id(dc)
    return _ids[dc]

def autonum(dc):
    return field(default_factory=partial(next_id, dc), metadata={"unique":True})

# @kwdataclass
# class UniqueConstraint:
#     column: str

# @kwdataclass
# class ForeignConstraint:
#     column: str
#     table: 'Base'
#     table_column: str

@kwdataclass # @dataclass(kw_only=True) # NOTE: kw_only=True is NOT inherited below; possibly could use alt. metaclass?
class Base:
    # id: int = field(default_factory=partial(next_id,__qualname__)) # TODO: __qualname__ is always Base when passed to the partial...
    # contraints: ClassVar [list[UniqueConstraint | ForeignConstraint]] = [UniqueConstraint(column='id')]
    # objects: ClassVar[list] = [] fail did not seem to work... child classes shared this var?
    def __post_init__(self):
        # print(">POST_INIT", self)
        # sleep(1)
        # TODO: get metadata once in loop, then apply metadata when appropriate
        for f in fields(self):
            if f.metadata:
                for mkey, mval in f.metadata.items():
                    if mkey == "abbreviation" and getattr(self, f.name) is None: # TODO: similar for display_name?
                        setattr(self, f.name, getattr(self, mval[0])[:mval[1]])
                    elif mkey == "copy":
                        setattr(self, f.name, getattr(self, mval).copy())
                    elif mkey == "copy2":
                        setattr(self, f.name, getattr(getattr(self, mval[0]), mval[1]).copy())
        for f in fields(self):
            if f.metadata:
                for mkey, mval in f.metadata.items():
                    if mkey == "unique" and mval: # TODO ENUM
                        if self.__class__.select(**{f.name:getattr(self, f.name)}):
                            raise TypeError("violates unique")
                        else:
                            pass # TODO add to INDEX
        _objects[self.__class__.__qualname__].append(self)
        for f in fields(self):
            if f.metadata:
                for mkey, mval in f.metadata.items():
                    if mkey == "fkeycollection":
                        getattr(getattr(self, f.name), mval).append(self)
        # TODO: insert into db? write to JSON? check metadata.ephemeral and class inheritance
        # self.__class__.objects.append(self)
        # print("<POST_INIT", self)
    @classmethod
    def all(cls):
        # print("ALL:", cls)
        return _objects[cls.__qualname__] # TODO: return frozenlist or tuple or generator?
    @classmethod
    def select(cls, **kwargs): # TODO use indexes if kwarg.key is a field we index
        return [b for b in cls.all() if all(item in b.__dict__.items() for item in kwargs.items())]
    @classmethod
    def __class_getitem__(cls, pk):
        return cls.get(**{cls.pk:pk})
    @classmethod
    def get(cls, **kwargs):
        dcs = cls.select(**kwargs)
        assert len(dcs) == 1
        return dcs[0]
    @classmethod
    def exists(cls, **kwargs):
        dcs = cls.select(**kwargs)
        return len(dcs)

@kwdataclass
class Named(Base):
    name: str # TODO unique?
    @classmethod
    def select_by_name(cls, name):
        return cls.select(name=name)

@kwdataclass
class UniqueNamed(Named):
    name: str = field(metadata={'unique':True}) # TODO: hook for trying to SET name
    @classmethod
    def get_by_name(cls, name):
        dcs = cls.select_by_name(name)
        assert len(dcs) == 1
        return dcs[0]

@kwdataclass
class Described(Base):
    description: str

@kwdataclass
class Race(UniqueNamed, Described):
    pk: ClassVar = 'name'
    playable: bool = False

# @kwdataclass
# class DisplayNamed(Named):
#     def get_display_name(self):

@kwdataclass
class AreaFlag(UniqueNamed, Described):
    def __hash__(self):
        return hash(self.name)

# @kwdataclass
# class AreaFlagValue(Base):
#     aflag: AreaFlag
#     value: bool = False # field(default=False)

def default_aflags():
    # print(">DEFAULT_AFLAGS")
    # return [AreaFlagValue(aflag=aflag) for aflag in AreaFlag.all()]
    # print("<DEFAULT_AFLAGS")
    return defaultdict(bool, {aflag: False for aflag in AreaFlag.all()})

def default_attributes():
    # d = defaultdict(partial(int, 10))
    # d.update({attr: 10 for attr in Attribute.all()})
    # return d
    return defaultdict(partial(int, 10), {attr: 10 for attr in Attribute.all()})

@kwdataclass
class Area(UniqueNamed):
    pk: ClassVar = 'area_id'
    area_id: int = autonum('Area') #  field(default_factory=partial(next_id, 'Area')) # auto('Area')
    rooms: list['Room'] = field(init=False, default_factory=list)
    aflags: dict[AreaFlag, bool] = field(default_factory=default_aflags)
    # active_aflags: dict[AreaFlag, bool] = field(init=False, metadata={"copy":"aflags", "ephemeral":True})

    # aflags: list['AreaFlagValue'] = field(default_factory=default_aflags) # [AreaFlagValue(aflag=aflag) for aflag in AreaFlag.all()])
        # self.area.rooms.append(self)

@kwdataclass
class RoomFlag(UniqueNamed, Described):
    def __hash__(self):
        return hash(self.name)

def default_rflags():
    # print(">DEFAULT_AFLAGS")
    # return [AreaFlagValue(aflag=aflag) for aflag in AreaFlag.all()]
    # print("<DEFAULT_AFLAGS")
    return defaultdict(bool, {rflag: False for rflag in RoomFlag.all()})

@kwdataclass
class Room(Named):
    pk: ClassVar = 'room_id'
    room_id: int = autonum('Room')
    area: Area = field(metadata={"fkeycollection": "rooms"})
    default_rflags: dict[RoomFlag, bool] = field(default_factory=default_rflags)
    rflags: dict[RoomFlag, bool] = field(init=False, metadata={"copy":"default_rflags", "ephemeral":True})
    doors: dict['Direction','Door'] = field(init=False, default_factory=dict)
    mresets: list['MobReset'] = field(init=False, default_factory=list)
    oresets: list['ObjectReset'] = field(init=False, default_factory=list)
    mobs: list['MobBase'] = field(init=False, default_factory=list, metadata={"ephemeral":True, "mresets":"mresets"}) # TODO impl mresets
    objects: list['Object'] = field(init=False, default_factory=list, metadata={"ephemeral":True, "oresets":"oresets"}) # TODO impl oresets

#    def __post_init__(self):
#        self.area.rooms.append(self)
    # TODO what happens when this room is deleted?

@kwdataclass
class Direction(UniqueNamed):
    pk: ClassVar = 'name'
    key: str = field(metadata={"unique":True, "abbreviation":("name",1)}, default=None)
    def __hash__(self):
        return hash(self.key)

@kwdataclass
class Attribute(UniqueNamed, Described): # TODO: if a new attr is added all MobDefinitions need it with default?
    pk: ClassVar = 'name'
    key: str = field(metadata={"unique":True, "abbreviation":("name", 3)}, default=None) # allows "lux" override for luck?
    def __hash__(self):
        return hash(self.key)

@kwdataclass
class DoorFlag(UniqueNamed, Described):
    def __hash__(self):
        return hash(self.name)

def default_dflags():
    return defaultdict(bool, {dflag: False for dflag in DoorFlag.all()})

# @kwdataclass
# class DoorFlagValue(Base):
#     dflag: DoorFlag
#     value: bool = False

@kwdataclass
class Door(Base):
    destination: Room
    # dflags: list['DoorFlagValue'] = field(default_factory=default_dflags)
    default_dflags: dict['DoorFlag', bool] = field(default_factory=default_dflags)
    dflags: dict['DoorFlag', bool] = field(init=False, metadata={"copy":"default_dflags", "ephemeral":True}) # TODO implement copy

def default_oflags():
    return defaultdict(bool, {oflag: False for oflag in ObjectFlag.all()})

@kwdataclass
class ObjectFlag(UniqueNamed, Described):
    def __hash__(self):
        return hash(self.name)

@kwdataclass
class ObjectDefinition(UniqueNamed, Described):
    pk: ClassVar = 'odef_id'
    odef_id: int = autonum('ObjectDefinition')
    default_oflags: dict['ObjectFlag', bool] = field(default_factory=default_oflags)

@kwdataclass
class Dice(Base):
    spec: str # TODO: make sure it obeys the spec? with regex metadata?
    def roll(self):
        base, roll = self.spec.split("+") if "+" in self.spec else self.spec, 0
        numrolls, dicesize = base.split("d")
        for i in range(numrolls):
            roll = roll + randint(1, dicesize)
        return roll

@kwdataclass
class MobFlag(UniqueNamed, Described):
    def __hash__(self):
        return hash(self.name)

def default_mflags():
    return defaultdict(bool, {mflag: False for mflag in MobFlag.all()})

class EquipmentLocation(UniqueNamed):
    def __hash__(self):
        return hash(self.name)

@kwdataclass
class MobObjectReset(Base):
    odef: ObjectDefinition
    # TODO: chance to select, etc.

@kwdataclass
class MobBaseDefinition(UniqueNamed, Described): # TODO optionally described? for player?
    race: 'Race'
    default_attrs: dict['Attribute',int|Dice] = field(default_factory=default_attributes)

@kwdataclass
class MobDefinition(MobBaseDefinition):
    pk: ClassVar = 'mdef_id'
    mdef_id: int = autonum('MobDefinition')
    default_mflags: dict[MobFlag, bool] = field(default_factory=default_mflags)
    default_equipment: dict[EquipmentLocation, list['MobObjectReset']] = field(default_factory=dict)

@kwdataclass
class PlayerDefinition(MobBaseDefinition): # TODO: account, or email recovery, etc.
    pk: ClassVar = 'pdef_id'
    description: str = None
    pdef_id: int = autonum('PlayerDefinition')
    password: str
    saved_attrs: dict['Attribute',int] = field(default_factory=default_attributes) # TODO: remove this default and require on create/load
    saved_equipment: dict[EquipmentLocation, list['Object']] = field(default_factory=dict)
    # TODO: bank vault, etc.

class Ephemeral:
    pass

@kwdataclass
class Object(Base): # TODO: optional renamed? NOTE: not ephemeral, it can be saved as part of a player file
    pk: ClassVar = 'obj_id'
    obj_id: int = autonum('Object')
    odef: ObjectDefinition
    oflags: dict[ObjectFlag, bool] = field(init=False, metadata={"copy2":("odef","default_oflags")})
    # TODO condition, owner, actual durability if rolled, etc. is it +1 enchanted, etc.

@kwdataclass
class MobBase(Base, Ephemeral):
    room: Room = field(metadata={"fkeycollection":"mobs"})
    mdef: MobBaseDefinition
    attrs: dict['Attribute',int] = field(init=False)

@kwdataclass
class Mob(MobBase): # TODO: optional renamed?
    mdef: MobDefinition
    attrs: dict['Attribute',int] = field(init=False, metadata={"roll2":("mdef","default_attrs")}) # TODO rename roll2
    equipment: dict[EquipmentLocation, Object] = field(init=False, metadata={"moresets":("mdef","default_equipment")}) # TODO rename moresets
    mflags: dict[MobFlag, bool] = field(init=False, metadata={"copy2":("mdef","default_mflags")}) # TODO rename copy2

@kwdataclass
class Player(MobBase):
    # pk: ClassVar = 'pid'
    # pid: int = autonum('Player')
    client: InitVar[Any] = None
    mdef: PlayerDefinition
    attrs: dict['Attribute',int] = field(init=False, metadata={"copy2":("mdef","saved_attrs")})
    def __post_init__(self, client):
        super().__post_init__()
        self.client = client

@kwdataclass
class ObjectReset(Base):
    room: Room = field(metadata={"fkeycollection":"oresets"})
    odef: ObjectDefinition

@kwdataclass
class MobReset(Base):
    room: Room = field(metadata={"fkeycollection":"mresets"}) 
    mdef: MobDefinition

if __name__=="__main__":
    print("MAIN:")
    for dname in ["up","down","east","west","north","south"]:
        d = Direction(name=dname)
    for attrname in ["strength","intelligence","wisdom","constitution"]:
        attrobj = Attribute(name=attrname, description=attrname)
    attrobj = Attribute(name="luck", key="lux", description="are you feeling lucky?")
    try:
        attrobj = Attribute(name="lucky", key="lux", description="not this lucky")
    except TypeError as e:
        print("Correctly caught error:", e)
    else:
        raise Exception("did not catch unique key error")
    try:
        attrobj = Attribute(name="luxy", description="really not this lucky")
    except TypeError as e:
        print("Correctly caught error:", e)
    else:
        raise Exception("did not catch unique abbreviated key error")
    af1 = AreaFlag(name='open', description='is the area open to players')
    a1 = Area(name="My Area")
    a2 = Area(name="Another Area")
    try:
        a4 = Area(name="Another Area")
    except TypeError as e:
        print("Correctly caught error:", e)
    else:
        raise Exception("did not catch unique name error")
    a3 = Area(area_id=50, name="Yet Another Area")
    rf1 = RoomFlag(name='outside', description='is the room outside')
    rf2 = RoomFlag(name='safe', description='is the room safe')
    r1 = Room(name="My Room", area=a1)
    r2 = Room(name="Your Room", area=a1)
    df1 = DoorFlag(name="reset_closed", description="should the door be closed at reset")
    df2 = DoorFlag(name="is_closed", description="is the door closed")
    r1.doors[Direction.get_by_name("north")] = Door(destination=r2)
    r2.doors[Direction.get_by_name("south")] = Door(destination=r1)
    mf1 = MobFlag(name='aggressive', description='is the mob aggro?')
    mf2 = MobFlag(name='assist_leader', description='will the mob assist its leader?')
    md1 = MobDefinition(name="orc", description="an ugly orc")
    mr1 = MobReset(room=r1, mdef=md1)
    of1 = ObjectFlag(name="bladed", description="is this bladed?")
    of2 = ObjectFlag(name="immobile", description="is this immobile?")
    od1 = ObjectDefinition(name="canteen", description="a nice can to drink water out of")
    od2 = ObjectDefinition(name="torch", description="a torch to light your way")
    or1 = ObjectReset(room=r1, odef=od1)
    el1 = EquipmentLocation(name="inventory")
    el2 = EquipmentLocation(name="right hand")
    md1.default_equipment[el2] = [MobObjectReset(odef=od1), MobObjectReset(odef=od2)]

    pd1 = PlayerDefinition(name="Phule", description="a new player", password="mypassword", saved_attrs={'strength':10})
    p1 = Player(mdef=pd1, room=r1, client="foo") # TODO actual client

    for a in Area.all(): # _objects['Area']:
        print(a)
