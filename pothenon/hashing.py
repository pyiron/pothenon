from __future__ import annotations

import hashlib
import json
from typing import Any

import networkx as nx


def _hash(data: Any) -> str:
    """Create a deterministic hash from JSON-serializable data."""
    payload = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _intrinsic_data(package_info: "PackageInfo") -> dict[str, Any]:
    """Return the part of a function's identity independent of dependencies."""
    if package_info.info.has_version:
        return {
            "kind": "versioned",
            "module": package_info.info.module,
            "qualname": package_info.info.qualname,
            "version": package_info.info.version,
        }

    return {
        "kind": "source",
        "code": package_info.source_code,
    }


def hash_package_info(package_info: "PackageInfo") -> str:
    """
    Return a deterministic identifier for a function and its dependencies.

    Dependencies are treated as unordered.

    Cyclic dependencies are handled by grouping mutually recursive functions
    into strongly connected components.
    """

    graph = nx.DiGraph()
    packages = {}

    def collect(pkg) -> int:
        # Object identity is only used internally while constructing the graph.
        node = id(pkg)

        if node in packages:
            return node

        packages[node] = pkg
        graph.add_node(node)

        for dependency in (pkg.dependency or {}).values():
            dependency_node = collect(dependency)
            graph.add_edge(node, dependency_node)

        return node

    root = collect(package_info)

    # Hash each function independently of its dependencies.
    intrinsic_hashes = {
        node: _hash(_intrinsic_data(pkg)) for node, pkg in packages.items()
    }

    # Find mutually recursive groups.
    components = list(nx.strongly_connected_components(graph))

    component_of = {
        node: component_id
        for component_id, component in enumerate(components)
        for node in component
    }

    # Collapse SCCs. The resulting graph is guaranteed to be acyclic.
    component_graph = nx.condensation(graph, scc=components)

    component_hashes: dict[int, str] = {}

    # graph edges are:
    #
    #     function -> dependency
    #
    # so reversing topological order processes dependencies first.
    for component_id in reversed(list(nx.topological_sort(component_graph))):
        members = components[component_id]

        # Preserve the topology within a recursive component.
        internal_edges = sorted(
            (intrinsic_hashes[source], intrinsic_hashes[target])
            for source, target in graph.edges
            if source in members and target in members
        )

        # Dependencies outside the recursive component have already been
        # hashed because we're traversing in reverse topological order.
        external_dependencies = sorted(
            {
                component_hashes[component_of[target]]
                for source, target in graph.edges
                if source in members and target not in members
            }
        )

        component_hashes[component_id] = _hash(
            {
                "members": sorted(intrinsic_hashes[node] for node in members),
                "internal_edges": internal_edges,
                "dependencies": external_dependencies,
            }
        )

    root_component_hash = component_hashes[component_of[root]]

    # The SCC hash describes the complete recursive context. Combining it
    # with the root's intrinsic hash ensures that two different functions
    # within the same SCC still get different identifiers.
    return _hash(
        {
            "function": intrinsic_hashes[root],
            "component": root_component_hash,
        }
    )
