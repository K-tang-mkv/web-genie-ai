import bittensor as bt

from openai import AsyncOpenAI, OpenAI

from webgenie.constants import (
    LLM_MODEL_ID, 
    LLM_API_KEY, 
    LLM_MODEL_URL
)

import re


# if not LLM_API_KEY or not LLM_MODEL_URL or not LLM_MODEL_ID:
#     raise Exception("LLM_API_KEY, LLM_MODEL_URL, and LLM_MODEL_ID must be set")
LLM_API_KEY = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJHcm91cE5hbWUiOiLmooHmlrDlhbUiLCJVc2VyTmFtZSI6IuaigeaWsOWFtSIsIkFjY291bnQiOiIiLCJTdWJqZWN0SUQiOiIxNzY4NTM2ODA1NjIxMTIxNDExIiwiUGhvbmUiOiIxOTg2MDIwOTg3OCIsIkdyb3VwSUQiOiIxNzY4NTM2ODA1NTc0OTg0MDY3IiwiUGFnZU5hbWUiOiIiLCJNYWlsIjoiIiwiQ3JlYXRlVGltZSI6IjIwMjUtMDEtMjIgMjA6MDk6MTIiLCJUb2tlblR5cGUiOjEsImlzcyI6Im1pbmltYXgifQ.I8PCpExQP4Pyq3L43uLTHPaPOrjw9qlcpM2V1ZIEZf-6kZ3pYPuFLkMO3ikx7JVR2cpKl-nI4Z-1RH1MwOefrsQ7Fhkwtv6MMmXXO2j7HzOuKZaj5l_EJ431m2-jPx9l3cJ4TMAsP4aDhKvflcuRFbenXCZ8F2fuXr70WvSuoHCBWh-Hsqo_Dg04s9AkzB4WvaE3STwbX1N0CyWylezAzOrE0_6Yj-QlLzoqm0HeZbq_OhY-XnfbNA_CFvQTdb4_JG3eYBGACSClh-66N7qMZxOpDgEQfmF3cEzi9P9HuJlx0tIrkiiQfT-GmMAqHgaWIhTF6_clFNMNvwZNwqBseA"
LLM_MODEL_URL = "https://api.minimax.chat/v1"
LLM_MODEL_ID = "MiniMax-Text-01"
client = OpenAI(
    api_key=LLM_API_KEY,
    base_url=LLM_MODEL_URL,
)

async def openai_call(messages, response_format, deterministic=False, retries=3):
    for _ in range(retries):
        try:
            if deterministic:
                completion = await client.beta.chat.completions.parse(
                    model=LLM_MODEL_ID,
                    messages= messages,
                    response_format=response_format,
                    temperature=0,
                )
            else:
                # completion = await client.beta.chat.completions.parse(
                #     model=LLM_MODEL_ID,
                #     messages= messages,
                #     response_format=response_format,
                #     temperature=0.7,
                # )
                completion = client.chat.completions.create(
                    model=LLM_MODEL_ID,
                    messages=messages,
                    temperature=0.7,
                )
                # 假设 completion 是返回的对象
                content = completion.choices[0].message.content

                # 使用正则提取 ```html 到 ``` 之间的内容
                html_match = re.search(r'```html\n(.*?)```', content, re.DOTALL)

                if html_match:
                    html_content = html_match.group(1)
                    bt.logging.info(f"completion: {html_content}")
                else:
                    bt.logging.info(f"HTML content not found.")
                
            return html_content
        except Exception as e:
            bt.logging.error(f"Error calling OpenAI: {e}")
            continue
    raise Exception("Failed to call OpenAI")