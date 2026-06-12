alter table public.repair_rates
add column if not exists production_type text not null default 'Coil';

create index if not exists idx_repair_rates_production_type
on public.repair_rates (production_type);
