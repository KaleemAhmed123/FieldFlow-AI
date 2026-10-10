-- FieldFlow e-com inventory schema (Decision A: inventory is a SEPARATE source from Salesforce).
-- Run once in the Supabase SQL editor. Tables are ecom_-prefixed so they never collide with the
-- orchestrator's tables in the same project. The seed (scripts/seed.mjs) fills them from the
-- orchestrator's catalog.json so inventory, the Salesforce asset and RAG stay one consistent world.

create table if not exists ecom_products (
  part_no          text primary key,
  name             text    not null,
  kind             text    not null,          -- board | consumable | ...
  model_id         text    not null,
  model_name       text    not null,
  brand            text    not null,
  category         text    not null,          -- air-conditioner | ...
  price_paise      integer not null,          -- money is integer paise, never float
  warranty_covered boolean not null default false,
  scarce           boolean not null default false,
  image_url        text    not null
);

create table if not exists ecom_stock (
  id       bigint generated always as identity primary key,
  part_no  text    not null references ecom_products(part_no) on delete cascade,
  location text    not null,
  qty      integer not null check (qty >= 0),
  unique (part_no, location)
);

create index if not exists ecom_stock_part_no_idx on ecom_stock(part_no);

-- Atomic reserve: lock the best-stocked location with enough qty, decrement it, return true.
-- SELECT ... FOR UPDATE makes two concurrent reserves of the last unit safe: the loser sees no
-- eligible row and gets false (a refusal, NOT an oversell) — this is the NFR-5 inventory race.
create or replace function ecom_reserve(p_part_no text, p_qty integer)
returns boolean
language plpgsql
as $$
declare
  v_id bigint;
begin
  select id into v_id
    from ecom_stock
   where part_no = p_part_no and qty >= p_qty
   order by qty desc
   limit 1
   for update;

  if v_id is null then
    return false;
  end if;

  update ecom_stock set qty = qty - p_qty where id = v_id;
  return true;
end;
$$;
