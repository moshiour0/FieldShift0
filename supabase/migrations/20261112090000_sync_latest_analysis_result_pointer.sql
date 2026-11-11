-- Keep the current result pointer in sync with the immutable result revision.
-- The worker writes analysis_results through an RLS-protected RPC. This narrow
-- trigger-owned update is performed as the database owner and cannot be
-- called as an application RPC.

create or replace function private.sync_latest_analysis_result_pointer()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $function$
begin
    if new.is_current then
        update public.analysis_runs
           set latest_result_id = new.id
         where id = new.run_id
           and latest_result_id is distinct from new.id;
    end if;
    return new;
end;
$function$;

revoke all on function private.sync_latest_analysis_result_pointer()
    from public, anon, authenticated;

drop trigger if exists analysis_results_sync_latest_run_pointer
    on public.analysis_results;

create trigger analysis_results_sync_latest_run_pointer
after insert on public.analysis_results
for each row
execute function private.sync_latest_analysis_result_pointer();

-- Repair the currently affected and any historical runs that have a current
-- revision but a missing pointer. Only the current result per run is selected.
with current_results as (
    select distinct on (run_id)
           run_id, id
      from public.analysis_results
     where is_current = true
     order by run_id, revision desc, created_at desc
)
update public.analysis_runs r
   set latest_result_id = c.id
  from current_results c
 where r.id = c.run_id
   and r.latest_result_id is distinct from c.id;

notify pgrst, 'reload schema';
