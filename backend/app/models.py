"""ORM models for the indoor routing graph.

The schema mirrors how the app thinks about a building: a Building has
Floors, each Floor has Nodes (points you can route between — rooms, doors,
hallway junctions, exits, stairs/elevators), and Edges connect two Nodes
with a traversal cost. Running pathfinding (Phase 2) means loading a
floor's (or building's) Nodes/Edges into a graph and searching it with A*.
"""

import enum

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class NodeType(str, enum.Enum):
    """What kind of physical thing a Node represents.

    STAIRS/ELEVATOR nodes are special: they can appear on multiple floors
    and get linked via `Node.transition_group` so a transition Edge can
    connect "these stairs on floor 1" to "these stairs on floor 2"
    (see Phase 6).
    """

    ROOM = "room"
    JUNCTION = "junction"
    DOOR = "door"
    EXIT = "exit"
    STAIRS = "stairs"
    ELEVATOR = "elevator"


class Building(Base):
    """A single building, top of the hierarchy. Owns one or more Floors."""

    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

    # cascade="all, delete-orphan": deleting a Building deletes its Floors
    # (and, transitively, their Nodes) too — no orphaned rows left behind.
    floors: Mapped[list["Floor"]] = relationship(
        back_populates="building", cascade="all, delete-orphan"
    )


class Floor(Base):
    """One level of a Building.

    `image_path` points at the uploaded blueprint image used as the canvas
    background in the floor-plan editor/viewer (Phases 4-5). `width`/`height`
    are the image's pixel dimensions, used to scale node coordinates
    consistently when the image is displayed at different zoom levels.
    """

    __tablename__ = "floors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Floor ordering/height, e.g. 1 = ground floor, 2 = second floor, etc.
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    width: Mapped[float | None] = mapped_column(Float, nullable=True)
    height: Mapped[float | None] = mapped_column(Float, nullable=True)

    building: Mapped["Building"] = relationship(back_populates="floors")
    nodes: Mapped[list["Node"]] = relationship(
        back_populates="floor", cascade="all, delete-orphan"
    )


class Node(Base):
    """A routable point on a floor: a room, door, hallway junction, exit,
    or stairs/elevator.

    `x`/`y` are pixel coordinates on that floor's blueprint image, placed
    by whoever tagged the floor plan in the editor (Phase 5).
    """

    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    floor_id: Mapped[int] = mapped_column(ForeignKey("floors.id"), nullable=False)
    type: Mapped[NodeType] = mapped_column(Enum(NodeType), nullable=False)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)

    # Links stairs/elevator nodes that represent the same physical structure
    # across floors (e.g. all four Nodes for "Stairwell B" share the same
    # transition_group string), so a transition edge can connect them.
    transition_group: Mapped[str | None] = mapped_column(String, nullable=True)

    floor: Mapped["Floor"] = relationship(back_populates="nodes")


class Edge(Base):
    """A walkable connection between two Nodes, with a traversal cost.

    Edges are modeled as directional (from_node -> to_node) at the schema
    level, but the pathfinding engine (Phase 2) treats ordinary hallway/room
    edges as bidirectional — you can walk a hallway both ways. `is_transition`
    marks edges that represent moving between floors (stairs/elevator),
    which get a fixed time-cost weight rather than a distance-based one.
    """

    __tablename__ = "edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False)
    # Traversal cost used by A*. For regular edges this is Euclidean pixel
    # distance; for transition edges it's a fixed floor-change cost (Phase 6).
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    is_transition: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Two relationships to the same table (Node), so SQLAlchemy needs to be
    # told explicitly which foreign key backs each direction.
    from_node: Mapped["Node"] = relationship(foreign_keys=[from_node_id])
    to_node: Mapped["Node"] = relationship(foreign_keys=[to_node_id])
