"""Teste temporário de conectividade com a API Gemini."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

import google.genai as genai
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import configurar_encoding_utf8  # noqa: E402

configurar_encoding_utf8()


def main() -> None:
    """Testa uma chamada de geração usando o SDK atual do Gemini."""

    try:
        load_dotenv(PROJECT_ROOT / ".env")
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("A variável GEMINI_API_KEY não está definida no .env")

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents="Responda apenas com a palavra OK",
        )
        print(response.text)
    except Exception:
        print("Erro completo ao testar a API Gemini:")
        traceback.print_exc()


if __name__ == "__main__":
    main()
