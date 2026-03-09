"""Weather commands: WEATHER, RAIN."""

import logging
import os
from datetime import datetime, timedelta

import httpx

from commands import register_command

log = logging.getLogger(__name__)

DEFAULT_LOCATION = os.getenv("DEFAULT_LOCATION", "London,UK")
DEFAULT_LAT = os.getenv("DEFAULT_LAT", "51.5074")
DEFAULT_LON = os.getenv("DEFAULT_LON", "-0.1278")
MET_OFFICE_API_KEY = os.getenv("MET_OFFICE_API_KEY", "")


# Met Office significant weather codes to text
MET_OFFICE_WEATHER_CODES = {
    0: "Clear", 1: "Clear", 2: "Partly cloudy", 3: "Partly cloudy",
    5: "Mist", 6: "Fog", 7: "Cloudy", 8: "Overcast",
    9: "Light rain showers", 10: "Rain showers", 11: "Drizzle",
    12: "Light rain", 13: "Heavy rain showers", 14: "Heavy rain",
    15: "Heavy rain", 16: "Sleet showers", 17: "Sleet",
    18: "Sleet showers", 19: "Hail showers", 20: "Hail",
    21: "Snow showers", 22: "Snow showers", 23: "Snow",
    24: "Snow", 25: "Heavy snow showers", 26: "Heavy snow",
    27: "Heavy snow", 28: "Thunder showers", 29: "Thunder",
    30: "Thunder",
}


@register_command("WEATHER")
async def handle_weather(args: str = "") -> str:
    """Get weather information.

    WEATHER - current conditions
    WEATHER week - 5 day forecast
    WEATHER [place] - weather for location (Open-Meteo only)
    """
    args = args.strip().lower()

    # Check for week forecast
    if args == "week":
        location = DEFAULT_LOCATION
        show_week = True
    elif args.startswith("week "):
        location = args[5:].strip()
        show_week = True
    elif args.endswith(" week"):
        location = args[:-5].strip()
        show_week = True
    else:
        location = args if args else DEFAULT_LOCATION
        show_week = False

    # Use Met Office for default location, Open-Meteo for other locations
    if MET_OFFICE_API_KEY and location.lower() == DEFAULT_LOCATION.lower():
        if show_week:
            return await _weather_week_met_office()
        else:
            return await _weather_current_met_office()
    else:
        return await _weather_open_meteo(location, show_week)


