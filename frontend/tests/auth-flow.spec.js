import { test, expect } from '@playwright/test';
import mysql from 'mysql2/promise';

const TEST_EMAIL = 'playwright_test@slopee.com';
const TEST_PHONE = '0000000000';

test.describe('Auth Flow', () => {
  // Option B: Teardown script directly connecting to MySQL
  test.afterAll(async () => {
    try {
      const connection = await mysql.createConnection({
        host: process.env.DB_HOST || '127.0.0.1',
        user: process.env.DB_USER || 'root',
        password: process.env.DB_PASSWORD || '',
        database: process.env.DB_NAME || 'slopee_db',
      });
      
      // Since `users` and `credentials` are linked by a foreign key, 
      // depending on the ON DELETE CASCADE setup, deleting the user will delete the credential.
      // If not cascaded, we must delete credentials first. We will delete from users and credentials.
      
      const [userRows] = await connection.execute(
        'SELECT id FROM users WHERE email = ?',
        [TEST_EMAIL]
      );
      
      if (userRows.length > 0) {
        const userId = userRows[0].id;
        await connection.execute('DELETE FROM credentials WHERE userId = ?', [userId]);
        await connection.execute('DELETE FROM users WHERE id = ?', [userId]);
        console.log(`🧹 Teardown Complete: Successfully purged test user ${userId} from database.`);
      }
      
      await connection.end();
    } catch (err) {
      console.error('Error during database teardown:', err);
    }
  });

  test('User can register successfully', async ({ page }) => {
    // Navigate to homepage
    await page.goto('/');

    // Click Sign Up link in the Navbar
    await page.getByRole('link', { name: 'Sign Up' }).click();
    await expect(page).toHaveURL(/.*signup/);

    // Fill out the registration form
    await page.getByPlaceholder('Full Name').fill('Playwright Tester');
    await page.getByPlaceholder('Email').fill(TEST_EMAIL);
    await page.getByPlaceholder('Phone').fill(TEST_PHONE);
    await page.getByPlaceholder('Username').fill('playwright123');
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    await page.getByPlaceholder('6-Digit Payment Passphrase').fill('123456');
    
    // Choose role
    // Assuming there is a select or radio for role, defaulting to user usually.
    // If there is a "Sign Up" button, click it.
    await page.getByRole('button', { name: 'Sign Up' }).click();

    // Verify successful registration by checking if we get redirected or see a success message
    // Usually it redirects to /login or /
    await expect(page).toHaveURL(/.*login|.*$/);
    
    // Optional: wait for a Toast notification or message
    // await expect(page.getByText('User registered successfully!')).toBeVisible();
  });
});
