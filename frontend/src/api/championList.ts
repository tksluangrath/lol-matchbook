/**
 * Real champion names for /advice command parsing, fetched from the same
 * Data Dragon endpoint/patch the backend uses throughout this project
 * (app/data_pipeline/data_dragon.py, app/finetune/qualitative_advice.py) --
 * not a second, hardcoded list. No frontend picker/list existed before
 * this, so this is the real source fetched fresh, not a reuse of an
 * existing frontend list.
 */
const DDRAGON_CHAMPION_LIST_URL = 'https://ddragon.leagueoflegends.com/cdn/{patch}/data/en_US/champion.json'
const PATCH = '16.15.1'

let cached: Promise<string[]> | null = null

export async function fetchChampionNames(): Promise<string[]> {
  cached ??= fetch(DDRAGON_CHAMPION_LIST_URL.replace('{patch}', PATCH))
    .then((res) => res.json())
    .then((body: { data: Record<string, unknown> }) => Object.keys(body.data))
    .catch((err: unknown) => {
      cached = null // allow retry on next call rather than caching a failure
      throw err
    })
  return cached
}
