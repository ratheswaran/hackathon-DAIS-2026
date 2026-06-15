"""Thin Neo4j driver wrapper + GDS helpers."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from neo4j import GraphDatabase

from . import config


class Neo4j:
    def __init__(self, uri: str | None = None, user: str | None = None,
                 password: str | None = None, database: str | None = None):
        self.database = database or config.NEO4J_DATABASE
        self._driver = GraphDatabase.driver(
            uri or config.NEO4J_URI,
            auth=(user or config.NEO4J_USER, password or config.NEO4J_PASSWORD),
        )

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4j":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def run(self, cypher: str, **params: Any) -> list[dict]:
        with self._driver.session(database=self.database) as s:
            return [r.data() for r in s.run(cypher, **params)]

    def run_one(self, cypher: str, **params: Any) -> dict | None:
        rows = self.run(cypher, **params)
        return rows[0] if rows else None

    @contextmanager
    def session(self):
        with self._driver.session(database=self.database) as s:
            yield s

    # --- GDS projection lifecycle ------------------------------------------
    def drop_graph_if_exists(self, name: str) -> None:
        # No-op when GDS is absent (e.g. Aura Free) — there are no projections
        # to drop in that case, and the offline analytics path never makes any.
        try:
            self.run(
                "CALL gds.graph.exists($name) YIELD exists "
                "WITH exists WHERE exists CALL gds.graph.drop($name) YIELD graphName "
                "RETURN graphName",
                name=name,
            )
        except Exception:
            pass

    def verify(self) -> dict:
        comp = self.run_one(
            "CALL dbms.components() YIELD name, versions, edition "
            "RETURN name AS name, versions[0] AS version, edition AS edition"
        )
        # gds.version() throws on Aura Free / any Neo4j without the GDS plugin.
        # The offline analytics backend doesn't need it, so treat absence as None.
        try:
            gds = self.run_one("RETURN gds.version() AS v")
            gds_ver = gds["v"] if gds else None
        except Exception:
            gds_ver = None
        return {"neo4j": comp, "gds": gds_ver}
