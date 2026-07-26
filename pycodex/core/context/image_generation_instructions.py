from __future__ import annotations

from dataclasses import dataclass

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class ImageGenerationInstructions(ContextualUserFragmentBase):
    image_output_dir: str
    image_output_path: str

    @classmethod
    def new(cls, image_output_dir: object, image_output_path: object) -> "ImageGenerationInstructions":
        return cls(str(image_output_dir), str(image_output_path))

    @classmethod
    def role(cls) -> str:
        return "developer"

    def body(self) -> str:
        return (
            f"Generated images are saved to {self.image_output_dir} as {self.image_output_path} by default.\n"
            "If you need to use a generated image at another path, copy it and leave the original in place "
            "unless the user explicitly asks you to delete it."
        )


__all__ = ["ImageGenerationInstructions"]
