from .models import PipelineResult, PipelineStatistics

__all__ = ["BlockSangamPipeline", "PipelineResult", "PipelineStatistics"]


def __getattr__(name: str):
    if name == "BlockSangamPipeline":
        from .runner import BlockSangamPipeline

        return BlockSangamPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
