// Shown instead of the app when VITE_* configuration is missing or invalid (fail visibly).
interface EnvErrorScreenProps {
  issues: { key: string; message: string }[]
}

export function EnvErrorScreen({ issues }: EnvErrorScreenProps) {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-page p-4 text-text">
      <div role="alert" className="w-full max-w-lg rounded-lg border border-danger bg-surface p-6">
        <h1 className="text-[18px] font-bold text-danger">Konfigurasi aplikasi tidak valid</h1>
        <p className="mt-1 text-[13px] text-text-muted">
          Periksa file <code>admin/.env.local</code> (salin dari <code>admin/.env.example</code>)
          lalu jalankan ulang <code>pnpm dev</code>.
        </p>
        <ul className="mt-4 space-y-1 rounded-md bg-danger-soft p-3 text-[13px] text-danger">
          {issues.map((issue) => (
            <li key={issue.key}>
              <code className="font-semibold">{issue.key}</code>: {issue.message}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
