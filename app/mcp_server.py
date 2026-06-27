import asyncio
import json
import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio

# Create server instance
server = Server("cafeteria-server")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Exposes cafeteria assistant tools to the MCP client."""
    return [
        types.Tool(
            name="search_menu",
            description="Search the cafeteria menu by query, category, or dietary labels.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword (e.g. 'vegan', 'coffee', 'salad')"}
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="place_order",
            description="Place a cafeteria order. Note: Placing an order will flag it as pending approval.",
            inputSchema={
                "type": "object",
                "properties": {
                    "items": {"type": "string", "description": "Items and quantities to order"}
                },
                "required": ["items"]
            }
        ),
        types.Tool(
            name="track_order",
            description="Track order status by order ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "ID of the order to track"}
                },
                "required": ["order_id"]
            }
        ),
        types.Tool(
            name="check_inventory",
            description="Check item stock levels in the cafeteria inventory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_name": {"type": "string", "description": "Name of the item to check"}
                },
                "required": ["item_name"]
            }
        ),
        types.Tool(
            name="get_sales_analytics",
            description="Retrieve basic sales analytics data (daily totals, popular items).",
            inputSchema={
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "description": "Metric to analyze (e.g., 'popular_items', 'revenue')"}
                },
                "required": ["metric"]
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """Handles execution of cafeteria tools."""
    if not arguments:
        arguments = {}
        
    if name == "search_menu":
        query = arguments.get("query", "").lower()
        menu = [
            {"name": "Garden Salad", "category": "Food", "price": 8.50, "dietary": ["vegetarian", "vegan", "gluten-free"], "ingredients": "lettuce, tomatoes, cucumbers, carrots, vinaigrette"},
            {"name": "Quinoa Bowl", "category": "Food", "price": 10.50, "dietary": ["vegetarian", "vegan", "gluten-free"], "ingredients": "quinoa, black beans, corn, avocado, cilantro"},
            {"name": "Turkey Club Sandwich", "category": "Food", "price": 9.00, "dietary": [], "ingredients": "turkey, bacon, lettuce, tomato, mayo, wheat bread"},
            {"name": "Margherita Pizza Slice", "category": "Food", "price": 4.50, "dietary": ["vegetarian"], "ingredients": "mozzarella, tomato sauce, basil, flour crust"},
            {"name": "Croissant", "category": "Bakery", "price": 3.50, "dietary": ["vegetarian"], "ingredients": "butter, flour, yeast"},
            {"name": "Drip Coffee", "category": "Beverage", "price": 2.50, "dietary": ["vegetarian", "vegan", "gluten-free"], "ingredients": "coffee beans, water"},
            {"name": "Matcha Latte", "category": "Beverage", "price": 4.50, "dietary": ["vegetarian", "gluten-free"], "ingredients": "matcha green tea, milk, sweetener"},
            {"name": "Apple Juice", "category": "Beverage", "price": 3.00, "dietary": ["vegetarian", "vegan", "gluten-free"], "ingredients": "apples"}
        ]
        results = []
        for item in menu:
            if (query in item["name"].lower() or 
                query in item["category"].lower() or 
                query in item["ingredients"].lower() or 
                any(query in label.lower() for label in item["dietary"])):
                results.append(item)
        return [types.TextContent(type="text", text=json.dumps(results, indent=2))]
        
    elif name == "place_order":
        items = arguments.get("items", "")
        # Place order logs success and returns tracking number
        return [types.TextContent(type="text", text=json.dumps({
            "status": "success", 
            "message": f"Order for '{items}' successfully processed by MCP Server. Assigned Order ID: CAF-{hash(items) % 10000}."
        }))]
        
    elif name == "track_order":
        order_id = arguments.get("order_id", "")
        status_map = {
            "1234": "Preparing (expected in 5 mins)",
            "5678": "Ready for pickup",
            "9012": "Completed"
        }
        status = status_map.get(order_id, "Pending / In Queue")
        return [types.TextContent(type="text", text=json.dumps({
            "order_id": order_id,
            "status": status
        }))]
        
    elif name == "check_inventory":
        item_name = arguments.get("item_name", "").lower()
        inventory = {
            "garden salad": 15,
            "quinoa bowl": 8,
            "turkey club sandwich": 0,
            "margherita pizza slice": 20,
            "croissant": 5,
            "drip coffee": 100,
            "matcha latte": 40,
            "apple juice": 25
        }
        stock = None
        matched_item = None
        for k, v in inventory.items():
            if item_name in k:
                stock = v
                matched_item = k
                break
        if stock is not None:
            return [types.TextContent(type="text", text=json.dumps({
                "item": matched_item,
                "in_stock": stock > 0,
                "quantity": stock
            }))]
        else:
            return [types.TextContent(type="text", text=json.dumps({
                "error": f"Item '{item_name}' not found in inventory."
            }))]
            
    elif name == "get_sales_analytics":
        metric = arguments.get("metric", "").lower()
        if "item" in metric or "popular" in metric:
            data = {
                "period": "Today",
                "popular_items": [
                    {"name": "Drip Coffee", "sales_count": 87},
                    {"name": "Garden Salad", "sales_count": 34},
                    {"name": "Quinoa Bowl", "sales_count": 22}
                ]
            }
        else:
            data = {
                "period": "Today",
                "total_revenue": 874.50,
                "orders_count": 143
            }
        return [types.TextContent(type="text", text=json.dumps(data))]
        
    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="cafeteria-server",
                server_version="0.1.0",
                capabilities=types.ServerCapabilities(
                    tools=types.ToolsCapability()
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())