async def _weather_current_met_office() -> str:
    """Get current weather from Met Office."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/hourly",
                params={
                    "datasource": "BD1",
                    "latitude": DEFAULT_LAT,
                    "longitude": DEFAULT_LON,
                    "excludeParameterMetadata": "true",
                },
                headers={"apikey": MET_OFFICE_API_KEY},
            )

            if resp.status_code != 200:
                log.error(f"Met Office API error: {resp.status_code}")
                return await _weather_open_meteo(DEFAULT_LOCATION, False)

            data = resp.json()
            features = data.get("features", [])
            if not features:
                return await _weather_open_meteo(DEFAULT_LOCATION, False)

            time_series = features[0].get("properties", {}).get("timeSeries", [])
            if not time_series:
                return await _weather_open_meteo(DEFAULT_LOCATION, False)

            # Get current hour's data (first entry)
            current = time_series[0]
            temp = current.get("screenTemperature", "?")
            feels = current.get("feelsLikeTemperature", "?")
            weather_code = current.get("significantWeatherCode", 0)
            rain_prob = current.get("probOfPrecipitation", 0) or 0
            visibility = current.get("visibility", 0)

            weather_text = MET_OFFICE_WEATHER_CODES.get(weather_code, "Unknown")

            # Get sunrise/sunset from daily endpoint
            sun_str = ""
            try:
                daily_resp = await client.get(
                    "https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/daily",
                    params={
                        "datasource": "BD1",
                        "latitude": DEFAULT_LAT,
                        "longitude": DEFAULT_LON,
                        "excludeParameterMetadata": "true",
                    },
                    headers={"apikey": MET_OFFICE_API_KEY},
                )
                if daily_resp.status_code == 200:
                    daily_data = daily_resp.json()
                    daily_series = daily_data.get("features", [{}])[0].get("properties", {}).get("timeSeries", [])
                    if daily_series:
                        today = daily_series[0]
                        # Times are in ISO format with Z suffix
                        sunrise = today.get("sunrise", "")
                        sunset = today.get("sunset", "")
                        if sunrise and sunset:
                            sun_rise = sunrise[11:16]  # Extract HH:MM
                            sun_set = sunset[11:16]
                            sun_str = f" Sun: {sun_rise}-{sun_set}"
            except Exception:
                pass  # Skip sun times if failed

            rain_str = f" Rain: {rain_prob}%." if rain_prob > 0 else ""
            return f"{DEFAULT_LOCATION}: {weather_text}, {int(temp)}C (feels {int(feels)}C).{rain_str}{sun_str}"

    except Exception as e:
        log.error(f"Met Office weather error: {e}")
        return await _weather_open_meteo(DEFAULT_LOCATION, False)


async def _weather_week_met_office() -> str:
    """Get 5-day forecast from Met Office."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/daily",
                params={
                    "datasource": "BD1",
                    "latitude": DEFAULT_LAT,
                    "longitude": DEFAULT_LON,
                    "excludeParameterMetadata": "true",
                },
                headers={"apikey": MET_OFFICE_API_KEY},
            )

            if resp.status_code != 200:
                log.error(f"Met Office API error: {resp.status_code}")
                return await _weather_open_meteo(DEFAULT_LOCATION, True)

            data = resp.json()
            features = data.get("features", [])
            if not features:
                return await _weather_open_meteo(DEFAULT_LOCATION, True)

            time_series = features[0].get("properties", {}).get("timeSeries", [])
            if not time_series:
                return await _weather_open_meteo(DEFAULT_LOCATION, True)

            lines = [f"{DEFAULT_LOCATION} 5-day:"]
            for i, entry in enumerate(time_series[:5]):
                date_str = entry.get("time", "")[:10]
                day = datetime.fromisoformat(date_str).strftime("%a")

                # Day and night temps
                hi = entry.get("dayMaxScreenTemperature") or entry.get("nightMaxScreenTemperature") or "?"
                lo = entry.get("nightMinScreenTemperature") or entry.get("dayMinScreenTemperature") or "?"

                # Rain probability (max of day/night)
                rain_day = entry.get("dayProbabilityOfPrecipitation", 0) or 0
                rain_night = entry.get("nightProbabilityOfPrecipitation", 0) or 0
                rain = max(rain_day, rain_night)

                hi_int = int(hi) if isinstance(hi, (int, float)) else hi
                lo_int = int(lo) if isinstance(lo, (int, float)) else lo
                rain_str = f" {rain}%rain" if rain > 20 else ""
                lines.append(f"{day}: {lo_int}-{hi_int}C{rain_str}")

            return "\n".join(lines)

    except Exception as e:
        log.error(f"Met Office forecast error: {e}")
        return await _weather_open_meteo(DEFAULT_LOCATION, True)


