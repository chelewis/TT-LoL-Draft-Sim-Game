import { describe, expect, it } from 'vitest'
import { searchQuery } from './search'

describe('searchQuery', () => {
  it('drops empty filters and repeats arrays', () => {
    expect(searchQuery({ q: 'fak', role: '', rank_min: null, aggr_min: 5, champions: [3, 7], tags: [], x: undefined }))
      .toBe('q=fak&aggr_min=5&champions=3&champions=7')
  })
  it('keeps zero', () => {
    expect(searchQuery({ offset: 0 })).toBe('offset=0')
  })
})
