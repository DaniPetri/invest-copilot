/** Product mixes behind the simulator's "Mischung" buttons. Keep in sync with MIXES in scripts/build_frontend_fixtures.py
 *  (a test compares them with the request stored in every simulation fixture). */
export type MixId = 'vorsichtig' | 'ausgewogen' | 'dynamisch'

export interface Mix {
  id: MixId
  label: string
  weights: { product_id: string; weight: number }[]
  description: string
}

export const MIXES: Record<MixId, Mix> = {
  vorsichtig: {
    id: 'vorsichtig',
    label: 'Vorsichtig',
    description: 'Überwiegend Anleihen, ein Teil Welt-Aktien',
    weights: [
      { product_id: 'P36', weight: 0.4 },
      { product_id: 'P33', weight: 0.3 },
      { product_id: 'P03', weight: 0.3 },
    ],
  },
  ausgewogen: {
    id: 'ausgewogen',
    label: 'Ausgewogen',
    description: '60 % Welt-Aktien, 40 % Staatsanleihen',
    weights: [
      { product_id: 'P03', weight: 0.6 },
      { product_id: 'P33', weight: 0.4 },
    ],
  },
  dynamisch: {
    id: 'dynamisch',
    label: 'Dynamisch',
    description: 'Welt-Aktien mit einem Technologie-Anteil',
    weights: [
      { product_id: 'P03', weight: 0.7 },
      { product_id: 'P22', weight: 0.3 },
    ],
  },
}

export const MIX_IDS = Object.keys(MIXES) as MixId[]
export const RATES = [25, 50, 100, 250] as const
export const YEARS = [5, 10, 20, 30] as const
