import { describe, expect, it } from 'vitest'
import { validate } from './schema'

describe('validate', () => {
  it('checks types, required and additionalProperties', () => {
    const schema = {
      type: 'object',
      properties: { a: { type: 'integer', minimum: 1 }, b: { type: 'string' } },
      required: ['a'],
      additionalProperties: false,
    }
    expect(validate(schema, { a: 1 })).toEqual([])
    expect(validate(schema, {})).toHaveLength(1)
    expect(validate(schema, { a: 0 })).toHaveLength(1)
    expect(validate(schema, { a: 1.5 })).toHaveLength(1)
    expect(validate(schema, { a: 1, c: true })).toHaveLength(1)
  })

  it('resolves $ref and anyOf with null', () => {
    const root = {
      $defs: { S: { type: 'object', properties: { x: { anyOf: [{ type: 'string' }, { type: 'null' }] } } } },
    }
    expect(validate({ $ref: '#/$defs/S' }, { x: null }, root)).toEqual([])
    expect(validate({ $ref: '#/$defs/S' }, { x: 3 }, root)).not.toEqual([])
  })

  it('validates arrays, enum, const, pattern and dates', () => {
    expect(validate({ type: 'array', items: { enum: ['a', 'b'] } }, ['a', 'c'])).toHaveLength(1)
    expect(validate({ const: 'trace' }, 'done')).toHaveLength(1)
    expect(validate({ type: 'string', pattern: '^P\\d{2}$' }, 'P07')).toEqual([])
    expect(validate({ type: 'string', pattern: '^P\\d{2}$' }, 'X07')).toHaveLength(1)
    expect(validate({ type: 'string', format: 'date' }, '2026-08-12')).toEqual([])
    expect(validate({ type: 'string', format: 'date' }, '12.08.2026')).toHaveLength(1)
  })

  it('uses the discriminator to pick the branch', () => {
    const root = {
      $defs: {
        A: { type: 'object', properties: { k: { const: 'a' }, n: { type: 'integer' } }, required: ['k', 'n'] },
        B: { type: 'object', properties: { k: { const: 'b' } }, required: ['k'] },
      },
      discriminator: { propertyName: 'k', mapping: { a: '#/$defs/A', b: '#/$defs/B' } },
      oneOf: [{ $ref: '#/$defs/A' }, { $ref: '#/$defs/B' }],
    }
    expect(validate(root, { k: 'a', n: 1 })).toEqual([])
    expect(validate(root, { k: 'a', n: 'x' })).toHaveLength(1)
    expect(validate(root, { k: 'z' })[0]).toContain('unknown k')
  })
})
