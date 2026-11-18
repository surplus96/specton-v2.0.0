import type { components } from './schema'

export type Specification = components['schemas']['SpecView']
export type Bundle = Specification['bundle']

export async function specificationRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const csrf = document.cookie.split('; ').find(v => v.startsWith('specton_csrf='))?.split('=')[1] ?? ''
  const response = await fetch('/api/v1' + path, {
    method, credentials: 'include',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => null) as { message?: string } | null
    throw new Error(response.status === 401 ? 'Google 계정으로 로그인해 주세요.' : error?.message ?? '요청을 처리하지 못했습니다.')
  }
  return response.json() as Promise<T>
}
