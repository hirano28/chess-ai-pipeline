---
doc: GUIA_DO_PROJETO.md
publico: o dono do projeto (humano), não agentes de IA
escopo: a rotina de uso do sistema no dia a dia
nao_contem: comandos (ver OPERACAO.md), arquitetura (ver ARQUITETURA.md)
verificado_em: 2026-09-11
---

# Guia de uso — o que você faz no dia a dia

Suas partidas são coletadas automaticamente → o Stockfish acha os erros → a IA
diagnostica a causa → a estatística revela o gargalo → o RAG cita o livro →
uma sprint de treino é prescrita → o dashboard mostra tudo.

## Onde cada coisa acontece

| Onde | O quê | Quando |
|---|---|---|
| GitHub Actions | coleta, Stockfish, Agente 1 | todo dia, ~06h de Brasília |
| GitHub Actions | Agente 2 e Agente 3 | segundas, ~07h de Brasília |
| Seu computador | processar livro novo, backfills, os scripts ainda não automatizados | sob demanda |
| `chess-ai-pipeline.vercel.app` | dashboard e as três ferramentas interativas | quando quiser |

No dia a dia você não roda nada. A automação cuida da coleta e do diagnóstico.

## O ciclo recomendado

1. Jogue normalmente no Lichess ou no Chess.com.
2. Deixe a automação rodar.
3. Abra o dashboard, veja o gargalo atual e a sprint prescrita.
4. Estude e pratique o que a sprint sugere.
5. **Marque a sessão como concluída.** Sem isso o `medir_eficacia.py` não tem o
   que medir e o sistema nunca aprende se o treino funcionou.
6. Continue jogando. Cerca de 15 dias depois, a medição de eficácia avalia se
   aquele treino reduziu de fato a frequência daquele erro.

> Os passos 5 e 6 nunca aconteceram até hoje — ver pendência P-4 em `ESTADO.md`.

## As três ferramentas interativas

- **Laboratório de Raciocínio** (`/laboratorio`) — cole uma posição (FEN ou PGN,
  ou reconheça de uma foto), o lance que você jogou e o que estava pensando.
  Aceita notação em português. Devolve qualidade do lance, qualidade do
  raciocínio e aderência aos 8 passos da rotina.
- **Explicador de Posição** (`/explicador`) — o que está acontecendo nesta
  posição, com avaliação objetiva e explicação didática.
- **Analisador de Partida** (`/analisador`) — cole o PGN e receba a narrativa da
  partida inteira com o momento-chave estratégico.

A rubrica dos 8 passos usada pelo Laboratório está em `GUIA_GUESS_THE_MOVE.md`.

## Livros no RAG

| Livro | Idioma | OCR |
|---|---|---|
| Meu Sistema — Nimzowitsch | PT | sim |
| Xadrez Vitorioso: Táticas — Seirawan/Silman | PT | não |

Pendente: "How to Calculate Chess Tactics" (inglês, precisa OCR configurado para
inglês no Tesseract).

Para processar um livro novo, veja `OPERACAO.md`, seção 5.
