// Supabase Auth error text → wireframe O1 copy.
export function authErrorCopy(message: string): string {
  if (/account_inactive|banned/i.test(message)) return 'Akun dinonaktifkan'
  if (/account_not_invited/i.test(message)) return 'Email belum diundang'
  if (/invalid login credentials/i.test(message)) return 'Email atau password salah.'
  if (/email not confirmed/i.test(message)) return 'Buka link undangan di email untuk atur password.'
  return 'Gagal masuk. Coba lagi.'
}

