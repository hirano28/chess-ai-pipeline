---
doc: CLAUDE.md
papel: ponteiro do Claude Code para o conhecimento canônico
verificado_em: 2026-09-11
---

# Claude Code — Chess AI Pipeline

**Leia [`AGENTS.md`](AGENTS.md) primeiro.** Ele é o ponto de entrada canônico deste
repositório, compartilhado com os outros agentes de IA que trabalham aqui, e
contém o roteador de documentos, as regras invioláveis (R1–R10) e o protocolo de
atualização do conhecimento.

Este arquivo existe só para o que é específico do Claude Code. Nada de
arquitetura, schema, comando ou estado factual deve ser duplicado aqui — se você
sentir vontade de acrescentar esse tipo de conteúdo, o lugar certo está no
roteador da seção 3 de `AGENTS.md`.

---

## Ambiente desta máquina

- Windows 11 + PowerShell. A shell Bash também está disponível; cada uma tem a
  própria sintaxe.
- Interpretador do projeto: `.venv/Scripts/python.exe` (o `python` do PATH é uma
  instalação separada e **não** tem as dependências do projeto instaladas).
- `unittest discover` não funciona a partir de `backend/`: os pacotes são
  namespace packages, sem `__init__.py`. Use a lista explícita de módulos de
  `docs/OPERACAO.md`.

## Verificação de trabalho

Este projeto tem backend e frontend reais rodando localmente; prefira verificar
de verdade em vez de só rodar teste unitário:

- Backend: `uvicorn backend.api.api_server:app --port 8000` e chame o endpoint.
- Frontend: `cd frontend && npm start` e exercite a tela no navegador.
- A chave de API local está no `.env`, em `API_SECRET_KEY`.

## Acesso ao banco

O projeto Supabase em uso é `pmzmershonrqzwbmhaco` ("Xadrez - treinamento").
Existe um segundo projeto na mesma organização que **não** é este — confira o
`SUPABASE_URL` do `.env` antes de rodar query em produção.
