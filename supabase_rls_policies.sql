alter table public.repair_rates enable row level security;

grant usage on schema public to anon;
grant select, insert, update on public.repair_rates to anon;
grant usage, select on all sequences in schema public to anon;

drop policy if exists "repair_rates_select_anon" on public.repair_rates;
create policy "repair_rates_select_anon"
on public.repair_rates
for select
to anon
using (true);

drop policy if exists "repair_rates_insert_anon" on public.repair_rates;
create policy "repair_rates_insert_anon"
on public.repair_rates
for insert
to anon
with check (true);

drop policy if exists "repair_rates_update_anon" on public.repair_rates;
create policy "repair_rates_update_anon"
on public.repair_rates
for update
to anon
using (true)
with check (true);
