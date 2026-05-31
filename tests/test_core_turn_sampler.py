import unittest
from collections.abc import Sequence

from pycodex.core.turn_sampler import response_items_from_transport_result
from pycodex.protocol import ContentItem, ResponseItem


class ResponseSequence(Sequence):
    def __init__(self, items):
        self._items = tuple(items)

    def __getitem__(self, index):
        return self._items[index]

    def __len__(self):
        return len(self._items)


class TurnSamplerTests(unittest.TestCase):
    def test_response_items_from_transport_result_accepts_sequence(self) -> None:
        first = ResponseItem.message("assistant", (ContentItem.output_text("one"),))
        second = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "two"}],
        }

        items = response_items_from_transport_result(ResponseSequence((first, second)))

        self.assertEqual(items[0], first)
        self.assertEqual(items[1].content[0].text, "two")

    def test_response_items_from_transport_result_rejects_text_sequence(self) -> None:
        with self.assertRaisesRegex(TypeError, "transport result"):
            response_items_from_transport_result("not response items")


if __name__ == "__main__":
    unittest.main()
