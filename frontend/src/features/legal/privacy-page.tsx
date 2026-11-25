export function PrivacyPage() {
  return (
    <article className="mx-auto max-w-2xl px-4 py-12">
      <p className="text-sm font-semibold text-primary-600">Version 1.0 · Effective from launch</p>
      <h1 className="mt-2 text-3xl font-bold text-ink-900">Privacy notice</h1>
      <div className="prose-sm mt-6 flex flex-col gap-4 text-ink-700">
        <p>
          This notice is placeholder content pending legal review. Flingra collects the minimum
          information needed to run the service: your contact details, profile information you choose to
          add, and coarse location if you enable it.
        </p>
        <p>
          We never show your exact location to other members, and discovery preferences you set stay
          private unless you choose to display them on your profile.
        </p>
        <p>
          You can request a copy of your data or delete your account from{' '}
          <a href="/settings/privacy" className="font-semibold text-primary-600 hover:underline">
            Privacy settings
          </a>
          .
        </p>
        <p>
          When you request account deletion, your profile is removed from discovery and access to
          your account is disabled. Records are retained where needed for legal and safety purposes.
        </p>
      </div>
    </article>
  )
}
