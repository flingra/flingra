import { useState } from 'react'
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
}

export function FiltersDrawer({ open, onClose, filters, onApply }: FiltersDrawerProps) {
  const [draft, setDraft] = useState(filters)

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
              min={18}
              max={99}
              value={draft.minAge}
              onChange={(event) => setDraft((d) => ({ ...d, minAge: Number(event.target.value) }))}
            />
          </Field>
          <Field id="maxAge" label="Max age">
            <Input
              id="maxAge"
              type="number"
              min={18}
              max={99}
              value={draft.maxAge}
              onChange={(event) => setDraft((d) => ({ ...d, maxAge: Number(event.target.value) }))}
            />
          </Field>
        </div>
        <Field id="maxDistance" label="Maximum distance" hint="Exact location stays private.">
          <Input
            id="maxDistance"
            type="number"
            min={1}
            max={200}
            value={draft.maxDistanceKm}
            onChange={(event) => setDraft((d) => ({ ...d, maxDistanceKm: Number(event.target.value) }))}
          />
        </Field>

        <Field id="lookingFor" label="Show me">
          <Select
            id="lookingFor"
            value={draft.lookingFor}
            onChange={(event) => setDraft((d) => ({ ...d, lookingFor: event.target.value as AudiencePreference }))}
          >
            <option value="everyone">Everyone</option>
            <option value="men">Men</option>
            <option value="women">Women</option>
          </Select>
        </Field>

        <label className="flex items-center gap-3 text-sm text-ink-700">
          <Checkbox checked={draft.liveOnly} onChange={(event) => setDraft((d) => ({ ...d, liveOnly: event.target.checked }))} />
          Live right now only
        </label>

        <Field id="interests" label="Interests" optional>
          <div className="flex max-h-40 flex-wrap gap-2 overflow-y-auto">
            {INTERESTS.map((interest) => (
              <Chip key={interest} selected={draft.interests.includes(interest)} onClick={() => toggleInterest(interest)}>
                {interest}
              </Chip>
            ))}
          </div>
        </Field>

        <div className="mt-2 flex gap-3">
          <Button
            type="button"
            variant="secondary"
            className="flex-1"
            onClick={() => {
              setDraft(DEFAULT_FILTERS)
              onApply(DEFAULT_FILTERS)
            }}
          >
            Reset
          </Button>
          <Button type="button" className="flex-1" onClick={() => onApply(draft)}>
            Apply
          </Button>
        </div>
      </div>
    </Drawer>
  )
}
