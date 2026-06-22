import unittest

from pycodex.codex_api.search import AllowedCaller
from pycodex.codex_api.search import ApproximateLocation
from pycodex.codex_api.search import ClickOperation
from pycodex.codex_api.search import FinanceAssetType
from pycodex.codex_api.search import FinanceOperation
from pycodex.codex_api.search import FindOperation
from pycodex.codex_api.search import OpenOperation
from pycodex.codex_api.search import ScreenshotOperation
from pycodex.codex_api.search import SearchCommands
from pycodex.codex_api.search import SearchContextSize
from pycodex.codex_api.search import SearchFilters
from pycodex.codex_api.search import SearchImageSettings
from pycodex.codex_api.search import SearchInput
from pycodex.codex_api.search import SearchQuery
from pycodex.codex_api.search import SearchRequest
from pycodex.codex_api.search import SearchResponse
from pycodex.codex_api.search import SearchResponseLength
from pycodex.codex_api.search import SearchSettings
from pycodex.codex_api.search import SportsFunction
from pycodex.codex_api.search import SportsLeague
from pycodex.codex_api.search import SportsOperation
from pycodex.codex_api.search import SportsToolName
from pycodex.codex_api.search import TimeOperation
from pycodex.codex_api.search import WeatherOperation
from pycodex.protocol import ContentItem
from pycodex.protocol import ResponseItem


