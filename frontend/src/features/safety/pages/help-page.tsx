export function HelpPage() {
  return (
    <article className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="text-3xl font-bold text-ink-900">Help &amp; support</h1>

      <div className="mt-8 flex flex-col gap-6">
        <section>
          <h2 className="text-lg font-bold text-ink-900">Contact support</h2>
          <p className="mt-2 text-ink-700">
            Email{' '}
            <a href="mailto:support@flingra.example" className="font-semibold text-primary-600 hover:underline">
              support@flingra.example
            </a>{' '}
            for account issues, moderation appeals, or anything else.
          </p>
        </section>
        <section>
          <h2 className="text-lg font-bold text-ink-900">Common questions</h2>
          <dl className="mt-3 flex flex-col gap-4">
            <div>
              <dt className="font-semibold text-ink-800">How do I delete my account?</dt>
              <dd className="mt-1 text-ink-600">
                Go to Settings &rsaquo; Privacy and choose Delete account. You'll see what happens to your
                data before confirming.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-ink-800">Can other members see my exact location?</dt>
              <dd className="mt-1 text-ink-600">
                No. Flingra only shows an approximate area or distance, never exact coordinates.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-ink-800">What happens after I report someone?</dt>
              <dd className="mt-1 text-ink-600">
                Our moderation team reviews the report. We don't disclose the outcome or your identity to
                the reported member.
              </dd>
            </div>
          </dl>
        </section>
      </div>
    </article>
  )
}
