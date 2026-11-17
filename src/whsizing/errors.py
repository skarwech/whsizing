"""Exception hierarchy and CLI exit codes (§2.7)."""


class WhsizingError(Exception):
    """Unexpected failure; traceback goes to logs/run.log."""

    exit_code: int = 1


class ConfigError(WhsizingError):
    """Invalid YAML, unknown key or parameter id."""

    exit_code = 2


class MappingError(WhsizingError):
    """Required column unmapped in non-interactive mode."""

    exit_code = 2


class DataQualityError(WhsizingError):
    """At least one blocking data-quality issue (R-rules)."""

    exit_code = 3


class SizingInfeasibleError(WhsizingError):
    """`--strict` only: no scenario fits the building, or a required input is missing."""

    exit_code = 4


class ReportIntegrityError(WhsizingError):
    """A report integrity check (IC1..IC8) failed."""

    exit_code = 5
