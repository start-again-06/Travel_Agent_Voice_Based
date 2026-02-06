
import asyncio
import httpx
import logging
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("itinerary-mcp")

# Initialize Server
server = Server("itinerary-builder")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="estimate_travel_time",
            description="Estimate driving time between two coordinates",
            inputSchema={
                "type": "object",
                "properties": {
                    "origin_lat": {"type": "number"},
                    "origin_lon": {"type": "number"},
                    "dest_lat": {"type": "number"},
                    "dest_lon": {"type": "number"},
                    "mode": {"type": "string", "enum": ["driving", "walking"], "default": "driving"}
                },
                "required": ["origin_lat", "origin_lon", "dest_lat", "dest_lon"]
            },
        )
    ]

async def get_osrm_route(start: tuple, end: tuple, mode: str = "driving") -> dict | None:
    """Fetch route from OSRM."""
    # OSRM Public API: http://router.project-osrm.org/route/v1/driving/
    # format: /driving/lon1,lat1;lon2,lat2
    
    # Modes mapping (OSRM demo mainly supports driving/car, but footprint for others exists)
    profile = "driving" if mode == "driving" else "foot" # foot might not be on main demo server, usually it's just 'driving'
    if mode == "walking":
        profile = "foot"

    url = f"http://router.project-osrm.org/route/v1/{profile}/{start[1]},{start[0]};{end[1]},{end[0]}"
    params = {"overview": "false"}
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if data["code"] == "Ok":
                # Returns duration in seconds, distance in meters
                return data["routes"][0]
        except Exception as e:
            logger.error(f"OSRM Error: {e}")
    return None

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "estimate_travel_time":
        origin_lat = arguments.get("origin_lat")
        origin_lon = arguments.get("origin_lon")
        dest_lat = arguments.get("dest_lat")
        dest_lon = arguments.get("dest_lon")
        mode = arguments.get("mode", "driving")
        
        route = await get_osrm_route((origin_lat, origin_lon), (dest_lat, dest_lon), mode)
        
        if route:
            duration_min = route["duration"] / 60
            dist_km = route["distance"] / 1000
            return [types.TextContent(type="text", text=f"Duration: {duration_min:.1f} mins, Distance: {dist_km:.2f} km")]
        else:
            return [types.TextContent(type="text", text="Could not calculate route")]

    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="itinerary-builder",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
