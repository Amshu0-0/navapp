import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Building, Edge, Floor, Node, NodeType


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_building_floor_relationship(db):
    building = Building(name="Test Hall")
    db.add(building)
    db.flush()

    floor = Floor(building_id=building.id, name="1F", level=1)
    db.add(floor)
    db.commit()

    assert building.floors == [floor]
    assert floor.building == building


def test_node_and_edge_creation(db):
    building = Building(name="Test Hall")
    db.add(building)
    db.flush()

    floor = Floor(building_id=building.id, name="1F", level=1)
    db.add(floor)
    db.flush()

    room = Node(floor_id=floor.id, type=NodeType.ROOM, label="Room A", x=0, y=0)
    door = Node(floor_id=floor.id, type=NodeType.DOOR, label="Door A", x=0, y=10)
    db.add_all([room, door])
    db.flush()

    edge = Edge(from_node_id=room.id, to_node_id=door.id, weight=10.0)
    db.add(edge)
    db.commit()

    assert edge.from_node.label == "Room A"
    assert edge.to_node.label == "Door A"
    assert edge.is_transition is False


def test_deleting_building_cascades_to_floors_and_nodes(db):
    building = Building(name="Test Hall")
    db.add(building)
    db.flush()

    floor = Floor(building_id=building.id, name="1F", level=1)
    db.add(floor)
    db.flush()

    node = Node(floor_id=floor.id, type=NodeType.JUNCTION, x=0, y=0)
    db.add(node)
    db.commit()

    db.delete(building)
    db.commit()

    assert db.query(Floor).count() == 0
    assert db.query(Node).count() == 0
"""Tests for the ORM models in app/models.py.

Runs against a fresh in-memory SQLite database per test (see the `db`
fixture), so these are fast and never touch the real navapp.db file used
for local dev/manual testing.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Building, Edge, Floor, Node, NodeType


@pytest.fixture()
def db():
    """Fresh in-memory SQLite session, schema created from the models.

    Using `:memory:` means each test gets an isolated database that's
    thrown away automatically when the session closes.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_building_floor_relationship(db):
    """A Building's `floors` relationship reflects Floors created under it,
    and the reverse `floor.building` link resolves back correctly."""
    building = Building(name="Test Hall")
    db.add(building)
    db.flush()

    floor = Floor(building_id=building.id, name="1F", level=1)
    db.add(floor)
    db.commit()

    assert building.floors == [floor]
    assert floor.building == building


def test_node_and_edge_creation(db):
    """An Edge correctly links two Nodes and defaults is_transition to False
    (i.e. a plain walkable connection, not a floor-change edge)."""
    building = Building(name="Test Hall")
    db.add(building)
    db.flush()

    floor = Floor(building_id=building.id, name="1F", level=1)
    db.add(floor)
    db.flush()

    room = Node(floor_id=floor.id, type=NodeType.ROOM, label="Room A", x=0, y=0)
    door = Node(floor_id=floor.id, type=NodeType.DOOR, label="Door A", x=0, y=10)
    db.add_all([room, door])
    db.flush()

    edge = Edge(from_node_id=room.id, to_node_id=door.id, weight=10.0)
    db.add(edge)
    db.commit()

    assert edge.from_node.label == "Room A"
    assert edge.to_node.label == "Door A"
    assert edge.is_transition is False


def test_deleting_building_cascades_to_floors_and_nodes(db):
    """Deleting a Building cascades through Floor -> Node, leaving no
    orphaned rows. This is what `cascade="all, delete-orphan"` in the
    model relationships is there to guarantee."""
    building = Building(name="Test Hall")
    db.add(building)
    db.flush()

    floor = Floor(building_id=building.id, name="1F", level=1)
    db.add(floor)
    db.flush()

    node = Node(floor_id=floor.id, type=NodeType.JUNCTION, x=0, y=0)
    db.add(node)
    db.commit()

    db.delete(building)
    db.commit()

    assert db.query(Floor).count() == 0
    assert db.query(Node).count() == 0
