import httpx
import pytest
from livekit.agents.llm import ToolError

import tools as assistant_tools
from agent import _simulation_tool_mocks
from tools import AssistantTools


async def invoke(tool_name: str, *args: object) -> object:
    tool = getattr(AssistantTools, tool_name)
    return await tool._func(AssistantTools(), None, *args)


def test_assistant_registers_only_supported_callable_tools():
    assert [tool.info.name for tool in AssistantTools().tools] == [
        "search_the_web",
        "get_weather",
        "define_word",
    ]


def mock_httpx(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    async_client = httpx.AsyncClient

    def make_client(*, timeout: float) -> httpx.AsyncClient:
        return async_client(transport=httpx.MockTransport(handler), timeout=timeout)

    monkeypatch.setattr(assistant_tools.httpx, "AsyncClient", make_client)


@pytest.mark.asyncio
async def test_search_strips_query_and_limits_results(monkeypatch: pytest.MonkeyPatch):
    observed: dict[str, object] = {}

    class FakeDDGS:
        def text(self, query: str, *, max_results: int) -> list[dict[str, str]]:
            observed.update(query=query, max_results=max_results)
            return [{"title": "Result"}]

    monkeypatch.setattr(assistant_tools, "DDGS", FakeDDGS)

    result = await invoke("search_the_web", "  livekit agents  ")

    assert result == [{"title": "Result"}]
    assert observed == {"query": "livekit agents", "max_results": 5}


@pytest.mark.asyncio
async def test_search_rejects_empty_query():
    with pytest.raises(ToolError, match="provide a search query"):
        await invoke("search_the_web", "  ")


@pytest.mark.asyncio
async def test_simulation_mocks_default_to_empty_without_scenario_fixtures():
    mocks = _simulation_tool_mocks({})

    assert await mocks["search_the_web"](query="anything") == []
    assert await mocks["get_weather"](location="anywhere") == {}
    assert await mocks["define_word"](word="anything") == {}


@pytest.mark.asyncio
async def test_simulation_mocks_return_scenario_fixtures():
    expected = {"word": "ephemeral", "meanings": []}
    mocks = _simulation_tool_mocks({"tool_results": {"define_word": expected}})

    assert await mocks["define_word"](word="ephemeral") == expected


@pytest.mark.asyncio
async def test_weather_requests_clarification_for_ambiguous_city(
    monkeypatch: pytest.MonkeyPatch,
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "Springfield",
                        "admin1": "Illinois",
                        "country": "United States",
                        "latitude": 39.8,
                        "longitude": -89.6,
                    },
                    {
                        "name": "Springfield",
                        "admin1": "Oregon",
                        "country": "United States",
                        "latitude": 44.0,
                        "longitude": -123.0,
                    },
                ]
            },
        )

    mock_httpx(monkeypatch, handler)

    with pytest.raises(ToolError, match="specify the country or region") as error:
        await invoke("get_weather", "Springfield")

    assert "Illinois" in str(error.value)
    assert "Oregon" in str(error.value)
    assert len(requests) == 1
    assert requests[0].url.params["count"] == "5"


@pytest.mark.asyncio
async def test_weather_uses_region_to_resolve_duplicate_city(
    monkeypatch: pytest.MonkeyPatch,
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "geocoding" in request.url.host:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "Springfield",
                            "admin1": "Oregon",
                            "country": "United States",
                            "latitude": 44.0,
                            "longitude": -123.0,
                        },
                        {
                            "name": "Springfield",
                            "admin1": "Illinois",
                            "country": "United States",
                            "latitude": 39.8,
                            "longitude": -89.6,
                        },
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "current": {"temperature_2m": 20},
                "daily": {"time": ["2026-10-09"]},
            },
        )

    mock_httpx(monkeypatch, handler)

    result = await invoke("get_weather", "Springfield, Illinois")

    assert result["location"] == "Springfield, Illinois, United States"
    assert requests[1].url.params["latitude"] == "39.8"


@pytest.mark.asyncio
async def test_weather_returns_current_and_daily_forecast(
    monkeypatch: pytest.MonkeyPatch,
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "geocoding" in request.url.host:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "Mumbai",
                            "admin1": "Maharashtra",
                            "country": "India",
                            "latitude": 19.0,
                            "longitude": 72.8,
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "timezone": "Asia/Kolkata",
                "current": {
                    "time": "2026-10-09T12:00",
                    "temperature_2m": 29.0,
                    "apparent_temperature": 34.0,
                    "relative_humidity_2m": 70,
                    "precipitation": 0.2,
                    "weather_code": 2,
                    "wind_speed_10m": 12.0,
                },
                "daily": {
                    "time": ["2026-10-09"],
                    "temperature_2m_max": [31.0],
                    "temperature_2m_min": [26.0],
                    "precipitation_probability_max": [40],
                    "weather_code": [61],
                },
            },
        )

    mock_httpx(monkeypatch, handler)

    result = await invoke("get_weather", "Mumbai, India")

    assert result["location"] == "Mumbai, Maharashtra, India"
    assert result["current"]["conditions"] == "Partly cloudy"
    assert result["today"]["rain_chance_percent"] == 40
    assert result["current"]["precipitation_mm"] == 0.2
    assert requests[0].url.params["name"] == "Mumbai, India"
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_dictionary_returns_pronunciation_and_meanings(
    monkeypatch: pytest.MonkeyPatch,
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "word": "ephemeral",
                    "phonetics": [{"text": "ih-FEM-er-ul"}],
                    "meanings": [
                        {
                            "partOfSpeech": "adjective",
                            "definitions": [
                                {"definition": "Lasting for a short time."}
                            ],
                        }
                    ],
                }
            ],
        )

    mock_httpx(monkeypatch, handler)

    result = await invoke("define_word", " ephemeral ")

    assert result == {
        "word": "ephemeral",
        "phonetic": "ih-FEM-er-ul",
        "meanings": [
            {
                "part_of_speech": "adjective",
                "definitions": ["Lasting for a short time."],
            }
        ],
    }


