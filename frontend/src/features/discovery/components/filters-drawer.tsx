import { useEffect, useState } from 'react'
import { Drawer } from '@/components/ui/drawer'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Chip } from '@/components/ui/chip'
import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import { DEFAULT_FILTERS } from '@/lib/api/profiles'
import type { AudiencePreference, DiscoveryFilters } from '@/lib/api/types'
import { INTERESTS } from '@/lib/constants/interests'

interface FiltersDrawerProps {
  open: boolean
  onClose: () => void
  filters: DiscoveryFilters
  onApply: (filters: DiscoveryFilters) => void
  distanceEnabled: boolean
}

export function FiltersDrawer({ open, onClose, filters, onApply, distanceEnabled }: FiltersDrawerProps) {
  const [draft, setDraft] = useState(filters)
  const [filterError, setFilterError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setDraft(filters)
    setFilterError(null)
  }, [filters, open])

  function applyDraft() {
    if (!Number.isInteger(draft.minAge) || draft.minAge < 21 || draft.minAge > 99) {
      setFilterError('Minimum age must be a whole number between 21 and 99.')
      return
    }
    if (!Number.isInteger(draft.maxAge) || draft.maxAge < draft.minAge || draft.maxAge > 99) {
      setFilterError('Maximum age must be a whole number at least as high as the minimum age, up to 99.')
      return
    }
    if (!Number.isFinite(draft.maxDistanceKm) || draft.maxDistanceKm < 1 || draft.maxDistanceKm > 200) {
      setFilterError('Maximum distance must be between 1 and 200 km.')
      return
    }

    setFilterError(null)
    onApply(draft)
  }

  function toggleInterest(interest: string) {
    setDraft((d) => ({
      ...d,
      interests: d.interests.includes(interest) ? d.interests.filter((item) => item !== interest) : [...d.interests, interest],
    }))
  }

  return (
    <Drawer open={open} onClose={onClose} title="Filters">
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-4">
          <Field id="minAge" label="Min age">
            <Input
              id="minAge"
              type="number"
              min={21}
              max={99}
              value={draft.minAge}
              onChange={(event) => {
                setFilterError(null)
                setDraft((d) => ({ ...d, minAge: Number(event.target.value) }))
              }}
            />
          </Field>
          <Field id="maxAge" label="Max age">
            <Input
              id="maxAge"
              type="number"
              min={21}
              max={99}
              value={draft.maxAge}
              onChange={(event) => {
                setFilterError(null)
                setDraft((d) => ({ ...d, maxAge: Number(event.target.value) }))
              }}
            />
          </Field>
        </div>
        <Field
          id="maxDistance"
          label="Maximum distance"
          hint={
            distanceEnabled
              ? 'Approximate distance from your current location. Exact location stays private.'
              : 'Enable Distance above the map to filter from your current location.'
          }
        >
          <Input
            id="maxDistance"
            type="number"
            min={1}
            max={200}
            value={draft.maxDistanceKm}
            onChange={(event) => {
              setFilterError(null)
              setDraft((d) => ({ ...d, maxDistanceKm: Number(event.target.value) }))
            }}
          />
        </Field>

        <Field id="lookingFor" label="Show me">
          <Select
            id="lookingFor"
            value={draft.lookingFor}
            onChange={(event) => {
              setFilterError(null)
              setDraft((d) => ({ ...d, lookingFor: event.target.value as AudiencePreference }))
            }}
          >
            <option value="everyone">Everyone</option>
            <option value="men">Men</option>
            <option value="women">Women</option>
          </Select>
        </Field>

        <label className="flex items-center gap-3 text-sm text-ink-500">
          <Checkbox checked={false} disabled />
          Live right now only (coming soon)
        </label>

        <Field id="interests" label="Interests" optional>
          <div className="flex max-h-40 flex-wrap gap-2 overflow-y-auto">
            {INTERESTS.map((interest) => (
              <Chip
                key={interest}
                selected={draft.interests.includes(interest)}
                onClick={() => {
                  setFilterError(null)
                  toggleInterest(interest)
                }}
              >
                {interest}
              </Chip>
            ))}
          </div>
        </Field>

        {filterError && <p className="text-sm text-red-600" role="alert">{filterError}</p>}

        <div className="mt-2 flex gap-3">
          <Button
            type="button"
            variant="secondary"
            className="flex-1"
            onClick={() => {
              setFilterError(null)
              setDraft(DEFAULT_FILTERS)
              onApply(DEFAULT_FILTERS)
            }}
          >
            Reset
          </Button>
          <Button type="button" className="flex-1" onClick={applyDraft}>
            Apply
          </Button>
        </div>
      </div>
    </Drawer>
  )
}
