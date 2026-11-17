"""One scenario in one world: where its F6 quantities are read, which Params apply and where the
finance nodes are traced. Built by `compute_finance`; capex.py and opex.py take it as input."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from whsizing.catalog import ParamSet
from whsizing.errors import WhsizingError
from whsizing.schemas import DesignBasis, FamilyId, ScenarioResult, World
from whsizing.schemas.trace import Tracer

MANUAL: FamilyId = "manual_p2p"


@dataclass(frozen=True, eq=False)
class Ctx:
    """`source` holds the F6 nodes of `result` (all three worlds, I62); finance nodes are
    recorded in `sink` (the scenario's own Tracer, or a scratch one for a baseline)."""

    result: ScenarioResult
    basis: DesignBasis
    params: ParamSet
    world: World
    source: Tracer
    sink: Tracer
    role_costs: Mapping[str, float]  # role -> EUR/h: catalog defaults replaced by the client's

    @property
    def sid(self) -> str:
        return self.result.scenario.id

    @property
    def fam(self) -> FamilyId:
        """The family whose cost formulas apply: the scenario's, or manual_p2p for an automated
        scenario without eligible line (I48: it costs what the manual scenario costs)."""
        fam = self.result.scenario.family
        return fam if self.result.eligibility.share_lines > 0 else MANUAL

    @property
    def auto(self) -> bool:
        return self.fam != MANUAL

    @property
    def zone(self) -> str:
        """Trace prefix of the manual storage classes: `overflow.` for every automated family,
        also a degenerate one (F6 files its manual classes under the overflow zone, I48)."""
        return "" if self.result.scenario.family == MANUAL else "overflow."

    def tid(self, key: str) -> str:
        """Trace id of a scenario quantity: `<scenario id>.<key>`."""
        return f"{self.sid}.{key}"

    def q(self, key: str) -> float:
        """F6 quantity `<scenario id>.<key>` in this world."""
        try:
            return self.source.get(self.tid(key), self.world).value
        except KeyError:
            raise WhsizingError(
                f"finance: no F6 trace node {self.tid(key)!r} in the {self.world} world; pass the "
                "Tracer of the size_scenario run that produced this ScenarioResult"
            ) from None

    def v(self, param_id: str) -> float:
        """Catalog value in this world (after basis and scenario overrides)."""
        return self.params.value(param_id, self.world)

    def rec(
        self, key: str, label: str, value: float, unit: str, formula: str, inputs: dict[str, str]
    ) -> float:
        """Trace `<scenario id>.<key>` in this world; returns `value`."""
        return self.sink.record(
            self.tid(key), label, value, unit, formula, inputs, scope=self.sid, world=self.world
        )
