import { test, expect } from '@playwright/test';

test('baseline progressive disclosure - Palovarotene FOP mechanism', async ({ page }) => {
  // Navigate to app
  await page.goto('http://localhost:3000');
  await page.waitForLoadState('networkidle');

  // Take initial screenshot
  await page.screenshot({
    path: '../../baseline-screenshots/00-initial.png',
    fullPage: true
  });

  // Enter competency question
  const query = 'By what mechanism does Palovarotene treat Fibrodysplasia Ossificans Progressiva (FOP)?';

  const textarea = page.locator('textarea').first();
  await textarea.fill(query);
  await textarea.press('Enter');

  console.log('Query submitted, waiting for phases...');

  // Wait and capture each phase
  const phases = [
    { name: 'anchor_specialist', file: '01-phase1-anchor.png', timeout: 60000 },
    { name: 'enrichment_specialist', file: '02-phase2-enrich.png', timeout: 60000 },
    { name: 'expansion_specialist', file: '03-phase3-expand.png', timeout: 60000 },
    { name: 'traversal_drugs_specialist', file: '04-phase4a-drugs.png', timeout: 60000 },
    { name: 'traversal_trials_specialist', file: '05-phase4b-trials.png', timeout: 60000 },
    { name: 'validation_specialist', file: '06-phase5-validate.png', timeout: 60000 },
    { name: 'persistence_specialist', file: '07-phase6-persist.png', timeout: 90000 },
  ];

  for (const phase of phases) {
    try {
      console.log(`Waiting for ${phase.name}...`);

      // Wait for phase to appear (case insensitive)
      await page.waitForSelector(`text=/${phase.name}/i`, {
        timeout: phase.timeout
      });

      // Wait for content to render
      await page.waitForTimeout(2000);

      // Capture screenshot
      await page.screenshot({
        path: `../../baseline-screenshots/${phase.file}`,
        fullPage: true
      });

      console.log(`✓ Captured ${phase.name}`);
    } catch (e) {
      console.log(`⚠ Timeout waiting for ${phase.name}`);
      await page.screenshot({
        path: `../../baseline-screenshots/${phase.file.replace('.png', '-timeout.png')}`,
        fullPage: true
      });
    }
  }

  // Final complete state
  await page.waitForTimeout(5000);
  await page.screenshot({
    path: '../../baseline-screenshots/08-final-complete.png',
    fullPage: true
  });

  // Count completed phases
  const doneCount = await page.locator('text=/Done/i').count();
  console.log(`Found ${doneCount} completed phases`);

  expect(doneCount).toBeGreaterThanOrEqual(6);
});
