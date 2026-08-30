from .schemas import AddInputModel

async def add_handler(args):
    try:
        input_model = AddInputModel(**args)
    except Exception as e:
        raise ValueError(f"Invalid input: {e}")
    return float(input_model.a) + float(input_model.b)

tool_add = {
    "name": "add",
    "description": "Add two numbers",
    "args_schema": AddInputModel,
    "handler": add_handler,
}