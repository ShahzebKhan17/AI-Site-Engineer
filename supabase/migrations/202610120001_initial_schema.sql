create extension if not exists vector;

create type public.drawing_status as enum ('uploaded', 'processing', 'ready', 'failed');
create type public.calculation_status as enum ('pending', 'completed', 'failed', 'needs_review');

create table public.projects (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.drawings (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  file_name text not null,
  storage_path text not null unique,
  mime_type text not null,
  file_size_bytes bigint not null check (file_size_bytes > 0),
  revision text,
  status public.drawing_status not null default 'uploaded',
  page_count integer,
  processing_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.document_chunks (
  id uuid primary key default gen_random_uuid(),
  drawing_id uuid not null references public.drawings(id) on delete cascade,
  content text not null,
  page_number integer not null check (page_number > 0),
  chunk_index integer not null check (chunk_index >= 0),
  entity_type text,
  entity_code text,
  metadata jsonb not null default '{}'::jsonb,
  embedding vector(1536),
  created_at timestamptz not null default now(),
  unique (drawing_id, chunk_index)
);

create index document_chunks_embedding_idx on public.document_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);
create index document_chunks_entity_code_idx on public.document_chunks (entity_code);
create index drawings_project_idx on public.drawings (project_id);

create table public.calculation_runs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  drawing_id uuid references public.drawings(id) on delete set null,
  requested_by uuid not null references auth.users(id) on delete cascade,
  question text not null,
  extracted_inputs jsonb not null default '{}'::jsonb,
  result jsonb,
  calculation_engine_version text,
  status public.calculation_status not null default 'pending',
  review_notes text,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

alter table public.projects enable row level security;
alter table public.drawings enable row level security;
alter table public.document_chunks enable row level security;
alter table public.calculation_runs enable row level security;

create policy "Users manage their own projects" on public.projects for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "Users access drawings in their projects" on public.drawings for all using (exists (select 1 from public.projects where projects.id = drawings.project_id and projects.owner_id = auth.uid())) with check (exists (select 1 from public.projects where projects.id = drawings.project_id and projects.owner_id = auth.uid()));
create policy "Users access chunks in their projects" on public.document_chunks for select using (exists (select 1 from public.drawings join public.projects on projects.id = drawings.project_id where drawings.id = document_chunks.drawing_id and projects.owner_id = auth.uid()));
create policy "Users access their project calculations" on public.calculation_runs for all using (requested_by = auth.uid()) with check (requested_by = auth.uid());
