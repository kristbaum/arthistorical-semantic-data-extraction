"""Surya model management — only one model in VRAM at a time for 6 GB GPUs."""

import logging

log = logging.getLogger(__name__)

_layout_predictor = None
_recognition_predictor = None


def _free_gpu():
    """Free CUDA memory between model loads."""
    import gc
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def get_layout_predictor():
    """Load (or return cached) Surya LayoutPredictor, unloading recognition first."""
    global _layout_predictor, _recognition_predictor
    if _layout_predictor is None:
        if _recognition_predictor is not None:
            log.info("Unloading recognition model …")
            del _recognition_predictor
            _recognition_predictor = None
            _free_gpu()

        from surya.foundation import FoundationPredictor
        from surya.layout import LayoutPredictor
        from surya.settings import settings

        log.info("Loading Surya layout model …")
        _layout_predictor = LayoutPredictor(
            FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        )
    return _layout_predictor


def get_recognition_predictor():
    """Load (or return cached) Surya RecognitionPredictor, unloading layout first."""
    global _layout_predictor, _recognition_predictor
    if _recognition_predictor is None:
        if _layout_predictor is not None:
            log.info("Unloading layout model …")
            del _layout_predictor
            _layout_predictor = None
            _free_gpu()

        from surya.foundation import FoundationPredictor
        from surya.recognition import RecognitionPredictor

        log.info("Loading Surya recognition model …")
        _recognition_predictor = RecognitionPredictor(FoundationPredictor())
    return _recognition_predictor
