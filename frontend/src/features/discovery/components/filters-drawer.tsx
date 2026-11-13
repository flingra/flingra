import { useState } from 'react'
import { Drawer } from '@/components/ui/drawer'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { DEFAULT_FILTERS } from '@/lib/api/profiles'
import type { DiscoveryFilters } from '@/lib/api/types'

interface FiltersDrawerProps {
  open: boolean
  onClose: () => void
  filters: DiscoveryFilters
  onApply: (filters: DiscoveryFilters) => void
}

export function FiltersDrawer({ open, onClose, filters, onApply }: FiltersDrawerProps) {
  const [draft, setDraft] = useState(filters)

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
