/**
 * Minimal JSON Schema validator: exactly the keywords pydantic emits into contracts/*.schema.json.
 * Hand-written on purpose (no ajv dependency). Returns a list of human-readable errors; empty = valid.
 */

export type Schema = Record<string, unknown>

const DATE = /^\d{4}-\d{2}-\d{2}$/

function typeOf(value: unknown): string {
  if (value === null) return 'null'
  if (Array.isArray(value)) return 'array'
  if (typeof value === 'number') return Number.isInteger(value) ? 'integer' : 'number'
  return typeof value
}

function matchesType(value: unknown, type: string): boolean {
  const actual = typeOf(value)
  return actual === type || (type === 'number' && actual === 'integer')
}

function resolveRef(ref: string, root: Schema): Schema {
  if (!ref.startsWith('#/')) throw new Error(`unsupported $ref: ${ref}`)
  let node: unknown = root
  for (const part of ref.slice(2).split('/')) node = (node as Record<string, unknown>)?.[part]
  if (!node || typeof node !== 'object') throw new Error(`unresolved $ref: ${ref}`)
  return node as Schema
}

export function validate(schema: Schema, value: unknown, root: Schema = schema, path = '$'): string[] {
  if (typeof schema.$ref === 'string') return validate(resolveRef(schema.$ref, root), value, root, path)

  if ('const' in schema && value !== schema.const) return [`${path}: expected ${JSON.stringify(schema.const)}`]
  if (Array.isArray(schema.enum) && !schema.enum.includes(value)) {
    return [`${path}: ${JSON.stringify(value)} not in enum`]
  }

  const anyOf = schema.anyOf as Schema[] | undefined
  if (anyOf) {
    const attempts = anyOf.map((s) => validate(s, value, root, path))
    return attempts.some((e) => e.length === 0) ? [] : [`${path}: matches none of anyOf (${attempts[0][0]})`]
  }

  const oneOf = schema.oneOf as Schema[] | undefined
  if (oneOf) {
    const disc = schema.discriminator as { propertyName: string; mapping?: Record<string, string> } | undefined
    if (disc && value && typeof value === 'object') {
      const tag = (value as Record<string, unknown>)[disc.propertyName]
      const target = typeof tag === 'string' ? disc.mapping?.[tag] : undefined
      if (!target) return [`${path}: unknown ${disc.propertyName} ${JSON.stringify(tag)}`]
      return validate(resolveRef(target, root), value, root, path)
    }
    const matches = oneOf.filter((s) => validate(s, value, root, path).length === 0).length
    return matches === 1 ? [] : [`${path}: matches ${matches} of oneOf, expected exactly 1`]
  }

  const errors: string[] = []
  if (typeof schema.type === 'string' && !matchesType(value, schema.type)) {
    return [`${path}: expected ${schema.type}, got ${typeOf(value)}`]
  }

  if (typeof value === 'number') {
    if (typeof schema.minimum === 'number' && value < schema.minimum) errors.push(`${path}: below minimum ${schema.minimum}`)
    if (typeof schema.maximum === 'number' && value > schema.maximum) errors.push(`${path}: above maximum ${schema.maximum}`)
    if (typeof schema.exclusiveMinimum === 'number' && value <= schema.exclusiveMinimum) {
      errors.push(`${path}: must be > ${schema.exclusiveMinimum}`)
    }
  }

  if (typeof value === 'string') {
    if (typeof schema.pattern === 'string' && !new RegExp(schema.pattern).test(value)) {
      errors.push(`${path}: does not match /${schema.pattern}/`)
    }
    if (schema.format === 'date' && !DATE.test(value)) errors.push(`${path}: not a date`)
  }

  if (Array.isArray(value) && schema.items) {
    value.forEach((item, i) => errors.push(...validate(schema.items as Schema, item, root, `${path}[${i}]`)))
  }

  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const obj = value as Record<string, unknown>
    const props = (schema.properties ?? {}) as Record<string, Schema>
    for (const key of (schema.required ?? []) as string[]) {
      if (!(key in obj)) errors.push(`${path}: missing required "${key}"`)
    }
    for (const [key, val] of Object.entries(obj)) {
      if (key in props) errors.push(...validate(props[key], val, root, `${path}.${key}`))
      else if (schema.additionalProperties === false) errors.push(`${path}: unexpected property "${key}"`)
      else if (schema.additionalProperties && typeof schema.additionalProperties === 'object') {
        errors.push(...validate(schema.additionalProperties as Schema, val, root, `${path}.${key}`))
      }
    }
  }

  return errors
}
