"""FieldShift V3 scientific decision-support engine.

Load the engine lazily so the standard-library AppEEARS smoke test can run
in Termux without first installing FastAPI, Earth Engine, or PyYAML.
"""
__all__ = ["run_v3"]


def __getattr__(name):
    if name == "run_v3":
        from .pipeline import run_v3
        return run_v3
    raise AttributeError(name)
