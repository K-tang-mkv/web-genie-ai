import bittensor as bt

from openai import AsyncOpenAI, OpenAI

from webgenie.constants import (
    LLM_MODEL_ID, 
    LLM_API_KEY, 
    LLM_MODEL_URL
)

from webgenie.helpers.htmls import (
    preprocess_html, 
)

import re
import time


LLM_API_KEY = ""
LLM_MODEL_URL = "https://openrouter.ai/api/v1"
# LLM_MODEL_ID = "minimax/minimax-01"
LLM_MODEL_ID = "google/gemini-2.0-flash-001"
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
                
                start_time = time.time()  # 记录开始时间

                completion = client.chat.completions.create(
                    model=LLM_MODEL_ID,
                    messages=messages,
                    temperature=0.7,
                    stream=True,
                )

                content = ""
                for chunk in completion:
                    if chunk.choices[0].delta.content:
                        chunk_content = chunk.choices[0].delta.content
                        content += chunk_content

                        # 检查是否遇到结束标记
                        if "</html>\n```" in content:
                            break


                end_time = time.time()  # 记录结束时间

                elapsed_time = end_time - start_time  # 计算耗时
                bt.logging.info(f"Call llm took {elapsed_time:.2f} seconds.")
                # 假设 completion 是返回的对象
                # content = completion.choices[0].message.content

                # 使用正则提取 ```html 到 ``` 之间的内容
                bt.logging.info(f"html content: {content}")
                html_match = re.search(r'```html\n(.*?)```', content, re.DOTALL)

                if html_match:
                    html_content = html_match.group(1)
                    # bt.logging.info(f"completion: {html_content}")
                else:
                    bt.logging.info(f"HTML content not found.")
                # html_content = "<html> </html>"
            
            # html_content = preprocess_html(html_content)
            bt.logging.info(f"no preprocess!!!")
            return html_content
        except Exception as e:
            bt.logging.warning(f"Error calling OpenAI: {e}")
            continue
    raise Exception("Failed to call OpenAI")
