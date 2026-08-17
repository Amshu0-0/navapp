"""Pathfinding engine: turns stored Nodes/Edges into a graph and searches it.

This is the "brain" of the app. Everything upstream (the database, the
seed script) exists to produce Node/Edge rows; everything downstream
(Phase 3's API, Phase 4's map viewer) exists to call into this module and
show the result. The core idea:

  1. Load a floor's Nodes and Edges into a networkx graph.
  2. Run A* search to find the shortest path between two nodes.
  3. For "nearest exit," run the same search against every exit on the
     floor and keep whichever one is cheapest to reach.

A* vs. plain shortest-path (Dijkstra): Dijkstra explores outward in every
direction equally. A* uses a heuristic — an estimate of remaining distance
to the goal — to explore in the goal's general direction first, which is
faster in practice. Our heuristic is straight-line (Euclidean) distance
between two nodes' x/y coordinates. This is provably "admissible" (it never
overestimates the true walking distance, since a straight line is always
the shortest possible path between two points), which guarantees A* still
finds the truly optimal route, not just a fast-to-compute one.
"""

from __future__ import annotations

import math

import networkx as nx
from sqlalchemy.orm import Session

from app.models import Edge, Node, NodeType


class NoPathError(Exception):
    """Raised when no walkable route exists between two nodes."""


def build_floor_graph(db: Session, floor_id: int) -> nx.Graph:
    """Load every Node/Edge on a floor into an undirected weighted graph.

    Undirected because ordinary hallway/room edges are walkable both ways —
    if you can walk from a junction to a door, you can walk back. (Directed
    edges would matter for one-way stairs, but we're not modeling that yet.)

    Each graph node is keyed by the database Node's id; the full Node
    object is stashed as node attribute "data" so callers can get back
    labels/types/coordinates without a second database query.
    """
    graph = nx.Graph()

    nodes = db.query(Node).filter(Node.floor_id == floor_id).all()
    for node in nodes:
        graph.add_node(node.id, data=node)

    node_ids = {node.id for node in nodes}
    edges = (
        db.query(Edge)
        .filter(Edge.from_node_id.in_(node_ids), Edge.to_node_id.in_(node_ids))
        .all()
    )
    for edge in edges:
        graph.add_edge(edge.from_node_id, edge.to_node_id, weight=edge.weight)

    return graph


def _make_euclidean_heuristic(graph: nx.Graph):
    """Build a heuristic(a, b) callback bound to a specific graph.

    networkx's astar_path calls the heuristic as heuristic(node, target) —
    just two node ids, no graph reference — so we close over `graph` here
    to look up each node's coordinates. Returns straight-line pixel
    distance, used by A* to estimate "how much further to the goal" (see
    the module docstring for why this particular heuristic is safe to use).
    """

    def heuristic(a: int, b: int) -> float:
        node_a: Node = graph.nodes[a]["data"]
        node_b: Node = graph.nodes[b]["data"]
        return math.hypot(node_a.x - node_b.x, node_a.y - node_b.y)

    return heuristic


def shortest_path(graph: nx.Graph, start_id: int, end_id: int) -> tuple[list[Node], float]:
    """Find the shortest walkable path between two nodes on the same floor.

    Returns (ordered list of Node objects from start to end, total distance).
    Raises NoPathError if start/end aren't connected (e.g. isolated rooms,
    or ids that don't exist in this graph).
    """
    if start_id not in graph or end_id not in graph:
        raise NoPathError(f"Node {start_id} or {end_id} not found on this floor.")

    try:
        path_ids = nx.astar_path(
            graph, start_id, end_id, heuristic=_make_euclidean_heuristic(graph), weight="weight"
        )
    except nx.NetworkXNoPath as exc:
        raise NoPathError(f"No path between node {start_id} and {end_id}.") from exc

    total_distance = nx.path_weight(graph, path_ids, weight="weight")
    path_nodes = [graph.nodes[node_id]["data"] for node_id in path_ids]
    return path_nodes, total_distance


def nearest_exit(graph: nx.Graph, start_id: int) -> tuple[list[Node], float]:
    """Find the closest EXIT node reachable from `start_id`.

    Runs A* against every exit on the floor and keeps the cheapest result.
    For a building with only a handful of exits per floor, this is simpler
    and plenty fast — no need for a fancier multi-target search algorithm.
    Raises NoPathError if there are no exits on the floor, or none are
    reachable from the start node.
    """
    if start_id not in graph:
        raise NoPathError(f"Node {start_id} not found on this floor.")

    exit_ids = [
        node_id
        for node_id, attrs in graph.nodes(data=True)
        if attrs["data"].type == NodeType.EXIT
    ]
    if not exit_ids:
        raise NoPathError("This floor has no exit nodes.")

    best_path: list[Node] | None = None
    best_distance = math.inf

    for exit_id in exit_ids:
        try:
            path_nodes, distance = shortest_path(graph, start_id, exit_id)
        except NoPathError:
            continue
        if distance < best_distance:
            best_path, best_distance = path_nodes, distance

    if best_path is None:
        raise NoPathError(f"No exit reachable from node {start_id}.")

    return best_path, best_distance
