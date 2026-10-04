import { test as base, expect } from '@playwright/test'

// Existing account scenarios start without an avatar; individual cases can override this route.
export const test = base.extend({
  page: async ({ page }, use) => {
    await page.route('https://124.220.147.193/api/v1/me/avatar', route => route.fulfill({ status: 404, json: { code: 'NO_AVATAR' } }))
    await use(page)
  },
})
export { expect }
