import { expect, test } from '@playwright/test'

// This spec shares one backend/DB instance with clip-review.spec.ts, so
// assertions target this test's own "e2e-shroud" row rather than assuming
// the streamer list is empty at any point.
test('add, untrack, and remove a streamer through the real API', async ({ page }) => {
  await page.goto('/')

  const row = page.locator('li', { hasText: 'e2e-shroud' })
  await expect(row).toHaveCount(0)

  await page.getByPlaceholder('channel id / login').fill('e2e-shroud')
  await page.getByPlaceholder('display name').fill('e2e-shroud')
  await page.getByRole('button', { name: 'Add' }).click()

  await expect(row).toBeVisible()
  await expect(row.getByText('TWITCH')).toBeVisible()
  await expect(row.getByRole('checkbox')).toBeChecked()

  // Persisted server-side, not just local state: reload and it's still there.
  await page.reload()
  await expect(row).toBeVisible()

  // The checkbox's checked state only flips once the PATCH request round-trips
  // and the list refetches, so click + a polling expectation (rather than
  // uncheck()'s stricter same-tick check) is what actually waits for that.
  await row.getByRole('checkbox').click()
  await expect(row.getByRole('checkbox')).not.toBeChecked()

  await page.reload()
  await expect(row.getByRole('checkbox')).not.toBeChecked()

  await row.getByRole('button', { name: 'Remove' }).click()
  await expect(row).toHaveCount(0)

  await page.reload()
  await expect(row).toHaveCount(0)
})

test('integrations panel reflects no credentials configured in this e2e environment', async ({ page }) => {
  await page.goto('/')

  const panel = page.locator('.credential-status')
  await expect(panel.getByText('Twitch')).toBeVisible()
  const dots = panel.locator('.dot')
  await expect(dots).toHaveCount(5)
  for (const dot of await dots.all()) {
    await expect(dot).toHaveClass(/missing/)
  }
})
