
import os
import asyncio
import httpx
import logging
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("poi-search-mcp")

# Initialize Server
server = Server("poi-search")

# Load API Keys
FOURSQUARE_API_KEY = os.getenv("FOURSQUARE_SERVICE_API_KEY") 

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_places",
            description="Search for points of interest (POIs) in a city using OpenStreetMap and Foursquare. Returns top results.",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "Name of the city (e.g., 'Jaipur')"},
                    "category": {"type": "string", "description": "Category of place (e.g., 'museum', 'restaurant', 'park')"},
                    "limit": {"type": "integer", "description": "Max number of results (default 5)"}
                },
                "required": ["city", "category"]
            },
        ),
        types.Tool(
            name="get_place_details",
            description="Get detailed info about a specific place from Foursquare",
            inputSchema={
                "type": "object",
                "properties": {
                    "place_name": {"type": "string", "description": "Name of the place"},
                    "city": {"type": "string", "description": "City where the place is located"}
                },
                "required": ["place_name", "city"]
            },
        )
    ]

async def geocode_city(city_name: str) -> tuple[float, float] | None:
    """Get lat/lon for a city using Nominatim with timeout."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city_name, "format": "json", "limit": 1}
    headers = {"User-Agent": "VoiceAgentTravelPlanner/1.0"}
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception as e:
            logger.error(f"Geocoding error: {e}")
    return None

async def search_osm(lat: float, lon: float, category: str, radius: int = 3000) -> list[dict]:
    """Search OSM for POIs using raw HTTP with timeout."""
    # Reduced default radius to 3000m for speed
    
    overpass_url = "http://overpass-api.de/api/interpreter"
    
    # Map common categories to OSM tags
    osm_tags = {
        "museum": 'node["tourism"="museum"]',
        "restaurant": 'node["amenity"="restaurant"]',
        "park": 'node["leisure"="park"]',
        "historical": 'node["historic"]',
        "hotel": 'node["tourism"="hotel"]',
        "cafe": 'node["amenity"="cafe"]',
        "shopping": 'node["shop"]'
    }
    
    tag_query = osm_tags.get(category.lower(), f'node["amenity"="{category}"]')
    
    query = f"""
    [out:json][timeout:10];
    (
      {tag_query}(around:{radius},{lat},{lon});
    );
    out body 10; 
    >;
    out skel qt;
    """
    # Note: 'out body 10' limits to 10 nodes to prevent massive payloads
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(overpass_url, data={"data": query})
            if resp.status_code != 200:
                logger.error(f"OSM returned status {resp.status_code}")
                return []
                
            data = resp.json()
            places = []
            for element in data.get("elements", []):
                if "tags" in element and "name" in element["tags"]:
                    places.append({
                        "name": element["tags"]["name"],
                        "lat": element.get("lat"),
                        "lon": element.get("lon"),
                        "source": "OpenStreetMap"
                    })
            return places
        except httpx.TimeoutException:
            logger.error("OSM Query Timed Out")
            return []
        except Exception as e:
            logger.error(f"OSM Error: {e}")
            return []

async def search_foursquare(query: str, lat: float, lon: float, limit: int = 5) -> list[dict]:
    """Search Foursquare Places API."""
    if not FOURSQUARE_API_KEY:
        return []
        
    url = "https://api.foursquare.com/v3/places/search"
    params = {
        "query": query,
        "ll": f"{lat},{lon}",
        "limit": limit,
        "fields": "fsq_id,name,rating,location,photos"
    }
    headers = {
        "Accept": "application/json",
        "Authorization": FOURSQUARE_API_KEY
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 401:
                logger.error("Foursquare Unauthorized")
                return []
            resp.raise_for_status()
            data = resp.json()
            results = []
            for place in data.get("results", []):
                results.append({
                    "name": place.get("name"),
                    "rating": place.get("rating"),
                    "address": place.get("location", {}).get("formatted_address"),
                    "source": "Foursquare"
                })
            return results
        except Exception as e:
            logger.error(f"Foursquare Error: {e}")
            return []

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "search_places":
        city = arguments.get("city")
        category = arguments.get("category")
        limit = arguments.get("limit", 5)
        
        # 1. Geocode
        coords = await geocode_city(city)
        if not coords:
            return [types.TextContent(type="text", text=f"Could not find location for {city}")]
        
        lat, lon = coords
        
        # 2. Parallel Search with Timeout priority
        # Try Foursquare first (better quality), then OSM
        results = await search_foursquare(category, lat, lon, limit)
        
        if not results:
             logger.info("Foursquare returned no results, trying OSM...")
             # Fallback to OSM
             results = await search_osm(lat, lon, category)
        
        if not results:
            return [types.TextContent(type="text", text=f"No places found for {category} in {city}.")]

        return [types.TextContent(type="text", text=str(results[:limit]))]

    elif name == "get_place_details":
        return [types.TextContent(type="text", text="Not implemented fully yet, use search_places")]
    
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="poi-search",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