async def _weather_open_meteo(location: str, show_week: bool) -> str:
    """Fallback: Get weather from Open-Meteo API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if show_week:
                meteo = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": DEFAULT_LAT,
                        "longitude": DEFAULT_LON,
                        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                        "timezone": "Europe/London",
                        "forecast_days": 5,
                    }
                )
                if meteo.status_code == 200:
                    data = meteo.json()
                    daily = data.get("daily", {})
                    dates = daily.get("time", [])
                    highs = daily.get("temperature_2m_max", [])
                    lows = daily.get("temperature_2m_min", [])
                    rain = daily.get("precipitation_probability_max", [])

                    lines = [f"{location.title()} 5-day:"]
                    for i in range(min(5, len(dates))):
                        day = datetime.fromisoformat(dates[i]).strftime("%a")
                        hi = int(highs[i]) if i < len(highs) else "?"
                        lo = int(lows[i]) if i < len(lows) else "?"
                        r = rain[i] if i < len(rain) else 0
                        rain_str = f" {r}%rain" if r > 20 else ""
                        lines.append(f"{day}: {lo}-{hi}C{rain_str}")
                    return "\n".join(lines)

            # Current weather
            meteo = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": DEFAULT_LAT,
                    "longitude": DEFAULT_LON,
                    "current": "temperature_2m,apparent_temperature,precipitation_probability,weather_code",
                    "daily": "sunrise,sunset",
                    "timezone": "Europe/London",
                    "forecast_days": 1,
                }
            )
            if meteo.status_code == 200:
                data = meteo.json()
                current = data.get("current", {})
                daily = data.get("daily", {})

                temp = current.get("temperature_2m", "?")
                feels = current.get("apparent_temperature", "?")
                rain_prob = current.get("precipitation_probability", 0) or 0
                weather_code = current.get("weather_code", 0)

                weather_text = {
                    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
                    45: "Foggy", 48: "Icy fog", 51: "Light drizzle", 53: "Drizzle",
                    55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
                    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
                    80: "Light showers", 81: "Showers", 82: "Heavy showers",
                    85: "Light snow showers", 86: "Snow showers",
                    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Severe thunderstorm"
                }.get(weather_code, "Unknown")

                sunrise = daily.get("sunrise", [""])[0]
                sunset = daily.get("sunset", [""])[0]
                sun_rise = sunrise.split("T")[1][:5] if "T" in sunrise else "?"
                sun_set = sunset.split("T")[1][:5] if "T" in sunset else "?"

                rain_str = f" Rain: {rain_prob}%." if rain_prob > 0 else ""
                return f"{location.title()}: {weather_text}, {int(temp)}C (feels {int(feels)}C).{rain_str} Sun: {sun_rise}-{sun_set}"
            else:
                return f"Couldn't get weather for {location}"
    except Exception as e:
        log.error(f"Weather API error: {type(e).__name__}: {e!r}")
        return "Weather lookup failed"


@register_command("RAIN")
async def handle_rain(args: str = "") -> str:
    """Check if rain is expected using Met Office API.

    RAIN = next 3 hours
    RAIN TOMORROW = tomorrow's forecast
    """
    tomorrow = args.strip().upper() in ("TOMORROW", "TOM")

    # Use Met Office API if key is configured
    if MET_OFFICE_API_KEY:
        return await _rain_met_office(tomorrow)
    else:
        return await _rain_open_meteo(tomorrow)


async def _rain_met_office(tomorrow: bool) -> str:
    """Get rain forecast from Met Office DataHub API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Use hourly endpoint for detailed precipitation data
            endpoint = "hourly" if not tomorrow else "daily"
            resp = await client.get(
                f"https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/{endpoint}",
                params={
                    "datasource": "BD1",
                    "latitude": DEFAULT_LAT,
                    "longitude": DEFAULT_LON,
                    "excludeParameterMetadata": "true",
                },
                headers={"apikey": MET_OFFICE_API_KEY},
            )

            if resp.status_code == 401:
                log.error("Met Office API key invalid")
                return "Met Office API key invalid"

            if resp.status_code != 200:
                log.error(f"Met Office API error: {resp.status_code} {resp.text[:200]}")
                return await _rain_open_meteo(tomorrow)  # Fallback

            data = resp.json()
            features = data.get("features", [])
            if not features:
                return "No forecast data available"

            time_series = features[0].get("properties", {}).get("timeSeries", [])
            if not time_series:
                return "No forecast data available"

            if tomorrow:
                # Find tomorrow's entry in daily forecast
                tomorrow_date = (datetime.now().date() + timedelta(days=1)).isoformat()
                for entry in time_series:
                    entry_date = entry.get("time", "")[:10]
                    if entry_date == tomorrow_date:
                        prob_day = entry.get("dayProbabilityOfPrecipitation", 0) or 0
                        prob_night = entry.get("nightProbabilityOfPrecipitation", 0) or 0
                        prob = max(prob_day, prob_night)

                        if prob < 20:
                            return "Tomorrow: No rain expected"
                        elif prob < 50:
                            return f"Tomorrow: Low chance of rain ({prob}%)"
                        elif prob < 70:
                            return f"Tomorrow: Rain possible ({prob}%)"
                        else:
                            return f"Tomorrow: Rain likely ({prob}%)"
                return "Tomorrow forecast not available"

            # Today - next 3 hours from hourly data
            now = datetime.now()
            upcoming = []

            for entry in time_series:
                entry_time = datetime.fromisoformat(entry["time"].replace("Z", "+00:00"))
                # Convert to local time for comparison
                entry_local = entry_time.replace(tzinfo=None)

                # Only future hours
                if entry_local >= now and len(upcoming) < 3:
                    hour_str = entry_local.strftime("%H:%M")
                    prob = entry.get("probOfPrecipitation", 0) or 0
                    rate = entry.get("precipitationRate", 0) or 0  # mm/hr
                    significant = entry.get("significantWeatherCode", 0)
                    upcoming.append((hour_str, prob, rate, significant))

            if not upcoming:
                return "No forecast data available"

            # Check if currently raining based on weather codes
            # Codes 9-12 are rain, 13-15 are sleet/snow, etc.
            rain_codes = {9, 10, 11, 12, 13, 14, 15, 28, 29, 30}  # Various precip codes

            max_prob = max(p[1] for p in upcoming)
            max_rate = max(p[2] for p in upcoming)
            current_code = upcoming[0][3] if upcoming else 0

            # Build response
            if current_code in rain_codes or max_rate > 0:
                # It's raining or will rain
                details = ", ".join(f"{h}: {p}%" for h, p, _, _ in upcoming if p >= 20)
                if max_rate > 0:
                    return f"Rain! {max_rate:.1f}mm/hr. {details}"
                return f"Rain likely! {details}"
            elif max_prob < 10:
                return "No rain expected next 3 hours"
            elif max_prob < 30:
                return f"Low chance of rain ({max_prob}% max)"
            elif max_prob < 60:
                details = ", ".join(f"{h}: {p}%" for h, p, _, _ in upcoming if p >= 20)
                return f"Maybe rain. {details}"
            else:
                details = ", ".join(f"{h}: {p}%" for h, p, _, _ in upcoming)
                return f"Rain likely! {details}"

    except Exception as e:
        log.error(f"Met Office API error: {e}")
        return await _rain_open_meteo(tomorrow)  # Fallback


