from pycodex.tui.bottom_pane.mentions_v2 import MentionV2Popup
from pycodex.tui.bottom_pane.mentions_v2 import MentionV2Selection
from pycodex.tui.bottom_pane.mentions_v2 import build_search_catalog
from pycodex.tui.bottom_pane.mentions_v2.candidate import Selection
from pycodex.tui.bottom_pane.mentions_v2.popup import Popup
from pycodex.tui.bottom_pane.mentions_v2.search_catalog import build_search_catalog as catalog_builder


def test_mentions_v2_parent_module_reexports_rust_public_items():
    # Rust source: bottom_pane/mentions_v2/mod.rs.
    assert MentionV2Selection is Selection
    assert MentionV2Popup is Popup
    assert build_search_catalog is catalog_builder
