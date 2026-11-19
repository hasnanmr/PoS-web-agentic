// Product brand "Thinker": the "Gelembung T" mark + name (design: 99 · Components → "Logo Thinker",
// used by the Sidebar/Owner and Sidebar/Staff components). The mark is public/favicon.svg.
export const PRODUCT_NAME = 'Thinker'

export function Brand({ size = 20, className = '' }: { size?: number; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-bold text-primary ${className}`}>
      <img src="/favicon.svg" alt="" width={size} height={size} className="shrink-0 rounded-[22%]" />
      {PRODUCT_NAME}
    </span>
  )
}
