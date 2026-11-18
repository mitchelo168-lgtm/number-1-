import { expect, test } from '@playwright/test'
import { seedPendingClip } from './seed'

test('a seeded clip can be watched and approved end to end', async ({ page, request }) => {
  const clipId = seedPendingClip('e2e-clip-approve.ts', 0.91)

  await page.goto('/')

  const card = page.locator('.clip-card')
  await expect(card).toBeVisible()
  await expect(card.getByText('score: 0.91')).toBeVisible()
  await expect(card.getByText(/60s/)).toBeVisible()
  await expect(card.locator('video')).toHaveAttribute('src', /e2e-clip-approve\.ts$/)

  await card.getByRole('button', { name: 'Approve' }).click()

  await expect(page.getByText('Nothing waiting for review right now.')).toBeVisible()

  const apiResponse = await request.get(`http://127.0.0.1:8010/api/clips/`, {
    params: { review_status: 'approved' },
  })
  const approved = await apiResponse.json()
  expect(approved.some((c: { id: number }) => c.id === clipId)).toBe(true)
})

test('a seeded clip can be rejected end to end', async ({ page, request }) => {
  const clipId = seedPendingClip('e2e-clip-reject.ts', 0.6)

  await page.goto('/')

  const card = page.locator('.clip-card', { hasText: 'score: 0.60' })
  await expect(card).toBeVisible()

  await card.getByRole('button', { name: 'Reject' }).click()

  await expect(page.getByText('Nothing waiting for review right now.')).toBeVisible()

  const apiResponse = await request.get(`http://127.0.0.1:8010/api/clips/`, {
    params: { review_status: 'rejected' },
  })
  const rejected = await apiResponse.json()
  expect(rejected.some((c: { id: number }) => c.id === clipId)).toBe(true)
})
