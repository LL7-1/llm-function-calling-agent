"""大模型客户端：一套代码兼容 DeepSeek / 智谱 / OpenAI。

这三家的 API 都是 OpenAI 兼容协议，差别只在 base_url 和 model 名，
所以不需要为每家写一套适配层，改环境变量即可切换。
"""

from __future__ import annotations

import os

from openai import OpenAI

# 三家的默认配置，切换只改 PROVIDER 一个变量
PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "key_env": "DEEPSEEK_API_KEY",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "key_env": "ZHIPU_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "key_env": "OPENAI_API_KEY",
    },
}


class LLM:
    def __init__(self, provider: str | None = None, model: str | None = None):
        name = (provider or os.getenv("PROVIDER") or "deepseek").lower()
        if name not in PROVIDERS:
            raise SystemExit(f"未知的 PROVIDER：{name}，可选：{', '.join(PROVIDERS)}")

        conf = PROVIDERS[name]
        key = os.getenv(conf["key_env"])
        if not key:
            raise SystemExit(
                f"缺少 API Key：请复制 .env.example 为 .env，并把 {conf['key_env']} 填上。\n"
                f"（不想配 Key 也能验证代码是否跑通：python main.py --selftest）"
            )

        self.provider = name
        self.model = model or os.getenv("MODEL") or conf["model"]
        self.client = OpenAI(api_key=key, base_url=conf["base_url"])

    def chat(self, messages: list[dict], tools: list[dict] | None = None):
        """发一次请求，返回原始 message 对象（可能带 tool_calls）。"""
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools or None,
            temperature=0.2,  # 查数据要的是准，不是花
        )
        return resp.choices[0].message
