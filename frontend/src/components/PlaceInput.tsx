import { useEffect, useId, useRef, useState } from 'react'
import { ApiError, searchPlaces } from '../api'
import type { Place } from '../types'

type Status = 'idle' | 'loading' | 'empty' | 'error'

export function PlaceInput({
  label,
  value,
  onChange,
  error,
  placeholder,
  name,
}: {
  label: string
  value: Place | null
  onChange: (p: Place | null) => void
  error?: string
  placeholder: string
  name: string
}) {
  const id = useId()
  const listId = `${id}-list`
  const errId = `${id}-err`
  const [text, setText] = useState(value?.label ?? '')
  const [results, setResults] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [status, setStatus] = useState<Status>('idle')
  const [searchError, setSearchError] = useState('')
  const typed = useRef(false)

  // Show the label when the parent sets a place (e.g. the example trip). Typing
  // clears the chosen place, and that must not wipe what the user is typing.
  useEffect(() => {
    if (value) setText(value.label)
  }, [value])

  useEffect(() => {
    if (!typed.current) return
    const q = text.trim()
    if (q.length < 3) {
      setResults([])
      setStatus('idle')
      return
    }
    const ctrl = new AbortController()
    const timer = setTimeout(async () => {
      setStatus('loading')
      try {
        const { results } = await searchPlaces(q, ctrl.signal)
        setResults(results)
        setActive(results.length ? 0 : -1)
        setStatus(results.length ? 'idle' : 'empty')
      } catch (err) {
        if ((err as Error).name === 'AbortError') return
        setResults([])
        setStatus('error')
        setSearchError(err instanceof ApiError ? err.message : 'Place search failed. Try again.')
      }
    }, 250)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
  }, [text])

  const choose = (p: Place) => {
    typed.current = false
    onChange(p)
    setText(p.label)
    setOpen(false)
    setResults([])
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp') && results.length) {
      setOpen(true)
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => Math.min(results.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(0, i - 1))
    } else if (e.key === 'Enter' && open && active >= 0 && results[active]) {
      e.preventDefault()
      choose(results[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const showList = open && text.trim().length >= 3 && (results.length > 0 || status !== 'idle')
  const describedBy = error ? errId : undefined

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        name={name}
        className="input"
        type="text"
        autoComplete="off"
        spellCheck={false}
        placeholder={placeholder}
        value={text}
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList && active >= 0 ? `${id}-opt-${active}` : undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        onChange={(e) => {
          typed.current = true
          setText(e.target.value)
          setOpen(true)
          if (value) onChange(null)
        }}
        onFocus={() => results.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
      />
      {showList && (
        <ul className="listbox" id={listId} role="listbox" aria-label={`${label} suggestions`}>
          {status === 'loading' && results.length === 0 && <li className="status">Searching…</li>}
          {status === 'empty' && <li className="status">No places match “{text.trim()}”. Try a city and state.</li>}
          {status === 'error' && <li className="status">{searchError}</li>}
          {results.map((p, i) => (
            <li
              key={`${p.label}-${i}`}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault()
                choose(p)
              }}
              onMouseEnter={() => setActive(i)}
            >
              {p.label}
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p className="field-error" id={errId}>
          {error}
        </p>
      )}
    </div>
  )
}
