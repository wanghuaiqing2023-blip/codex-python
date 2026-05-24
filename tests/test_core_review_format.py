import unittest
from pathlib import Path

from pycodex.core import (
    REVIEW_FALLBACK_MESSAGE,
    format_location,
    format_review_findings_block,
    render_review_output_text,
)
from pycodex.protocol import (
    ReviewCodeLocation,
    ReviewFinding,
    ReviewLineRange,
    ReviewOutputEvent,
)


class CoreReviewFormatTests(unittest.TestCase):
    def finding(
        self,
        title: str,
        body: str = "Body line.",
        *,
        start: int = 10,
        end: int = 12,
        path: str = "C:/repo/app.py",
    ) -> ReviewFinding:
        return ReviewFinding(
            title=title,
            body=body,
            confidence_score=0.9,
            priority=1,
            code_location=ReviewCodeLocation(
                Path(path),
                ReviewLineRange(start, end),
            ),
        )

    def test_format_location_uses_path_and_line_range(self) -> None:
        item = self.finding("Bug", path="C:/repo/pkg/app.py", start=3, end=4)

        self.assertEqual(
            format_location(item),
            f"{Path('C:/repo/pkg/app.py')}:3-4",
        )

    def test_format_review_findings_block_omits_selection_by_default(self) -> None:
        first = self.finding("First", "Line one.\nLine two.", start=1, end=2)
        second = self.finding("Second", "Another body.", start=8, end=8)

        self.assertEqual(
            format_review_findings_block((first, second)),
            (
                "\n"
                "Full review comments:\n"
                "\n"
                f"- First \u2014 {Path('C:/repo/app.py')}:1-2\n"
                "  Line one.\n"
                "  Line two.\n"
                "\n"
                f"- Second \u2014 {Path('C:/repo/app.py')}:8-8\n"
                "  Another body."
            ),
        )

    def test_format_review_findings_block_applies_selection_flags(self) -> None:
        first = self.finding("Selected", start=1, end=1)
        second = self.finding("Unselected", start=2, end=3)
        third = self.finding("Default selected", start=4, end=5)

        self.assertEqual(
            format_review_findings_block((first, second, third), selection=(True, False)),
            (
                "\n"
                "Full review comments:\n"
                "\n"
                f"- [x] Selected \u2014 {Path('C:/repo/app.py')}:1-1\n"
                "  Body line.\n"
                "\n"
                f"- [ ] Unselected \u2014 {Path('C:/repo/app.py')}:2-3\n"
                "  Body line.\n"
                "\n"
                f"- [x] Default selected \u2014 {Path('C:/repo/app.py')}:4-5\n"
                "  Body line."
            ),
        )

    def test_format_review_findings_block_uses_single_comment_header(self) -> None:
        item = self.finding("Only", "One body.", start=6, end=7)

        self.assertEqual(
            format_review_findings_block((item,)),
            (
                "\n"
                "Review comment:\n"
                "\n"
                f"- Only \u2014 {Path('C:/repo/app.py')}:6-7\n"
                "  One body."
            ),
        )

    def test_render_review_output_text_combines_explanation_and_findings(self) -> None:
        item = self.finding("Bug", "The branch can fail.")
        output = ReviewOutputEvent((item,), "patch is incorrect", " because \n", 0.8)

        self.assertEqual(
            render_review_output_text(output),
            (
                "because\n"
                "\n"
                "Review comment:\n"
                "\n"
                f"- Bug \u2014 {Path('C:/repo/app.py')}:10-12\n"
                "  The branch can fail."
            ),
        )

    def test_render_review_output_text_handles_findings_only_and_fallback(self) -> None:
        item = self.finding("Bug")

        self.assertEqual(
            render_review_output_text(ReviewOutputEvent((item,), "", "", 0.0)),
            (
                "Review comment:\n"
                "\n"
                f"- Bug \u2014 {Path('C:/repo/app.py')}:10-12\n"
                "  Body line."
            ),
        )
        self.assertEqual(render_review_output_text(ReviewOutputEvent()), REVIEW_FALLBACK_MESSAGE)


if __name__ == "__main__":
    unittest.main()
