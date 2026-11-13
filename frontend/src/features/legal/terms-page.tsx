export function TermsPage() {
  return (
    <article className="mx-auto max-w-2xl px-4 py-12">
      <p className="text-sm font-semibold text-primary-600">Version 1.0 · Effective from launch</p>
      <h1 className="mt-2 text-3xl font-bold text-ink-900">Terms of use</h1>
      <div className="prose-sm mt-6 flex flex-col gap-4 text-ink-700">
        <p>
          These terms are placeholder content pending legal review. Flingra is intended only for
          consenting adults aged 18 and over who agree to use the service lawfully and respectfully.
        </p>
        <p>
          By creating an account you confirm you meet the age requirement, agree not to misuse the
          platform, and accept that Flingra does not guarantee the identity, intentions, or safety of any
          member.
        </p>
        <p>
          Flingra may suspend or remove accounts that violate these terms, including behaviour reported
          through the in-app reporting tools. See the{' '}
          <a href="/safety" className="font-semibold text-primary-600 hover:underline">
            safety guidance
          </a>{' '}
          for how to stay safe.
        </p>
      </div>
    </article>
  )
}
