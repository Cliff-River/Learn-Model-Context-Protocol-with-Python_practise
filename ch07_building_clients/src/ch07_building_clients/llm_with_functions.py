# - flake8: noqa: B018
# %% Import required modules
import os

from dotenv import find_dotenv, load_dotenv
from openai import OpenAI

load_dotenv(find_dotenv())

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

#%% First API call with reasoning
response = client.chat.completions.create(
    model="deepseek/deepseek-v4-pro-0813",
    messages=[
        {"role": "user", "content": "How many r's are in the word 'strawberry'?"}
    ],
    extra_body={"reasoning": {"enabled": True}},
)

#%% Extract the assistant message with reasoning_details
response = response.choices[0].message
print(response.content)

#%% Preserve the assistant message with reasoning_details
messages = [
    {"role": "user", "content": "How many r's are in the word 'strawberry'?"},
    {
        "role": "assistant",
        "content": response.content,
        "reasoning_details": response.reasoning_details,  # Pass back unmodified
    },
    {"role": "user", "content": "Are you sure? Think carefully."},
]

#%% Second API call - model continues reasoning from where it left off
response2 = client.chat.completions.create(
    model="deepseek/deepseek-v4-pro-0813",
    messages=messages,
    extra_body={"reasoning": {"enabled": True}},
)
print(response2.choices[0].message.content)

# %%