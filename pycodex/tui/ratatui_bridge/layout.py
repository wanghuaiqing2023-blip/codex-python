"""Small semantic equivalent of ratatui layout values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Optional, Tuple, Union


class Alignment(str, Enum):
    LEFT = "left"
    Left = "left"
    CENTER = "center"
    Center = "center"
    RIGHT = "right"
    Right = "right"


class Direction(str, Enum):
    HORIZONTAL = "horizontal"
    Horizontal = "horizontal"
    VERTICAL = "vertical"
    Vertical = "vertical"


@dataclass(frozen=True)
class Size:
    width: int = 0
    height: int = 0

    @classmethod
    def new(cls, width: int, height: int) -> "Size":
        return cls(max(0, int(width)), max(0, int(height)))


@dataclass(frozen=True)
class Position:
    x: int = 0
    y: int = 0

    @classmethod
    def new(cls, x: int, y: int) -> "Position":
        return cls(int(x), int(y))


@dataclass(frozen=True)
class Offset:
    x: int = 0
    y: int = 0


@dataclass(frozen=True)
class Margin:
    horizontal: int = 0
    vertical: int = 0

    @classmethod
    def new(cls, horizontal: int, vertical: int) -> "Margin":
        return cls(max(0, int(horizontal)), max(0, int(vertical)))


@dataclass(frozen=True)
class Constraint:
    kind: str
    value: int = 0
    value2: int = 1

    @classmethod
    def length(cls, value: int) -> "Constraint":
        return cls("length", max(0, int(value)))

    @classmethod
    def percentage(cls, value: int) -> "Constraint":
        return cls("percentage", max(0, min(100, int(value))))

    @classmethod
    def ratio(cls, numerator: int, denominator: int) -> "Constraint":
        denominator = int(denominator)
        if denominator <= 0:
            raise ValueError("ratio denominator must be positive")
        return cls("ratio", max(0, int(numerator)), denominator)

    @classmethod
    def min(cls, value: int) -> "Constraint":
        return cls("min", max(0, int(value)))

    @classmethod
    def max(cls, value: int) -> "Constraint":
        return cls("max", max(0, int(value)))

    @classmethod
    def fill(cls, scale: int = 1) -> "Constraint":
        return cls("fill", max(1, int(scale)))


Constraint.Length = Constraint.length
Constraint.Percentage = Constraint.percentage
Constraint.Ratio = Constraint.ratio
Constraint.Min = Constraint.min
Constraint.Max = Constraint.max
Constraint.Fill = Constraint.fill


@dataclass(frozen=True)
class Rect:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    @classmethod
    def new(cls, x: int, y: int, width: int, height: int) -> "Rect":
        return cls(int(x), int(y), max(0, int(width)), max(0, int(height)))

    @classmethod
    def from_size(cls, size: Size) -> "Rect":
        return cls(0, 0, size.width, size.height)

    def bottom(self) -> int:
        return self.y + self.height

    def right(self) -> int:
        return self.x + self.width

    def is_empty(self) -> bool:
        return self.width == 0 or self.height == 0

    def area(self) -> int:
        return self.width * self.height

    def as_size(self) -> Size:
        return Size.new(self.width, self.height)

    def position(self) -> Position:
        return Position.new(self.x, self.y)

    def intersection(self, other: "Rect") -> "Rect":
        x1 = max(self.x, other.x)
        y1 = max(self.y, other.y)
        x2 = min(self.right(), other.right())
        y2 = min(self.bottom(), other.bottom())
        return Rect.new(x1, y1, max(0, x2 - x1), max(0, y2 - y1))

    def union(self, other: "Rect") -> "Rect":
        if self.is_empty():
            return other
        if other.is_empty():
            return self
        x1 = min(self.x, other.x)
        y1 = min(self.y, other.y)
        x2 = max(self.right(), other.right())
        y2 = max(self.bottom(), other.bottom())
        return Rect.new(x1, y1, x2 - x1, y2 - y1)

    def offset(self, offset: Offset) -> "Rect":
        return Rect.new(self.x + offset.x, self.y + offset.y, self.width, self.height)

    def inset(self, insets: object) -> "Rect":
        left = max(0, int(getattr(insets, "left", 0)))
        right = max(0, int(getattr(insets, "right", 0)))
        top = max(0, int(getattr(insets, "top", 0)))
        bottom = max(0, int(getattr(insets, "bottom", 0)))
        return Rect.new(
            self.x + left,
            self.y + top,
            max(self.width - left - right, 0),
            max(self.height - top - bottom, 0),
        )

    def inner(self, margin: object = 0, horizontal: Optional[int] = None, vertical: Optional[int] = None) -> "Rect":
        if isinstance(margin, Margin):
            h = margin.horizontal if horizontal is None else int(horizontal)
            v = margin.vertical if vertical is None else int(vertical)
        else:
            base = int(margin)
            h = base if horizontal is None else int(horizontal)
            v = base if vertical is None else int(vertical)
        h = max(0, h)
        v = max(0, v)
        return Rect.new(self.x + h, self.y + v, max(self.width - h * 2, 0), max(self.height - v * 2, 0))

    def clamp_size(self, width: Optional[int] = None, height: Optional[int] = None) -> "Rect":
        return Rect.new(
            self.x,
            self.y,
            min(self.width, int(width)) if width is not None else self.width,
            min(self.height, int(height)) if height is not None else self.height,
        )


class Layout:
    """Portable subset of ratatui's rectangular layout splitter."""

    def __init__(
        self,
        direction: Direction = Direction.VERTICAL,
        constraints: Iterable[Constraint] = (),
        margin: Union[int, Margin] = 0,
    ) -> None:
        self.direction = direction if isinstance(direction, Direction) else Direction(direction)
        self.constraints = tuple(constraints)
        self.margin = margin if isinstance(margin, Margin) else Margin.new(int(margin), int(margin))

    @classmethod
    def default(cls) -> "Layout":
        return cls()

    @classmethod
    def vertical(cls, constraints: Iterable[Constraint]) -> "Layout":
        return cls(Direction.VERTICAL, constraints)

    @classmethod
    def horizontal(cls, constraints: Iterable[Constraint]) -> "Layout":
        return cls(Direction.HORIZONTAL, constraints)

    def direction_(self, direction: Direction) -> "Layout":
        return Layout(direction=direction, constraints=self.constraints, margin=self.margin)

    def constraints_(self, constraints: Iterable[Constraint]) -> "Layout":
        return Layout(direction=self.direction, constraints=constraints, margin=self.margin)

    def margin_(self, margin: Union[int, Margin]) -> "Layout":
        return Layout(direction=self.direction, constraints=self.constraints, margin=margin)

    def split(self, area: Rect) -> List[Rect]:
        inner = area.inner(self.margin)
        available = inner.width if self.direction is Direction.HORIZONTAL else inner.height
        sizes = _resolve_constraints(available, self.constraints)
        result = []
        cursor = inner.x if self.direction is Direction.HORIZONTAL else inner.y
        for size in sizes:
            if self.direction is Direction.HORIZONTAL:
                result.append(Rect.new(cursor, inner.y, size, inner.height))
                cursor += size
            else:
                result.append(Rect.new(inner.x, cursor, inner.width, size))
                cursor += size
        return result

    def areas(self, area: Rect) -> Tuple[Rect, ...]:
        return tuple(self.split(area))


