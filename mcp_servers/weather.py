import asyncio
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry
import logging
import requests
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather-mcp")

# Setup Open-Meteo Client with cache and timeout
# OpenMeteo client wrapper relies on the `requests` session.
# We create a session that enforces timeouts.

class TimeoutHTTPAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.pop("timeout", 5.0)
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        return super().send(request, **kwargs)

cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
retry_session.mount("https://", TimeoutHTTPAdapter(timeout=5.0))
retry_session.mount("http://", TimeoutHTTPAdapter(timeout=5.0))

openmeteo = openmeteo_requests.Client(session = retry_session)

# Initialize Server
server = Server("weather-service")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_forecast",
            description="Get weather forecast for a location",
            inputSchema={
                "type": "object",
                "properties": {
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                    "days": {"type": "integer", "default": 3}
                },
                "required": ["lat", "lon"]
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "get_forecast":
        lat = arguments.get("lat")
        lon = arguments.get("lon")
        days = arguments.get("days", 3)
        
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
            "forecast_days": days
        }
        
        try:
            # Run blocking call in thread to avoid blocking loop
            responses = await asyncio.to_thread(openmeteo.weather_api, url, params=params)
            response = responses[0]
            
            daily = response.Daily()
            daily_weather_code = daily.Variables(0).ValuesAsNumpy()
            daily_max_temp = daily.Variables(1).ValuesAsNumpy()
            daily_min_temp = daily.Variables(2).ValuesAsNumpy()
            daily_precip = daily.Variables(3).ValuesAsNumpy()
            
            dates = pd.date_range(
                start = pd.to_datetime(daily.Time(), unit = "s", utc = True),
                end = pd.to_datetime(daily.TimeEnd(), unit = "s", utc = True),
                freq = pd.Timedelta(seconds = daily.Interval()),
                inclusive = "left"
            )
            
            wmo_codes = {
                0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                45: "Fog", 48: "Depositing rime fog",
                51: "Drizzle: Light", 53: "Drizzle: Moderate", 55: "Drizzle: Dense",
                61: "Rain: Slight", 63: "Rain: Moderate", 65: "Rain: Heavy",
            }
            
            report = []
            for i, date in enumerate(dates):
                if i >= days: break
                code = int(daily_weather_code[i])
                desc = wmo_codes.get(code, "Unknown")
                report.append(f"{date.date()}: {desc}, High: {daily_max_temp[i]:.1f}C, Low: {daily_min_temp[i]:.1f}C, Rain: {daily_precip[i]:.1f}mm")
            
            return [types.TextContent(type="text", text="\n".join(report))]
            
        except requests.exceptions.Timeout:
             return [types.TextContent(type="text", text="Weather API timed out.")]
        except Exception as e:
            logger.error(f"Weather API Error: {e}")
            return [types.TextContent(type="text", text=f"Error fetching weather: {e}")]

    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="weather-service",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
