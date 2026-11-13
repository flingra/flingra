import { Button, type ButtonProps } from '@/components/ui/button'

function GoogleMark() {
  return (
    <svg className="size-4.5" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.47a5.54 5.54 0 0 1-2.4 3.63v3h3.89c2.27-2.09 3.58-5.17 3.58-8.82Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.07 7.95-2.91l-3.89-3a7.4 7.4 0 0 1-11-3.89H1.06v3.09A12 12 0 0 0 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.07 14.2a7.2 7.2 0 0 1 0-4.6V6.51H1.07a12 12 0 0 0 0 10.78l4-3.1Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.75a6.52 6.52 0 0 1 4.6 1.8l3.45-3.45A11.6 11.6 0 0 0 12 0 12 12 0 0 0 1.06 6.51l4 3.1A7.16 7.16 0 0 1 12 4.75Z"
      />
    </svg>
  )
}

export function GoogleButton({ label, loading, ...props }: { label: string } & Omit<ButtonProps, 'variant' | 'children'>) {
  return (
    <Button type="button" variant="outline" className="border-ink-200" loading={loading} {...props}>
      {!loading && <GoogleMark />}
      {label}
    </Button>
  )
}
