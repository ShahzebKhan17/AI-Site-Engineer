alter table public.document_chunks
  add column search_vector tsvector generated always as (to_tsvector('english', coalesce(content, ''))) stored;

create index document_chunks_search_vector_idx on public.document_chunks using gin (search_vector);

create or replace function public.hybrid_search_document_chunks(
  query_text text,
  query_embedding vector(1536),
  match_count integer default 8,
  filter_project_id uuid default null,
  filter_entity_code text default null
)
returns table (
  chunk_id uuid,
  drawing_id uuid,
  content text,
  page_number integer,
  entity_code text,
  metadata jsonb,
  keyword_score real,
  semantic_score real,
  combined_score real
)
language sql
stable
as $$
  with candidates as (
    select
      chunks.id as chunk_id,
      chunks.drawing_id,
      chunks.content,
      chunks.page_number,
      chunks.entity_code,
      chunks.metadata,
      coalesce(ts_rank_cd(chunks.search_vector, websearch_to_tsquery('english', query_text)), 0)::real as keyword_score,
      (1 - (chunks.embedding <=> query_embedding))::real as semantic_score,
      case when lower(chunks.entity_code) = lower(filter_entity_code) then 0.25 else 0 end::real as identifier_boost
    from public.document_chunks as chunks
    join public.drawings as drawings on drawings.id = chunks.drawing_id
    where chunks.embedding is not null
      and (filter_project_id is null or drawings.project_id = filter_project_id)
      and (filter_entity_code is null or chunks.entity_code = filter_entity_code or chunks.content ilike '%' || filter_entity_code || '%')
  )
  select
    chunk_id,
    drawing_id,
    content,
    page_number,
    entity_code,
    metadata,
    keyword_score,
    semantic_score,
    (0.45 * keyword_score + 0.55 * semantic_score + identifier_boost)::real as combined_score
  from candidates
  order by combined_score desc
  limit greatest(match_count, 1);
$$;

comment on function public.hybrid_search_document_chunks is
  'Hybrid retrieval over the caller-visible document chunks. RLS applies to the underlying tables.';
