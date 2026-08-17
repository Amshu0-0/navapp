"""Tests for the A* pathfinding engine in app/routing.py.

Builds the same hallway-with-4-rooms layout used by app/seed.py directly
in an in-memory database, then asserts on hand-verified expected paths and
distances — so a bug in the algorithm (wrong path, wrong distance, wrong
exit chosen) fails loudly instead of silently.

Layout (see app/seed.py for the diagram):

  Room A   Room B          Room C   Room D
    |         |               |        |
  Door A    Door B          Door C   Door D
    |         |               |        |
  J1 --200-- J2 --200-- J3 --200-- J4 --200-- Exit
 (100,200) (300,200)  (500,200) (700,200)  (900,200)

Every hallway/spine edge is 200 units; every door<->junction and
door<->room edge is 100 or 50 units respectively, matching the seed
script's straight-line pixel distances.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Building, Edge, Floor, Node, NodeType
from app.routing import NoPathError, build_floor_graph, nearest_exit, shortest_path


@pytest.fixture()
def floor_graph():
    """Seeds the standard demo hallway into an in-memory DB and returns
    (graph, nodes_by_label) so tests can look up node ids by name."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    building = Building(name="Test Hall")
    db.add(building)
    db.flush()

    floor = Floor(building_id=building.id, name="1F", level=1)
    db.add(floor)
    db.flush()

    def node(node_type: NodeType, label: str, x: float, y: float) -> Node:
        n = Node(floor_id=floor.id, type=node_type, label=label, x=x, y=y)
        db.add(n)
        db.flush()
        return n

    j1 = node(NodeType.JUNCTION, "J1", 100, 200)
    j2 = node(NodeType.JUNCTION, "J2", 300, 200)
    j3 = node(NodeType.JUNCTION, "J3", 500, 200)
    j4 = node(NodeType.JUNCTION, "J4", 700, 200)
    exit_node = node(NodeType.EXIT, "Main Exit", 900, 200)

    door_a = node(NodeType.DOOR, "Door A", 100, 100)
    room_a = node(NodeType.ROOM, "Room A", 100, 50)
    door_b = node(NodeType.DOOR, "Door B", 300, 100)
    room_b = node(NodeType.ROOM, "Room B", 300, 50)

    def edge(a: Node, b: Node) -> None:
        weight = ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5
        db.add(Edge(from_node_id=a.id, to_node_id=b.id, weight=weight))

    edge(j1, j2)
    edge(j2, j3)
    edge(j3, j4)
    edge(j4, exit_node)
    edge(j1, door_a)
    edge(door_a, room_a)
    edge(j2, door_b)
    edge(door_b, room_b)

    db.commit()

    nodes_by_label = {
        "J1": j1, "J2": j2, "J3": j3, "J4": j4, "Exit": exit_node,
        "Door A": door_a, "Room A": room_a, "Door B": door_b, "Room B": room_b,
    }
    graph = build_floor_graph(db, floor.id)
    return graph, nodes_by_label


def test_shortest_path_along_hallway(floor_graph):
    """J1 to J4 should walk straight down the spine: 200+200+200 = 600."""
    graph, n = floor_graph
    path, distance = shortest_path(graph, n["J1"].id, n["J4"].id)

    assert [node.label for node in path] == ["J1", "J2", "J3", "J4"]
    assert distance == pytest.approx(600)


def test_shortest_path_room_to_exit(floor_graph):
    """Room A to Exit must go out its door, down the full hallway, to Exit:
    50 (room->door) + 100 (door->J1) + 200*3 (J1->J2->J3->J4) + 200 (J4->Exit) = 950."""
    graph, n = floor_graph
    path, distance = shortest_path(graph, n["Room A"].id, n["Exit"].id)

    assert [node.label for node in path] == [
        "Room A", "Door A", "J1", "J2", "J3", "J4", "Main Exit",
    ]
    assert distance == pytest.approx(950)


def test_shortest_path_is_symmetric(floor_graph):
    """Since edges are undirected, Exit -> Room A should be the same
    distance (and reverse path) as Room A -> Exit."""
    graph, n = floor_graph
    forward_path, forward_distance = shortest_path(graph, n["Room A"].id, n["Exit"].id)
    backward_path, backward_distance = shortest_path(graph, n["Exit"].id, n["Room A"].id)

    assert forward_distance == pytest.approx(backward_distance)
    assert [node.label for node in backward_path] == [
        node.label for node in reversed(forward_path)
    ]


def test_shortest_path_no_path_for_unknown_node(floor_graph):
    """Requesting a route to/from a node id that isn't on this floor's
    graph should fail clearly rather than crash or silently return junk."""
    graph, n = floor_graph
    with pytest.raises(NoPathError):
        shortest_path(graph, n["Room A"].id, 999_999)


def test_nearest_exit_from_room_b(floor_graph):
    """Room B is closer to the only Exit via J2 -> J3 -> J4 -> Exit:
    50 (room->door) + 100 (door->J2) + 200*3 = 750."""
    graph, n = floor_graph
    path, distance = nearest_exit(graph, n["Room B"].id)

    assert [node.label for node in path] == [
        "Room B", "Door B", "J2", "J3", "J4", "Main Exit",
    ]
    assert distance == pytest.approx(750)


def test_nearest_exit_raises_when_no_exits_on_floor():
    """If a floor has no EXIT-typed node at all, nearest_exit should fail
    clearly instead of returning an empty/incorrect result."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    building = Building(name="No Exit Hall")
    db.add(building)
    db.flush()
    floor = Floor(building_id=building.id, name="1F", level=1)
    db.add(floor)
    db.flush()
    room = Node(floor_id=floor.id, type=NodeType.ROOM, label="Room A", x=0, y=0)
    db.add(room)
    db.commit()

    graph = build_floor_graph(db, floor.id)
    with pytest.raises(NoPathError):
        nearest_exit(graph, room.id)
