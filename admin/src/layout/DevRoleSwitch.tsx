// TEMPORARY: dev-only role toggle until auth lands (T-006). Not part of the wireframe;
// rendered only in `vite dev`, never in production builds.
import { useRole } from '../app/role'

export function DevRoleSwitch() {
  const { role, setRole } = useRole()
  return (
    <div className="mt-auto pt-6">
      <label className="block rounded-md border border-dashed border-border px-2 py-1.5 text-[11px] text-text-muted">
        Dev · peran
        <select
          aria-label="Peran (dev)"
          className="ml-2 rounded border border-border bg-surface px-1 text-[11px] text-text"
          value={role}
          onChange={(event) => setRole(event.target.value === 'staff' ? 'staff' : 'owner')}
        >
          <option value="owner">Owner</option>
          <option value="staff">Staf</option>
        </select>
      </label>
    </div>
  )
}
