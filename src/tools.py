import asyncio
from urllib.parse import quote

import httpx
from ddgs import DDGS
from ddgs.exceptions import DDGSException
from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError


class AssistantTools:
    @property
    def tools(self) -> list:
        return [self.search_the_web, self.get_weather, self.define_word]

    @function_tool()
    async def search_the_web(
        self,
        context: RunContext,
        query: str,
    ) -> list[dict[str, object]]:
        """Search the web through DDGS and return a few results.

        Use this when the user asks for a web search or needs current information.

        Args:
            query: A concise search query containing the relevant context.
        """
        query = query.strip()
        if not query:
            raise ToolError("Please provide a search query.")

        try:
            results = await asyncio.to_thread(lambda: DDGS().text(query, max_results=5))
        except DDGSException as exc:
            raise ToolError(
                "Web search is unavailable. Please try again later."
            ) from exc
        if not results:
            raise ToolError(
                "No search results were found. Please try a different query."
            )
        return results

    @function_tool()
    async def get_weather(
        self,
        context: RunContext,
        location: str,
    ) -> dict[str, object]:
        """Get current conditions and today's forecast for a city.

        Args:
            location: City name, preferably including its country for clarity.
        """
        location = location.strip()
        if not location:
            raise ToolError("Please provide a city or location.")

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                geocoding = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": location, "count": 5, "language": "en"},
                )
                geocoding.raise_for_status()
                places = geocoding.json().get("results", [])
                if not places:
                    raise ToolError(
                        f"I couldn't find a location matching {location!r}."
                    )

                requested_name = location.split(",", 1)[0].strip().casefold()
                exact_matches = [
                    place
                    for place in places
                    if str(place.get("name", "")).casefold() == requested_name
                ]
                qualifiers = [
                    part.strip().casefold()
                    for part in location.split(",")[1:]
                    if part.strip()
                ]
                country_aliases = {
                    "uk": "united kingdom",
                    "us": "united states",
                    "usa": "united states",
                }
                qualifiers = [
                    country_aliases.get(qualifier, qualifier)
                    for qualifier in qualifiers
                ]
                qualified_matches = [
                    candidate
                    for candidate in (exact_matches or places)
                    if all(
                        qualifier
                        in {
                            str(candidate.get(field, "")).casefold()
                            for field in (
                                "admin1",
                                "admin2",
                                "country",
                                "country_code",
                            )
                        }
                        # The service resolves short admin1 abbreviations in
                        # the first qualifier (e.g. CA for California).
                        or (index == 0 and len(qualifier) == 2)
                        for index, qualifier in enumerate(qualifiers)
                    )
                ]
                if qualifiers and not qualified_matches:
                    raise ToolError(
                        f"I couldn't find {location!r} in the specified country or region."
                    )
                if len(qualified_matches) == 1 or not exact_matches:
                    place = qualified_matches[0]
                else:
                    candidates = [
                        ", ".join(
                            part
                            for part in (
                                candidate.get("name"),
                                candidate.get("admin2"),
                                candidate.get("admin1"),
                                candidate.get("country"),
                            )
                            if part
                        )
                        for candidate in qualified_matches[:3]
                    ]
                    choices = "; ".join(candidates)
                    raise ToolError(
                        f"I found several places called {location!r}: {choices}. "
                        "Please specify the country or region."
                    )
                forecast = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": place["latitude"],
                        "longitude": place["longitude"],
                        "current": (
                            "temperature_2m,apparent_temperature,relative_humidity_2m,"
                            "precipitation,weather_code,wind_speed_10m"
                        ),
                        "daily": (
                            "weather_code,temperature_2m_max,temperature_2m_min,"
                            "precipitation_probability_max"
                        ),
                        "timezone": "auto",
                        "forecast_days": 1,
                        "temperature_unit": "celsius",
                        "wind_speed_unit": "kmh",
                    },
                )
                forecast.raise_for_status()
                data = forecast.json()
            current = data["current"]
            daily = data["daily"]
            if current.get("temperature_2m") is None or not daily.get("time"):
                raise ValueError("Missing weather data")
            country = place.get("country")
            admin_area = place.get("admin1")
            place_name = ", ".join(
                part for part in (place.get("name"), admin_area, country) if part
            )

            return {
                "location": place_name,
                "timezone": data.get("timezone"),
                "current": {
                    "time": current.get("time"),
                    "temperature_c": current.get("temperature_2m"),
                    "feels_like_c": current.get("apparent_temperature"),
                    "humidity_percent": current.get("relative_humidity_2m"),
                    "precipitation_mm": current.get("precipitation"),
                    "conditions": self._weather_description(
                        current.get("weather_code")
                    ),
                    "wind_speed_kmh": current.get("wind_speed_10m"),
                },
                "today": {
                    "date": (daily.get("time") or [None])[0],
                    "high_c": (daily.get("temperature_2m_max") or [None])[0],
                    "low_c": (daily.get("temperature_2m_min") or [None])[0],
                    "rain_chance_percent": (
                        daily.get("precipitation_probability_max") or [None]
                    )[0],
                    "conditions": self._weather_description(
                        (daily.get("weather_code") or [None])[0]
                    ),
                },
            }
        except ToolError:
            raise
        except httpx.HTTPError as exc:
            raise ToolError(f"Weather lookup failed: {exc}") from exc
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
            raise ToolError(
                "The weather service returned an unexpected response."
            ) from exc

    @function_tool()
    async def define_word(
        self,
        context: RunContext,
        word: str,
    ) -> dict[str, object]:
        """Look up an English word's pronunciation and definitions.

        Args:
            word: The English word to define.
        """
        word = word.strip()
        if not word:
            raise ToolError("Please provide a word to define.")

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.get(
                    f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(word, safe='')}"
                )
                if response.status_code == 404:
                    raise ToolError(f"I couldn't find a definition for {word!r}.")
                response.raise_for_status()
                entries = response.json()
            if not isinstance(entries, list) or not entries:
                raise ToolError(f"I couldn't find a definition for {word!r}.")

            entry = entries[0]
            phonetic = entry.get("phonetic")
            if not phonetic:
                phonetic = next(
                    (
                        item.get("text")
                        for item in entry.get("phonetics", [])
                        if item.get("text")
                    ),
                    None,
                )

            meanings = []
            for meaning in entry.get("meanings", [])[:3]:
                definitions = [
                    item["definition"]
                    for item in meaning.get("definitions", [])[:2]
                    if item.get("definition")
                ]
                meanings.append(
                    {
                        "part_of_speech": meaning.get("partOfSpeech"),
                        "definitions": definitions,
                    }
                )

            if not meanings or not any(item["definitions"] for item in meanings):
                raise ToolError("The dictionary returned no definitions for this word.")

            return {
                "word": entry.get("word", word),
                "phonetic": phonetic,
                "meanings": meanings,
            }
        except ToolError:
            raise
        except httpx.HTTPError as exc:
            raise ToolError(f"Dictionary lookup failed: {exc}") from exc
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
            raise ToolError("The dictionary returned an unexpected response.") from exc

    @staticmethod
    def _weather_description(code: object) -> str | None:
        descriptions = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            56: "Light freezing drizzle",
            57: "Dense freezing drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            66: "Light freezing rain",
            67: "Heavy freezing rain",
            71: "Slight snow",
            73: "Moderate snow",
            75: "Heavy snow",
            77: "Snow grains",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            85: "Slight snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with slight hail",
            99: "Thunderstorm with heavy hail",
        }
        return descriptions.get(code) if isinstance(code, int) else None
