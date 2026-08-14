"""Seeds a small hand-crafted building/floor for testing the routing engine.

This gives Phase 2's A* implementation (and anyone poking around the API)
a real, known graph to query against instead of an empty database. Run it
with `python -m app.seed` after applying migrations.

Layout (single floor, straight hallway with rooms off either side):

    [Room A]   [Room B]           [Room C]   [Room D]
       |          |                  |          |
    (doorA)    (doorB)            (doorC)    (doorD)
       |          |                  |          |
  J1 --+---------J2---------J3-------+---------J4-- EXIT
"""

from app.database import Base, SessionLocal, engine
from app.models import Edge, Node, NodeType, Building, Floor


def run() -> None:
    """Create tables if needed, then insert the demo building/floor/graph.

    Idempotent: if a Building already exists, assumes the database has
    already been seeded and does nothing (so re-running this script, e.g.
    after a fresh `alembic upgrade head`, is always safe).
    """
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Building).first() is not None:
            print("Database already seeded, skipping.")
            return

        building = Building(name="Demo Hall")
        db.add(building)
        db.flush()  # assigns building.id without committing the transaction yet

        floor = Floor(
            building_id=building.id,
            name="Ground Floor",
            level=1,
            width=1000,
            height=400,
        )
        db.add(floor)
        db.flush()  # assigns floor.id, needed by the nodes we're about to create

        def node(node_type: NodeType, label: str, x: float, y: float) -> Node:
            """Create, stage, and flush a Node on the demo floor.

            Flushing immediately (rather than batching) means the node has
            a real `id` right away, so it can be referenced by `edge()`
            calls below without a separate lookup step.
            """
            n = Node(floor_id=floor.id, type=node_type, label=label, x=x, y=y)
            db.add(n)
            db.flush()
            return n

        # Hallway junctions running left to right, plus the exit at the end.
        j1 = node(NodeType.JUNCTION, "J1", 100, 200)
        j2 = node(NodeType.JUNCTION, "J2", 300, 200)
        j3 = node(NodeType.JUNCTION, "J3", 500, 200)
        j4 = node(NodeType.JUNCTION, "J4", 700, 200)
        exit_node = node(NodeType.EXIT, "Main Exit", 900, 200)

        # Four rooms, each branching off a junction through its own door.
        door_a = node(NodeType.DOOR, "Door A", 100, 100)
        room_a = node(NodeType.ROOM, "Room A", 100, 50)

        door_b = node(NodeType.DOOR, "Door B", 300, 100)
        room_b = node(NodeType.ROOM, "Room B", 300, 50)

        door_c = node(NodeType.DOOR, "Door C", 500, 100)
        room_c = node(NodeType.ROOM, "Room C", 500, 50)

        door_d = node(NodeType.DOOR, "Door D", 700, 100)
        room_d = node(NodeType.ROOM, "Room D", 700, 50)

        def edge(a: Node, b: Node, weight: float | None = None) -> None:
            """Create a walkable Edge between two nodes.

            Defaults to the straight-line (Euclidean) pixel distance between
            them, matching what the A* engine will use as edge weight for
            ordinary (non-transition) edges.
            """
            w = weight if weight is not None else ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5
            db.add(Edge(from_node_id=a.id, to_node_id=b.id, weight=w))

        # Hallway spine: J1 -> J2 -> J3 -> J4 -> Exit.
        edge(j1, j2)
        edge(j2, j3)
        edge(j3, j4)
        edge(j4, exit_node)

        # Room branches: each junction connects to its door, which connects
        # to the room behind it.
        edge(j1, door_a)
        edge(door_a, room_a)

        edge(j2, door_b)
        edge(door_b, room_b)

        edge(j3, door_c)
        edge(door_c, room_c)

        edge(j4, door_d)
        edge(door_d, room_d)

        db.commit()
        node_count = db.query(Node).count()
        edge_count = db.query(Edge).count()
        print(f"Seeded building '{building.name}' (id={building.id}) with 1 floor, "
              f"{node_count} nodes, {edge_count} edges.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
