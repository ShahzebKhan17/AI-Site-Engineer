# Supabase setup

Create a Supabase project, then apply `migrations/202610120001_initial_schema.sql` in the SQL editor or through the Supabase CLI.

The initial migration deliberately creates only application data tables. Create a private `drawings` storage bucket separately before enabling real uploads. Every query is scoped through Row Level Security to the authenticated project owner.

Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` in `.env.local` before connecting the frontend.
