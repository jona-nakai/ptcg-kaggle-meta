create table if not exists public.cards (
  card_id integer primary key,
  name text not null,
  raw jsonb,
  image_path text,
  image_url text,
  image_updated_at timestamptz,
  updated_at timestamptz not null default now()
);

alter table public.cards
  add column if not exists image_path text,
  add column if not exists image_url text,
  add column if not exists image_updated_at timestamptz;

create table if not exists public.daily_datasets (
  dataset_date date primary key,
  dataset_slug text not null unique,
  dataset_url text,
  episode_count integer,
  total_bytes bigint,
  top_avg_score numeric,
  median_avg_score numeric,
  processed_at timestamptz not null default now()
);

create table if not exists public.battles (
  episode_id bigint primary key,
  dataset_date date not null references public.daily_datasets(dataset_date),
  battle_uuid uuid,
  player0_name text,
  player1_name text,
  winner_index smallint,
  player0_reward integer,
  player1_reward integer,
  player0_status text,
  player1_status text,
  step_count integer,
  created_at timestamptz not null default now()
);

create table if not exists public.decks (
  deck_hash text primary key,
  card_count integer not null default 60,
  first_seen_date date,
  last_seen_date date,
  updated_at timestamptz not null default now()
);

create table if not exists public.deck_cards (
  deck_hash text not null references public.decks(deck_hash) on delete cascade,
  card_id integer not null references public.cards(card_id),
  count integer not null,
  primary key (deck_hash, card_id)
);

create table if not exists public.battle_players (
  episode_id bigint not null references public.battles(episode_id) on delete cascade,
  player_index smallint not null,
  player_name text not null,
  deck_hash text not null references public.decks(deck_hash),
  reward integer,
  status text,
  won boolean,
  primary key (episode_id, player_index)
);

alter table public.battle_players
  alter column won drop not null,
  alter column won drop default;

create table if not exists public.daily_card_usage (
  dataset_date date not null references public.daily_datasets(dataset_date) on delete cascade,
  card_id integer not null references public.cards(card_id),
  copies_played integer not null,
  decks_played integer not null,
  primary key (dataset_date, card_id)
);

create table if not exists public.meta_summaries (
  key text primary key,
  payload jsonb not null,
  updated_at timestamptz not null default now()
);

create table if not exists public.archetype_runs (
  dataset_date date not null references public.daily_datasets(dataset_date) on delete cascade,
  algorithm_version text not null,
  params jsonb not null default '{}'::jsonb,
  archetype_count integer not null default 0,
  processed_at timestamptz not null default now(),
  primary key (dataset_date, algorithm_version)
);

create table if not exists public.daily_archetypes (
  dataset_date date not null,
  algorithm_version text not null,
  archetype_id text not null,
  slug text not null,
  name text not null,
  deck_count integer not null,
  appearances integer not null,
  wins integer not null default 0,
  losses integer not null default 0,
  win_rate numeric not null default 0,
  meta_share numeric not null default 0,
  signature_cards jsonb not null default '[]'::jsonb,
  primary key (dataset_date, algorithm_version, archetype_id),
  unique (dataset_date, algorithm_version, slug),
  foreign key (dataset_date, algorithm_version)
    references public.archetype_runs(dataset_date, algorithm_version)
    on delete cascade
);

create table if not exists public.deck_archetypes (
  dataset_date date not null,
  algorithm_version text not null,
  deck_hash text not null references public.decks(deck_hash) on delete cascade,
  archetype_id text not null,
  appearances integer not null,
  wins integer not null default 0,
  losses integer not null default 0,
  primary key (dataset_date, algorithm_version, deck_hash),
  foreign key (dataset_date, algorithm_version, archetype_id)
    references public.daily_archetypes(dataset_date, algorithm_version, archetype_id)
    on delete cascade
);

create table if not exists public.archetype_cards (
  dataset_date date not null,
  algorithm_version text not null,
  archetype_id text not null,
  card_id integer not null references public.cards(card_id),
  inclusion_count integer not null,
  inclusion_pct numeric not null,
  avg_copies numeric not null,
  copies_total integer not null,
  primary key (dataset_date, algorithm_version, archetype_id, card_id),
  foreign key (dataset_date, algorithm_version, archetype_id)
    references public.daily_archetypes(dataset_date, algorithm_version, archetype_id)
    on delete cascade
);

create table if not exists public.archetype_matchups (
  dataset_date date not null,
  algorithm_version text not null,
  archetype_id text not null,
  opponent_archetype_id text not null,
  games integer not null,
  wins integer not null,
  losses integer not null,
  win_rate numeric not null default 0,
  primary key (dataset_date, algorithm_version, archetype_id, opponent_archetype_id),
  foreign key (dataset_date, algorithm_version, archetype_id)
    references public.daily_archetypes(dataset_date, algorithm_version, archetype_id)
    on delete cascade
);

create index if not exists battles_dataset_date_idx on public.battles(dataset_date);
create index if not exists battle_players_deck_hash_idx on public.battle_players(deck_hash);
create index if not exists daily_card_usage_date_copies_idx on public.daily_card_usage(dataset_date, copies_played desc);
create index if not exists daily_archetypes_date_meta_share_idx
  on public.daily_archetypes(dataset_date, algorithm_version, meta_share desc);
create index if not exists archetype_cards_archetype_inclusion_idx
  on public.archetype_cards(dataset_date, algorithm_version, archetype_id, inclusion_pct desc);
create index if not exists archetype_matchups_archetype_games_idx
  on public.archetype_matchups(dataset_date, algorithm_version, archetype_id, games desc);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_cards_updated_at on public.cards;
create trigger set_cards_updated_at
before update on public.cards
for each row
execute function public.set_updated_at();

drop trigger if exists set_decks_updated_at on public.decks;
create trigger set_decks_updated_at
before update on public.decks
for each row
execute function public.set_updated_at();

drop trigger if exists set_meta_summaries_updated_at on public.meta_summaries;
create trigger set_meta_summaries_updated_at
before update on public.meta_summaries
for each row
execute function public.set_updated_at();

grant usage on schema public to service_role;

grant select, insert, update, delete on table public.cards to service_role;
grant select, insert, update, delete on table public.daily_datasets to service_role;
grant select, insert, update, delete on table public.battles to service_role;
grant select, insert, update, delete on table public.decks to service_role;
grant select, insert, update, delete on table public.deck_cards to service_role;
grant select, insert, update, delete on table public.battle_players to service_role;
grant select, insert, update, delete on table public.daily_card_usage to service_role;
grant select, insert, update, delete on table public.meta_summaries to service_role;
grant select, insert, update, delete on table public.archetype_runs to service_role;
grant select, insert, update, delete on table public.daily_archetypes to service_role;
grant select, insert, update, delete on table public.deck_archetypes to service_role;
grant select, insert, update, delete on table public.archetype_cards to service_role;
grant select, insert, update, delete on table public.archetype_matchups to service_role;
