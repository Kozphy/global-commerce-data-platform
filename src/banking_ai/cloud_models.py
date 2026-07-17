from __future__ import annotations

import os
from typing import Protocol


class TextModel(Protocol):
    provider_name: str

    def generate(self, prompt: str) -> str: ...


class DeterministicBankingModel:
    provider_name = "deterministic-local"

    def generate(self, prompt: str) -> str:
        if "human review required" in prompt.lower():
            return "For your security, this request has been routed to a bank specialist for review."
        return (
            "Based on the approved banking policy and the available account activity summary, "
            "please follow the in-app verification steps. No transaction has been executed by this assistant."
        )


class BedrockConverseModel:
    provider_name = "aws-bedrock-converse"

    def __init__(self, model_id: str | None = None, region: str | None = None) -> None:
        import boto3

        self.model_id = model_id or os.environ["BEDROCK_MODEL_ID"]
        self.client = boto3.client("bedrock-runtime", region_name=region or os.getenv("AWS_REGION"))

    def generate(self, prompt: str) -> str:
        response = self.client.converse(
            modelId=self.model_id,
            system=[{"text": "You are a cautious digital-banking assistant. Never execute transactions."}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 500, "temperature": 0.1},
        )
        return response["output"]["message"]["content"][0]["text"]


class VertexGenAIModel:
    provider_name = "gcp-vertex-google-genai"

    def __init__(self, model: str | None = None) -> None:
        from google import genai
        from google.genai.types import HttpOptions

        self.model = model or os.getenv("VERTEX_MODEL", "gemini-2.5-flash")
        self.client = genai.Client(http_options=HttpOptions(api_version="v1"))

    def generate(self, prompt: str) -> str:
        response = self.client.models.generate_content(model=self.model, contents=prompt)
        return response.text or "No response generated."


def build_text_model(provider: str | None = None) -> TextModel:
    provider = (provider or os.getenv("DBAI_MODEL_PROVIDER", "local")).lower()
    if provider == "bedrock":
        return BedrockConverseModel()
    if provider == "vertex":
        return VertexGenAIModel()
    return DeterministicBankingModel()