@pytest.mark.asyncio
async def test_dictionary_reports_missing_word(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    mock_httpx(monkeypatch, handler)

    with pytest.raises(ToolError, match="couldn't find a definition"):
        await invoke("define_word", "notawordxyz")


@pytest.mark.asyncio
async def test_search_reports_backend_failure_without_raw_details(monkeypatch):
    class FakeDDGS:
        def text(self, *args, **kwargs):
            raise assistant_tools.DDGSException("backend internal details")

    monkeypatch.setattr(assistant_tools, "DDGS", FakeDDGS)
    with pytest.raises(ToolError, match="Web search is unavailable") as error:
        await invoke("search_the_web", "LiveKit")
    assert "internal details" not in str(error.value)


@pytest.mark.asyncio
async def test_search_reports_no_results(monkeypatch):
    class FakeDDGS:
        def text(self, *args, **kwargs):
            return []

    monkeypatch.setattr(assistant_tools, "DDGS", FakeDDGS)
    with pytest.raises(ToolError, match="No search results"):
        await invoke("search_the_web", "unmatched query")


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["get_weather", "define_word"])
async def test_lookup_rejects_empty_input(tool_name):
    with pytest.raises(ToolError, match="Please provide"):
        await invoke(tool_name, "  ")


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["get_weather", "define_word"])
@pytest.mark.parametrize("failure", ["timeout", "http"])
async def test_lookup_reports_service_failure(monkeypatch, tool_name, failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("Timed out", request=request)
        return httpx.Response(503)

    mock_httpx(monkeypatch, handler)
    with pytest.raises(ToolError, match="lookup failed"):
        await invoke(tool_name, "Mumbai" if tool_name == "get_weather" else "ephemeral")


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, None, {"current": [], "daily": {}}])
async def test_weather_reports_malformed_forecast(monkeypatch, payload):
    def handler(request):
        if "geocoding" in request.url.host:
            return httpx.Response(
                200,
                json={"results": [{"name": "Mumbai", "latitude": 19, "longitude": 72}]},
            )
        return httpx.Response(200, json=payload)

    mock_httpx(monkeypatch, handler)
    with pytest.raises(ToolError, match="unexpected response"):
        await invoke("get_weather", "Mumbai")


@pytest.mark.asyncio
async def test_weather_reports_malformed_geocoding(monkeypatch):
    mock_httpx(monkeypatch, lambda request: httpx.Response(200, json=[]))
    with pytest.raises(ToolError, match="unexpected response"):
        await invoke("get_weather", "Mumbai")


@pytest.mark.asyncio
@pytest.mark.parametrize("country", ["India", "IN"])
async def test_weather_does_not_ignore_country_when_only_one_city_matches(
    monkeypatch, country
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "Springfield",
                        "admin1": "Illinois",
                        "country": "United States",
                        "latitude": 39.8,
                        "longitude": -89.6,
                    }
                ]
            },
        )

    mock_httpx(monkeypatch, handler)
    with pytest.raises(ToolError, match="specified country or region"):
        await invoke("get_weather", f"Springfield, Illinois, {country}")
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[None], [{"word": "ephemeral", "meanings": None}]])
async def test_dictionary_reports_malformed_entry(monkeypatch, payload):
    mock_httpx(monkeypatch, lambda request: httpx.Response(200, json=payload))
    with pytest.raises(ToolError, match="unexpected response"):
        await invoke("define_word", "ephemeral")


@pytest.mark.asyncio
async def test_dictionary_reports_empty_meanings(monkeypatch):
    mock_httpx(
        monkeypatch,
        lambda request: httpx.Response(
            200, json=[{"word": "ephemeral", "meanings": []}]
        ),
    )
    with pytest.raises(ToolError, match="no definitions"):
        await invoke("define_word", "ephemeral")


@pytest.mark.asyncio
async def test_dictionary_limits_returned_meanings_and_definitions(monkeypatch):
    entry = {
        "word": "test",
        "meanings": [
            {
                "partOfSpeech": "noun",
                "definitions": [{"definition": str(i)} for i in range(4)],
            }
            for _ in range(5)
        ],
    }
    mock_httpx(monkeypatch, lambda request: httpx.Response(200, json=[entry]))
    result = await invoke("define_word", "test")
    assert len(result["meanings"]) == 3
    assert all(len(meaning["definitions"]) == 2 for meaning in result["meanings"])