class CodexApiSearchRsTest(unittest.TestCase):
    # Rust: codex-api/src/search.rs plus
    # tests in codex-api/tests/endpoint/search.rs.
    def test_search_request_matches_endpoint_rust_body_shape(self) -> None:
        request = SearchRequest(
            id="search-session",
            model="gpt-test",
            input=SearchInput.items(
                [
                    ResponseItem.message(
                        role="user",
                        content=[
                            ContentItem.input_text("find this"),
                            ContentItem.input_image("https://example.com/image.png"),
                        ],
                    )
                ]
            ),
            commands=SearchCommands(
                search_query=[
                    SearchQuery(q="OpenAI news", recency=7, domains=["openai.com"])
                ],
                open=[OpenOperation(ref_id="https://openai.com", lineno=12)],
            ),
            settings=SearchSettings(
                user_location=ApproximateLocation(country="US", city="San Francisco"),
                search_context_size=SearchContextSize.LOW,
                filters=SearchFilters(
                    allowed_domains=["openai.com"],
                    blocked_domains=["example.com"],
                ),
                image_settings=SearchImageSettings(max_results=4, caption=True),
                allowed_callers=[AllowedCaller.DIRECT],
                external_web_access=True,
            ),
            max_output_tokens=2500,
        )

        self.assertEqual(
            request.to_json_dict(),
            {
                "id": "search-session",
                "model": "gpt-test",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "find this"},
                            {
                                "type": "input_image",
                                "image_url": "https://example.com/image.png",
                            },
                        ],
                    }
                ],
                "commands": {
                    "search_query": [
                        {
                            "q": "OpenAI news",
                            "recency": 7,
                            "domains": ["openai.com"],
                        }
                    ],
                    "open": [{"ref_id": "https://openai.com", "lineno": 12}],
                },
                "settings": {
                    "user_location": {
                        "type": "approximate",
                        "country": "US",
                        "city": "San Francisco",
                    },
                    "search_context_size": "low",
                    "filters": {
                        "allowed_domains": ["openai.com"],
                        "blocked_domains": ["example.com"],
                    },
                    "image_settings": {"max_results": 4, "caption": True},
                    "allowed_callers": ["direct"],
                    "external_web_access": True,
                },
                "max_output_tokens": 2500,
            },
        )

    def test_search_input_text_is_untagged_string(self) -> None:
        self.assertEqual(
            SearchRequest(id="sid", input=SearchInput.text("hello")).to_json_dict(),
            {"id": "sid", "input": "hello"},
        )
        self.assertEqual(
            SearchRequest(id="sid", input="hello").to_json_dict(),
            {"id": "sid", "input": "hello"},
        )

    def test_search_commands_cover_operation_wire_names_and_enum_values(self) -> None:
        commands = SearchCommands(
            image_query=[SearchQuery(q="waterfalls")],
            click=[ClickOperation(ref_id="r1", id=17)],
            find=[FindOperation(ref_id="r1", pattern="needle")],
            screenshot=[ScreenshotOperation(ref_id="doc", pageno=3)],
            finance=[FinanceOperation(ticker="BTC", type=FinanceAssetType.CRYPTO)],
            weather=[WeatherOperation(location="San Francisco, CA", duration=7)],
            sports=[
                SportsOperation(
                    tool=SportsToolName.SPORTS,
                    fn=SportsFunction.SCHEDULE,
                    league=SportsLeague.NFL,
                    team="SF",
                    num_games=2,
                )
            ],
            time=[TimeOperation(utc_offset="+03:00")],
            response_length=SearchResponseLength.LONG,
        )

        self.assertEqual(
            commands.to_json_dict(),
            {
                "image_query": [{"q": "waterfalls"}],
                "click": [{"ref_id": "r1", "id": 17}],
                "find": [{"ref_id": "r1", "pattern": "needle"}],
                "screenshot": [{"ref_id": "doc", "pageno": 3}],
                "finance": [{"ticker": "BTC", "type": "crypto"}],
                "weather": [{"location": "San Francisco, CA", "duration": 7}],
                "sports": [
                    {
                        "fn": "schedule",
                        "league": "nfl",
                        "tool": "sports",
                        "team": "SF",
                        "num_games": 2,
                    }
                ],
                "time": [{"utc_offset": "+03:00"}],
                "response_length": "long",
            },
        )

    def test_search_settings_skip_absent_fields_and_snake_case_allowed_callers(
        self,
    ) -> None:
        settings = SearchSettings(
            user_location=ApproximateLocation(region="CA", timezone="America/Los_Angeles"),
            allowed_callers=[AllowedCaller.SHELL, AllowedCaller.CODE_INTERPRETER],
        )

        self.assertEqual(
            settings.to_json_dict(),
            {
                "user_location": {
                    "type": "approximate",
                    "region": "CA",
                    "timezone": "America/Los_Angeles",
                },
                "allowed_callers": ["shell", "code_interpreter"],
            },
        )

    def test_search_enums_cover_all_rust_wire_values(self) -> None:
        # Rust module: codex-api/src/search.rs
        # Contract: serde(rename_all) fixes all enum wire values.
        self.assertEqual(
            {item.value for item in FinanceAssetType},
            {"equity", "fund", "crypto", "index"},
        )
        self.assertEqual({item.value for item in SportsToolName}, {"sports"})
        self.assertEqual(
            {item.value for item in SportsFunction},
            {"schedule", "standings"},
        )
        self.assertEqual(
            {item.value for item in SportsLeague},
            {"nba", "wnba", "nfl", "nhl", "mlb", "epl", "ncaamb", "ncaawb", "ipl"},
        )
        self.assertEqual(
            {item.value for item in SearchResponseLength},
            {"short", "medium", "long"},
        )
        self.assertEqual({AllowedCaller.CODE_INTERPRETER.value}, {"code_interpreter"})

    def test_u64_fields_reject_negative_and_bool_values(self) -> None:
        # Rust module: codex-api/src/search.rs
        # Contract: fields typed as u64 cannot be negative or boolean values.
        cases = [
            lambda value: SearchQuery(q="q", recency=value),
            lambda value: OpenOperation(ref_id="r", lineno=value),
            lambda value: ClickOperation(ref_id="r", id=value),
            lambda value: ScreenshotOperation(ref_id="r", pageno=value),
            lambda value: WeatherOperation(location="US, CA, SF", duration=value),
            lambda value: SportsOperation(
                fn=SportsFunction.SCHEDULE,
                league=SportsLeague.NFL,
                num_games=value,
            ),
            lambda value: SearchImageSettings(max_results=value),
            lambda value: SearchRequest(id="sid", max_output_tokens=value),
        ]

        for factory in cases:
            for value in (-1, True):
                with self.subTest(factory=factory, value=value):
                    with self.assertRaisesRegex(ValueError, "non-negative integer"):
                        factory(value)

    def test_search_response_decodes_encrypted_output(self) -> None:
        response = SearchResponse.from_json_dict({"encrypted_output": "ciphertext"})

        self.assertEqual(response.encrypted_output, "ciphertext")
        with self.assertRaisesRegex(ValueError, "encrypted_output"):
            SearchResponse.from_json_dict({})


if __name__ == "__main__":
    unittest.main()
