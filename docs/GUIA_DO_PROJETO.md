---
doc: GUIA_DO_PROJETO.md
publico: o dono do projeto (humano), não agentes de IA
escopo: a rotina de uso do sistema no dia a dia
nao_contem: comandos (ver OPERACAO.md), arquitetura (ver ARQUITETURA.md)
verificado_em: 2026-09-16
---

# Guia de uso — o que você faz no dia a dia

Suas partidas são coletadas automaticamente → o Stockfish acha os erros → a IA
diagnostica a causa → a estatística revela o gargalo → o RAG cita o livro →
uma sprint de treino é prescrita → o dashboard mostra tudo → **e você treina
dentro do próprio sistema**, que é o que faz o ciclo se fechar.

## Onde cada coisa acontece

| Onde | O quê | Quando |
|---|---|---|
| GitHub Actions | coleta, Stockfish, Agente 1, fila de treino do dia | todo dia, ~06h de Brasília |
| GitHub Actions | medição de eficácia, Agente 2 e Agente 3 | segundas, ~07h de Brasília |
| Seu computador | processar livro novo, backfills, importar catálogo de exercícios | sob demanda |
| `chess-ai-pipeline.vercel.app` | dashboard, treino, sessões e as três ferramentas interativas | quando quiser |

No dia a dia você não roda nada. A automação cuida da coleta, do diagnóstico e
de encher a fila de treino — **o que depende de você é responder a fila.**

## O ciclo recomendado

1. Jogue normalmente no Lichess ou no Chess.com.
2. Deixe a automação rodar.
3. **Todo dia: abra `/treino`.** É a fila curta de repetição espaçada sobre os
   seus próprios erros, mais exercícios de catálogo quando você pede foco numa
   categoria. É o hábito diário; leva poucos minutos.
4. Abra o dashboard (`/`), veja o gargalo atual e a sprint prescrita.
5. **Quando tiver um período longo: abra a sessão de treino focado** e execute
   os blocos — estudo marcado um a um, prática levando para a fila. A sessão se
   conclui sozinha quando o último bloco termina; você não precisa marcar nada
   à mão (era um passo manual antes do D-54, e ninguém nunca o executou).
6. Continue jogando. Cerca de 15 dias depois, a medição de eficácia avalia se
   aquele treino reduziu de fato a frequência daquele erro. São necessários 3
   diagnósticos daquela categoria na janela para a medição sair do "aguardando
   mais dados".

> Nenhuma sessão real foi concluída até 16/09/2026. O caminho técnico está
> validado de ponta a ponta (a pendência P-4 foi resolvida, e o D-54 tirou a
> conclusão das suas mãos), mas o primeiro número de eficácia só nasce de um
> treino que aconteceu de verdade.

## As duas formas de treinar

- **Treino Diário** (`/treino`) — a fila de repetição espaçada. Cada card é uma
  posição em que você errou numa partida sua, ou um exercício de catálogo, e
  volta a aparecer conforme você acerta ou erra (SM-2). A tela mostra no máximo
  20 por vez, e diz quantos ficaram de fora — o teto corta a exibição, nunca o
  agendamento. Card de gestão de tempo vem cronometrado com o tempo que o
  jogador original tinha: estourar o relógio não muda a nota do lance, mas traz
  o card de volta mais cedo, porque decidir dentro do tempo é o que ele treina.
- **Sessão de treino focado** (`/sessao/:id`, a partir da tela `/`) — o formato
  longo. A sprint que o Agente 3 prescreveu, com blocos de estudo que você marca
  conforme lê e um bloco de prática que enfileira exercícios da categoria do
  gargalo. Termina sozinha quando o último bloco fecha.

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

| Livro | Idioma | OCR | Trechos |
|---|---|---|---|
| Meu Sistema — Nimzowitsch | PT | sim | 229 |
| Xadrez Vitorioso: Táticas — Seirawan/Silman | PT | não | 141 |
| How to Reassess Your Chess — Silman (3ª ed.) | EN | sim | 251 |

O terceiro entrou no D-46, junto com a automação do índice conceitual — o OCR
multi-idioma que faltava foi resolvido no D-44.

Pendente: "How to Calculate Chess Tactics".

Para processar um livro novo, veja `OPERACAO.md`, seção 5.
