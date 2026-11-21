// The full privacy notice behind "Kebijakan privasi lengkap ›" (C5, C8, C10; FR12.1). It
// restates what the chat collects, why, where it is stored, and when it is deleted, in the
// same words as the short notice. The legally reviewed text per tenant comes with T-106 and
// replaces this page's body.
import { ChatHeader } from './ui'

export function PrivacyPage() {
  return (
    <div className="mx-auto min-h-dvh max-w-[480px] bg-page font-sans text-text">
      <ChatHeader initials="T" title="Thinker" subtitle="Kebijakan privasi pemesanan lewat chat" />
      <main className="space-y-3 px-4 py-4 text-[13px] leading-relaxed">
        <h2 className="text-[16px] font-semibold">Data yang kami minta</h2>
        <p>Saat kamu pesan atau reservasi lewat chat, kami meminta nama dan nomor HP. Untuk pesanan diantar, juga alamat antar.
          Di QR meja, cukup nama saja.</p>
        <h2 className="text-[16px] font-semibold">Untuk apa</h2>
        <p>Hanya supaya outlet bisa memproses pesanan atau reservasi itu dan menghubungi kamu kalau perlu. Tidak ada akun,
          tidak ada membership, dan pesananmu tidak dihubungkan ke kunjungan lain.</p>
        <h2 className="text-[16px] font-semibold">Disimpan di mana</h2>
        <p>Di server kami (Singapura), dalam bentuk terenkripsi.</p>
        <h2 className="text-[16px] font-semibold">Kapan dihapus</h2>
        <p>Otomatis setelah pesanan selesai atau batal, atau setelah reservasi selesai, batal, atau tidak datang. Catatan
          transaksi tetap ada tanpa data pribadimu.</p>
        <h2 className="text-[16px] font-semibold">Di HP kamu</h2>
        <p>Kalau kamu centang &quot;Ingat data di HP ini&quot;, nama, nomor HP, dan alamat disimpan di browser HP kamu saja
          (tidak di server). Kamu bisa menghapusnya dari chat kapan saja.</p>
      </main>
    </div>
  )
}
