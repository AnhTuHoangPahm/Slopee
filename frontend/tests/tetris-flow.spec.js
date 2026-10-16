import { test, expect } from '@playwright/test';

test.describe('Tetris Game Flow', () => {

  test.beforeEach(async ({ page }) => {
    // Inject a fake session (user + token) into sessionStorage so the app allows access
    await page.addInitScript(() => {
      window.sessionStorage.setItem('token', 'e2e-fake-token');
      window.sessionStorage.setItem('user', JSON.stringify({
        id: 'test-user-id',
        name: 'Player One',
        role: 'buyer'
      }));
    });
  });

  test('User can start, play, pause, and hit game over in Tetris', async ({ page }) => {
    // 1. Navigate to the game
    await page.goto('/play/tetris');

    // 2. Verify the Start Screen is rendered
    const playButton = page.getByRole('button', { name: 'PLAY', exact: true });
    await expect(playButton).toBeVisible();

    // 3. Start the game
    await playButton.click();

    // 4. Verify game UI elements are visible (Score, Lines, Next block)
    await expect(page.getByText('SCORE')).toBeVisible();
    await expect(page.getByText('LINES')).toBeVisible();
    
    // 5. Simulate playing the game (Movement and Rotation)
    // We target the body or the wrapper to send keyboard events
    await page.waitForTimeout(20) // delay to start to take input
    await page.keyboard.press('ArrowLeft');
    await page.waitForTimeout(100);
    await page.keyboard.press('ArrowRight');
    await page.waitForTimeout(100);
    await page.keyboard.press('ArrowUp'); // Rotate
    await page.waitForTimeout(100);

    // 6. Test Pause functionality
    const pauseButton = page.getByRole('button', { name: 'PAUSE', exact: true });
    await pauseButton.click();
    await expect(page.getByText('PAUSED', { exact: true })).toBeVisible();
    
    // Resume
    const resumeButton = page.getByRole('button', { name: 'RESUME', exact: true });
    await resumeButton.click();
    await expect(page.getByText('PAUSED', { exact: true })).toBeHidden();

    // 7. Force a Game Over by rapidly Hard Dropping blocks
    // Mashing spacebar will stack blocks immediately until the board fills up
    for (let i = 0; i < 20; i++) {
      await page.keyboard.press('Space');
      await page.waitForTimeout(50); // slight delay to allow React state to update sweeps
    }

    // 8. Verify the Game Over screen appears
    const gameOverText = page.getByText('GAME OVER');
    await expect(gameOverText).toBeVisible({ timeout: 10000 });

    // 9. Verify we can return to the main menu
    await page.getByRole('button', { name: 'MAIN MENU', exact: true }).click();
    await expect(page.getByRole('button', { name: 'PLAY', exact: true })).toBeVisible();
  });
});
