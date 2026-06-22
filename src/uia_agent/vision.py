"""OCR + bounding-box vision fallback (optional, gated extra).

The UIA-first happy path never touches this module. It is consulted *only* when
the pruned UIA tree yields zero actionable nodes for a step — the case where a
legacy app draws its own controls (owner-draw / GDI / a screenshot-in-a-pane)
and exposes nothing the accessibility tree can act on. Rather than logging and
exiting, the agent takes a screenshot, runs OCR, and surfaces clickable text
regions the LLM can target by coordinate.

Install the heavy dependencies with the optional extra::

    pip install uia-agent[vision]

which pulls `pytesseract` (a Tesseract OCR binding) and `pillow`. The core
package stays dependency-free: the imports here are lazy, and the OCR engine is
injectable so the decision logic can be unit-tested with no native deps.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .uia_tree import UIANode

# An actionable node is one the agent can dispatch a click/type/select against:
# it must be enabled and expose at least one of these interaction patterns.
_ACTIONABLE_PATTERNS = frozenset(
    {"Invoke", "Value", "Toggle", "ExpandCollapse", "SelectionItem"}
)


class TextRegion(BaseModel):
    """One OCR-detected clickable text region, targetable by its center point."""

    text: str = Field(description="Recognized text in the region.")
    bbox: tuple[int, int, int, int] = Field(
        description="(left, top, right, bottom) screen coords of the region."
    )
    confidence: float = Field(
        default=0.0, description="OCR confidence in [0, 1]; higher is better."
    )

    @property
    def center(self) -> tuple[int, int]:
        """The click point: the midpoint of the bounding box."""
        left, top, right, bottom = self.bbox
        return ((left + right) // 2, (top + bottom) // 2)


class VisionUnavailable(RuntimeError):
    """Raised when the vision fallback is requested but its extras are missing."""


class OCREngine(Protocol):
    """The single call the fallback makes; satisfied by the default Tesseract
    engine or any injected stub (used in tests)."""

    def regions(self, image: Any) -> list[TextRegion]: ...


def _count_actionable(node: UIANode) -> int:
    """Count nodes in a snapshot the agent could actually dispatch against."""
    count = 0
    if node.enabled and (set(node.patterns) & _ACTIONABLE_PATTERNS):
        count += 1
    for child in node.children:
        count += _count_actionable(child)
    return count


def tree_has_actionable_nodes(root: UIANode) -> bool:
    """True when the pruned UIA tree exposes at least one actionable node.

    The agent loop calls this to decide whether the UIA-first path can proceed.
    When it returns ``False`` *and* vision is enabled, the loop consults
    :func:`fallback_regions` instead of giving up.
    """
    return _count_actionable(root) > 0


class TesseractEngine:
    """Default OCR engine backed by ``pytesseract`` (the ``[vision]`` extra).

    Imports are lazy so importing :mod:`uia_agent.vision` never requires the
    native Tesseract binary or its Python binding to be installed.
    """

    def __init__(self, *, min_confidence: float = 0.4) -> None:
        self._min_confidence = min_confidence

    def regions(self, image: Any) -> list[TextRegion]:
        try:
            import pytesseract
            from pytesseract import Output
        except ImportError as exc:  # pragma: no cover - exercised only without extra
            raise VisionUnavailable(
                "OCR fallback needs the vision extra; install with "
                "`pip install uia-agent[vision]` (pulls pytesseract + pillow) and "
                "ensure the Tesseract binary is on PATH"
            ) from exc

        data = pytesseract.image_to_data(image, output_type=Output.DICT)
        out: list[TextRegion] = []
        for i, raw in enumerate(data.get("text", [])):
            text = (raw or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i]) / 100.0
            except (KeyError, ValueError, TypeError):
                conf = 0.0
            if conf < self._min_confidence:
                continue
            left = int(data["left"][i])
            top = int(data["top"][i])
            width = int(data["width"][i])
            height = int(data["height"][i])
            out.append(
                TextRegion(
                    text=text,
                    bbox=(left, top, left + width, top + height),
                    confidence=conf,
                )
            )
        return out


def _default_screenshotter(app: str) -> Any:
    """Grab a screenshot of the focused window for ``app`` (lazy, optional)."""
    try:
        import uiautomation as auto
    except ImportError as exc:  # pragma: no cover - exercised only without extra
        raise VisionUnavailable(
            "vision fallback needs a live Windows session with uiautomation"
        ) from exc

    from .uia_tree import _find_window

    window = _find_window(app)
    rect = getattr(window, "BoundingRectangle", None)
    capture = getattr(auto, "GetScreenshot", None) or getattr(auto, "Capture", None)
    if capture is None:  # pragma: no cover - depends on uiautomation build
        raise VisionUnavailable("uiautomation build exposes no screenshot helper")
    return capture(rect) if rect is not None else capture()


def fallback_regions(
    app: str,
    *,
    ocr: OCREngine | None = None,
    screenshotter: Callable[[str], Any] | None = None,
) -> list[TextRegion]:
    """Screenshot ``app``, OCR it, and return clickable text regions.

    Both the OCR engine and the screenshotter are injectable so the decision
    path is unit-testable with no native dependencies. In production both
    default to the lazy Tesseract / uiautomation implementations.
    """
    shoot = screenshotter or _default_screenshotter
    engine = ocr or TesseractEngine()
    image = shoot(app)
    return engine.regions(image)