def _resolve_constraints(available: int, constraints: Tuple[Constraint, ...]) -> List[int]:
    available = max(0, int(available))
    if not constraints:
        return []

    sizes = [0 for _ in constraints]
    fill_indices = []
    minimum_indices = []

    for index, constraint in enumerate(constraints):
        if constraint.kind == "length":
            sizes[index] = constraint.value
        elif constraint.kind == "percentage":
            sizes[index] = available * constraint.value // 100
        elif constraint.kind == "ratio":
            sizes[index] = available * constraint.value // constraint.value2
        elif constraint.kind == "min":
            sizes[index] = constraint.value
            minimum_indices.append(index)
        elif constraint.kind == "max":
            sizes[index] = min(available, constraint.value)
        elif constraint.kind == "fill":
            fill_indices.append(index)
        else:
            raise ValueError("unknown layout constraint: %s" % constraint.kind)

    used = sum(sizes)
    if used > available:
        return _clip_sequentially(sizes, available)

    remaining = available - used
    if fill_indices:
        total_scale = sum(constraints[index].value for index in fill_indices)
        allocated = 0
        for offset_index, index in enumerate(fill_indices):
            if offset_index == len(fill_indices) - 1:
                share = remaining - allocated
            else:
                share = remaining * constraints[index].value // total_scale
                allocated += share
            sizes[index] = share
    elif minimum_indices and remaining > 0:
        share, extra = divmod(remaining, len(minimum_indices))
        for offset_index, index in enumerate(minimum_indices):
            sizes[index] += share + (1 if offset_index < extra else 0)

    return _clip_sequentially(sizes, available)


def _clip_sequentially(sizes: List[int], available: int) -> List[int]:
    remaining = max(0, int(available))
    result = []
    for size in sizes:
        clipped = min(max(0, int(size)), remaining)
        result.append(clipped)
        remaining -= clipped
    return result


__all__ = [
    "Alignment",
    "Constraint",
    "Direction",
    "Layout",
    "Margin",
    "Offset",
    "Position",
    "Rect",
    "Size",
]
