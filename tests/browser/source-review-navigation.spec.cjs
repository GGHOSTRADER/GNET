const {test,expect}=require('./fixtures.cjs');
const {pipeline}=require('./pipeline-fixture.cjs');
for(const width of [1440,768,390])test('source review action belongs to the main UI '+width,async({page,harness})=>{
 pipeline(harness);await page.setViewportSize({width,height:1100});await page.goto('/research/');
 await expect(page.locator('#catalogCount')).toContainText('1 loaded');
 const heading=page.getByRole('region',{name:'Data preparation',exact:true});
 await expect(heading.getByRole('link',{name:'Review & approve sources'})).toHaveCount(0);
 await expect(page.locator('body > p')).toHaveCount(0);
 await expect(heading).toHaveScreenshot('source-review-action-'+width+'.png');
 await page.goto('/reviews/');
 await expect(page.locator('#notice')).toContainText('Select a received source');
 await expect(page.locator('#draft')).toBeDisabled();
});
