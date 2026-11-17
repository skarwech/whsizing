"""Synthetic data generator (F1): profile YAML → canonical frames → Parquet + CSV EN/FR."""

from whsizing.synth.defects import inject_defects
from whsizing.synth.export import export, render_csv, synthesize
from whsizing.synth.generator import generate
from whsizing.synth.profile import DefectCfg, SynthProfile, daily_lambda, load_synth_profile

__all__ = [
    "DefectCfg",
    "SynthProfile",
    "daily_lambda",
    "export",
    "generate",
    "inject_defects",
    "load_synth_profile",
    "render_csv",
    "synthesize",
]
