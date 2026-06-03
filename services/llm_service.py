from openai import AsyncOpenAI
from typing import List, Optional, AsyncGenerator, Dict

class LMStudioClient:
    def __init__(self, model: str = "local-model", base_url: str = "http://localhost:1234/v1"):
        self.model = model
        # LM Studio 的預設本地伺服器位址通常是 http://localhost:1234/v1
        # api_key 可以隨便填寫，因為本地不需要驗證
        self.client = AsyncOpenAI(base_url=base_url, api_key="lm-studio")

    async def call(self,
                  prompt: str,
                  system_prompt: Optional[str] = None,
                  temperature: float = 0.7) -> str:
        messages = self._build_messages(prompt, system_prompt)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error calling LM Studio: {str(e)}"

    async def stream(self,
                    prompt: str,
                    system_prompt: Optional[str] = None,
                    temperature: float = 0.7) -> AsyncGenerator[str, None]:
        messages = self._build_messages(prompt, system_prompt)

        try:
            stream_response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=temperature
            )

            async for chunk in stream_response:
                # OpenAI SDK 的結構中，內容在 delta.content
                content = chunk.choices[0].delta.content
                if content:
                    yield content

        except Exception as e:
            yield f"Error in stream: {str(e)}"

    def _build_messages(self, prompt: str, system_prompt: Optional[str]) -> List[Dict[str, str]]:
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})

        messages.append({'role': 'user', 'content': prompt})
        return messages


# --- 使用範例 ---

if __name__ == "__main__":
    import asyncio

    async def main():
        # 初始化 (model 名稱對應你在 LM Studio 載入的模型名稱)
        llm = LMStudioClient(model="local-model")

        print("--- 一般呼叫 (等待回應) ---")
        response = await llm.call(
            prompt="用一句話解釋什麼是 Python。",
            system_prompt="你是一個幽默的工程師"
        )
        print(f"回應: {response}\n")

        print("--- 串流呼叫 (打字機效果) ---")
        print("回應: ", end="", flush=True)
        async for chunk in llm.stream(prompt="寫一首關於 AI 的五言絕句"):
            print(chunk, end="", flush=True)
        print("\n")

    asyncio.run(main())
