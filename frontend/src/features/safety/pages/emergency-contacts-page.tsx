import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, MapPin, Phone, Siren, Trash2, UserPlus } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { PageSpinner } from '@/components/ui/spinner'
import { EmptyState } from '@/components/ui/state-message'
import { useToast } from '@/components/ui/toast'
import {
  addEmergencyContact,
  getCurrentLocationLink,
  listEmergencyContacts,
  listSafetyCheckIns,
  notifyEmergencyContacts,
  removeEmergencyContact,
} from '@/lib/api/safety'
import { ApiError } from '@/lib/api/types'

export function EmergencyContactsPage() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()

  const { data: contacts, isLoading } = useQuery({ queryKey: ['emergency-contacts'], queryFn: listEmergencyContacts })
  const { data: checkIns } = useQuery({ queryKey: ['safety-check-ins'], queryFn: listSafetyCheckIns })

  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [relationship, setRelationship] = useState('')
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  const [message, setMessage] = useState('')
  const [notifying, setNotifying] = useState(false)
  const [locatingStatus, setLocatingStatus] = useState<'idle' | 'locating' | 'found' | 'unavailable'>('idle')

  async function handleAddContact() {
    setAddError(null)
    setAdding(true)
    try {
      await addEmergencyContact({ name, phone, relationship })
      await queryClient.invalidateQueries({ queryKey: ['emergency-contacts'] })
      setName('')
      setPhone('')
      setRelationship('')
      showToast({ title: 'Emergency contact added', variant: 'success' })
    } catch (err) {
      setAddError(err instanceof ApiError ? err.message : 'Could not add contact. Try again.')
    } finally {
      setAdding(false)
    }
  }

  async function handleRemoveContact(id: string) {
    await removeEmergencyContact(id)
    await queryClient.invalidateQueries({ queryKey: ['emergency-contacts'] })
  }

  async function handleNotify() {
    setNotifying(true)
    setLocatingStatus('locating')
    try {
      const locationLink = await getCurrentLocationLink()
      setLocatingStatus(locationLink ? 'found' : 'unavailable')
      const checkIn = await notifyEmergencyContacts(message, locationLink ?? undefined)
      await queryClient.invalidateQueries({ queryKey: ['safety-check-ins'] })
      setMessage('')
      showToast({
        title: 'Contacts notified',
        description: locationLink
          ? `${checkIn.notifiedContacts.length} emergency contact(s) alerted with your live location.`
          : `${checkIn.notifiedContacts.length} emergency contact(s) alerted. Location wasn't available.`,
        variant: 'success',
      })
    } catch (err) {
      showToast({
        title: 'Could not notify contacts',
        description: err instanceof ApiError ? err.message : 'Try again.',
        variant: 'error',
      })
    } finally {
      setNotifying(false)
    }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <Link to="/safety" className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-600 hover:text-ink-900">
        <ArrowLeft className="size-4" aria-hidden="true" /> Safety
      </Link>

      <h1 className="mt-4 text-2xl font-bold text-ink-900">Emergency contacts</h1>
      <p className="mt-1 text-sm text-ink-500">
        Add people you trust. Before a meetup, let them know where you'll be — or alert them instantly if something
        feels wrong.
      </p>

      <Card className="mt-6 border-danger/20 bg-danger/5">
        <div className="flex items-center gap-3">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-danger text-white">
            <Siren className="size-5" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-lg font-bold text-ink-900">Notify my contacts now</h2>
            <p className="text-sm text-ink-500">Sends your check-in message and live location to everyone on this list.</p>
          </div>
        </div>
        <p className="mt-3 flex items-center gap-1.5 text-xs text-ink-500">
          <MapPin className="size-3.5 shrink-0" aria-hidden="true" />
          {notifying
            ? 'Getting your current location…'
            : "We'll ask your browser for your current location and share a map link with your contacts."}
        </p>
        <Field id="checkin-message" label="Message" className="mt-4" optional hint="Leave blank to use the default message.">
          <Textarea
            id="checkin-message"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="I'm meeting someone from Flingra at Lekki Phase 1 around 7pm."
            maxLength={280}
          />
        </Field>
        <Button variant="destructive" className="mt-4 w-full" loading={notifying} onClick={handleNotify}>
          <Siren className="size-4" aria-hidden="true" />
          {notifying && locatingStatus === 'locating' ? 'Getting location…' : 'Notify my emergency contacts'}
        </Button>
      </Card>

      <Card className="mt-6">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-600">
            <UserPlus className="size-5" aria-hidden="true" />
          </span>
          <h2 className="text-lg font-bold text-ink-900">Add a contact</h2>
        </div>
        <div className="mt-4 flex flex-col gap-4">
          <Field id="contact-name" label="Name">
            <Input id="contact-name" value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field id="contact-phone" label="Phone number">
            <Input id="contact-phone" type="tel" value={phone} onChange={(event) => setPhone(event.target.value)} />
          </Field>
          <Field id="contact-relationship" label="Relationship" optional>
            <Input
              id="contact-relationship"
              value={relationship}
              onChange={(event) => setRelationship(event.target.value)}
              placeholder="e.g. Sister, Best friend"
            />
          </Field>
          {addError && <p role="alert" className="text-sm font-medium text-danger">{addError}</p>}
          <Button loading={adding} disabled={!name || !phone} onClick={handleAddContact}>
            Add contact
          </Button>
        </div>
      </Card>

      <div className="mt-8">
        <h2 className="text-lg font-bold text-ink-900">Your contacts</h2>
        {isLoading && <PageSpinner label="Loading contacts" />}
        {contacts && contacts.length === 0 && (
          <div className="mt-3">
            <EmptyState title="No emergency contacts yet" description="Add at least one trusted contact above." />
          </div>
        )}
        {contacts && contacts.length > 0 && (
          <ul className="mt-3 flex flex-col gap-3">
            {contacts.map((contact) => (
              <li key={contact.id} className="flex items-center gap-3 rounded-2xl border border-ink-100 bg-white p-4 shadow-soft">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-ink-50 text-ink-500">
                  <Phone className="size-4" aria-hidden="true" />
                </span>
                <div className="flex-1">
                  <p className="font-semibold text-ink-900">{contact.name}</p>
                  <p className="text-sm text-ink-500">
                    {contact.phone}
                    {contact.relationship ? ` · ${contact.relationship}` : ''}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleRemoveContact(contact.id)}
                  aria-label={`Remove ${contact.name}`}
                  className="flex size-9 cursor-pointer items-center justify-center rounded-full text-ink-400 hover:bg-danger/10 hover:text-danger"
                >
                  <Trash2 className="size-4" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {checkIns && checkIns.length > 0 && (
        <div className="mt-8">
          <h2 className="text-lg font-bold text-ink-900">Check-in history</h2>
          <ul className="mt-3 flex flex-col gap-3">
            {checkIns.map((checkIn) => (
              <li key={checkIn.id} className="rounded-2xl border border-ink-100 bg-white p-4 shadow-soft">
                <p className="text-sm text-ink-800">{checkIn.message}</p>
                <p className="mt-1 text-xs text-ink-400">
                  Sent to {checkIn.notifiedContacts.join(', ')} · {new Date(checkIn.createdAt).toLocaleString()}
                </p>
                {checkIn.locationLink && (
                  <a
                    href={checkIn.locationLink}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1.5 inline-flex items-center gap-1 text-xs font-semibold text-primary-600 hover:underline"
                  >
                    <MapPin className="size-3.5" aria-hidden="true" /> View shared location
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
