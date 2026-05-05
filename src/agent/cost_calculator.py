MODEL_COSTS = {
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 0.8, "output": 4.0},
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "qwen-plus": {"input": 0.4, "output": 1.2},
}


def normalize_model_name(model: str) -> str:
    model = model.lower().strip()
    if "openai:" in model:
        model = model.replace("openai:", "")
    if ":" in model:
        model = model.split(":")[-1]
    return model


def estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    normalized = normalize_model_name(model)
    costs = MODEL_COSTS.get(normalized)
    if not costs:
        return 0.0
    return (prompt_tokens * costs["input"] + completion_tokens * costs["output"]) / 1_000_000


def get_model_info(model: str) -> dict:
    normalized = normalize_model_name(model)
    costs = MODEL_COSTS.get(normalized)
    if costs:
        return {**costs, "unknown": False}
    return {"input": 0, "output": 0, "unknown": True}


def calculate_price(model: str, tokens: int, is_input: bool = True) -> float:
    normalized = normalize_model_name(model)
    costs = MODEL_COSTS.get(normalized)
    if not costs:
        return 0.0
    price = costs["input"] if is_input else costs["output"]
    return (tokens * price) / 1_000_000


__all__ = [
    "MODEL_COSTS",
    "estimate_cost",
    "get_model_info",
    "calculate_price",
]