async def _rain_open_meteo(tomorrow: bool) -> str:
    """Fallback: Get rain forecast from Open-Meteo API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": DEFAULT_LAT,
                    "longitude": DEFAULT_LON,
                    "hourly": "precipitation_probability,precipitation",
                    "daily": "precipitation_probability_max,precipitation_sum",
                    "timezone": "Europe/London",
                    "forecast_days": 2,
                }
            )

            if resp.status_code != 200:
                return "Couldn't check rain forecast"

            data = resp.json()

            if tomorrow:
                daily = data.get("daily", {})
                dates = daily.get("time", [])
                probs = daily.get("precipitation_probability_max", [])
                precip = daily.get("precipitation_sum", [])

                if len(dates) < 2:
                    return "No tomorrow forecast available"

                prob = probs[1] if len(probs) > 1 else 0
                mm = precip[1] if len(precip) > 1 else 0

                if prob < 20:
                    return "Tomorrow: No rain expected"
                elif prob < 50:
                    return f"Tomorrow: Low chance of rain ({prob}%)"
                elif prob < 70:
                    return f"Tomorrow: Rain possible ({prob}%)"
                else:
                    if mm > 0:
                        return f"Tomorrow: Rain likely ({prob}%), ~{mm:.1f}mm"
                    return f"Tomorrow: Rain likely ({prob}%)"

            # Today - next 3 hours
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            probs = hourly.get("precipitation_probability", [])
            precip = hourly.get("precipitation", [])

            now = datetime.now()
            current_hour = now.strftime("%Y-%m-%dT%H:00")

            upcoming = []
            found_current = False
            for i, t in enumerate(times):
                if t >= current_hour:
                    found_current = True
                if found_current and len(upcoming) < 3:
                    hour_str = datetime.fromisoformat(t).strftime("%H:%M")
                    prob = probs[i] if i < len(probs) else 0
                    mm = precip[i] if i < len(precip) else 0
                    upcoming.append((hour_str, prob, mm))

            if not upcoming:
                return "No forecast data available"

            max_prob = max(p[1] for p in upcoming)
            total_mm = sum(p[2] for p in upcoming)

            if max_prob < 10:
                return "No rain expected next 3 hours"
            elif max_prob < 30:
                return f"Low chance of rain ({max_prob}% max)"
            elif max_prob < 60:
                details = ", ".join(f"{h}: {p}%" for h, p, _ in upcoming if p >= 20)
                return f"Maybe rain. {details}"
            else:
                details = ", ".join(f"{h}: {p}%" for h, p, _ in upcoming)
                if total_mm > 0:
                    return f"Rain likely! {details}. ~{total_mm:.1f}mm expected"
                return f"Rain likely! {details}"

    except Exception as e:
        log.error(f"Rain check error: {e}")
        return f"Rain check failed: {str(e)[:50]}"
