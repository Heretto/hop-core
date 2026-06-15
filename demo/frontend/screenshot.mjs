import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
page.setDefaultTimeout(10000);

// Login page
await page.goto('http://localhost:4201/login');
await page.waitForLoadState('networkidle');
await page.screenshot({ path: '/tmp/hop-login.png', fullPage: true });
console.log('✓ login screenshot');

// Register flow from login
await page.click('button:has-text("Create Account")');
await page.waitForTimeout(500);
await page.screenshot({ path: '/tmp/hop-register.png', fullPage: true });
console.log('✓ register screenshot');

// Register a user
await page.fill('input[type="text"]', 'Demo Org');
await page.fill('input[type="email"]', 'demo@example.com');
await page.fill('input[type="password"]', 'password123');
await page.click('button[type="submit"]');
await page.waitForTimeout(1500);
await page.screenshot({ path: '/tmp/hop-after-register.png', fullPage: true });
console.log('✓ after-register screenshot');

// Log in
await page.goto('http://localhost:4201/login');
await page.waitForLoadState('networkidle');
await page.fill('input[type="email"]', 'demo@example.com');
await page.fill('input[type="password"]', 'password123');
await page.click('button[type="submit"]');
await page.waitForTimeout(2000);
await page.screenshot({ path: '/tmp/hop-dashboard.png', fullPage: true });
console.log('✓ dashboard screenshot, url:', page.url());

// Account page
await page.click('a:has-text("My Account")');
await page.waitForTimeout(1500);
await page.screenshot({ path: '/tmp/hop-account.png', fullPage: true });
console.log('✓ account screenshot');

// Admin page
await page.click('a:has-text("Administration")');
await page.waitForTimeout(1500);
await page.screenshot({ path: '/tmp/hop-admin.png', fullPage: true });
console.log('✓ admin screenshot');

await browser.close();
console.log('Done');
