"""
Shared prompt constants with zero heavy imports -- deliberately its own
module so serving code (app/llm/serve.py) can use SYSTEM_PROMPT without
transitively pulling in the training stack (torch/transformers/peft/trl),
which app/finetune/train.py imports at module level. A real CI failure
caught this the first time: app/llm/serve.py importing SYSTEM_PROMPT
directly from app.finetune.train broke the serving/training dependency
boundary requirements-serving.txt is supposed to enforce.
"""

SYSTEM_PROMPT = (
    "You are a League of Legends coach. Give concise, rank-aware matchup "
    "advice for the game phase asked about. If you do not have reliable "
    "data for this matchup at this rank, say so plainly instead of "
    "inventing specifics."
)
