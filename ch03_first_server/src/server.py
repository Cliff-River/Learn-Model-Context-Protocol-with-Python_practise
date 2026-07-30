from mcp.server.mcpserver import MCPServer

mcp = MCPServer("ch03-first-server")

@mcp.tool()
def multiply(a: int, b: int) -> int:
    """
    Multiply two numbers together.

    Args:
        a (int): The first number.
        b (int): The second number.

    Returns:
        int: The product of a and b.
    """
    return a * b

@mcp.resource("greeting://{name}")
def hello(name: str) -> str:
    """
    Greet the user by name.
    """
    return f"Hello, {name}!"

@mcp.prompt()
def review_code(code: str) -> str:
    """
    Review the code and provide feedback.

    Args:
        code (str): The code to review.

    Returns:
        str: Feedback on the code.
    """
    return f"Code looks good! {code }"

if __name__ == "__main__":
    mcp.run()