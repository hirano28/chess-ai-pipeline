create or replace function match_livros_chunks(
    query_embedding vector(768),
    filtro_livros text[] default null,
    filtro_capitulos text[] default null,
    match_count int default 5
)
returns table (
    id bigint,
    livro text,
    capitulo text,
    pagina_aprox int,
    conteudo text,
    similaridade float
)
language sql
stable
as $$
    select
        lc.id,
        lc.livro,
        lc.capitulo,
        lc.pagina_aprox,
        lc.conteudo,
        1 - (lc.embedding <=> query_embedding) as similaridade
    from livros_chunks lc
    where (
        filtro_livros is null
        or array_length(filtro_livros, 1) is null
        or lc.livro = any(filtro_livros)
    )
    and (
        filtro_capitulos is null
        or array_length(filtro_capitulos, 1) is null
        or lc.capitulo = any(filtro_capitulos)
    )
    order by lc.embedding <=> query_embedding
    limit match_count;
$$;
