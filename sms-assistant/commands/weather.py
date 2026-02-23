"""Weather commands: WEATHER, RAIN."""

import logging
import os
from datetime import datetime

import httpx

from commands import register_command

log = logging.getLogger(__name__)

DEFAULT_LOCATION = os.getenv("DEFAULT_LOCATION", "London,UK")
DEFAULT_LAT = os.getenv("DEFAULT_LAT", "51.5074")
DEFAULT_LON = os.getenv("DEFAULT_LON", "-0.1278")


@register_command("WEATHER")
async def handle_weather(args: str = "") -> str:
    """Get weather information using Open-Meteo API.

    WEATHER - current conditions
    WEATHER week - 5 day forecast
    WEATHER [place] - weather for location
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

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if show_week:
                # 5 day forecast
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

                # Convert WMO weather code to text
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
    """Check if rain is expected. RAIN = next 3 hours, RAIN TOMORROW = tomorrow's forecast."""
    tomorrow = args.strip().upper() in ("TOMORROW", "TOM")

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
                # Tomorrow's daily forecast
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

            # Find next 3 hours
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

            # Summarize
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
